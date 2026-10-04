import frappe
from frappe import _
from frappe.utils import cint, flt

CUSTOM_FIELD = "custom_vehicle_import_file"
DOWNSTREAM_STATUSES = {"Reserved", "Sold", "Delivered", "Under Maintenance"}


def get_settings():
	return frappe.get_single("AN Truck Settings")


def is_vehicle_item(item_code):
	settings = get_settings()
	if not settings.vehicle_item_group:
		frappe.throw(_("Set Vehicle Item Group in AN Truck Settings before receiving vehicle items."))
	item_group = frappe.db.get_value("Item", item_code, "item_group")
	if not item_group:
		return False
	if item_group == settings.vehicle_item_group:
		return True
	group_bounds = frappe.db.get_value("Item Group", settings.vehicle_item_group, ["lft", "rgt"], as_dict=True)
	item_bounds = frappe.db.get_value("Item Group", item_group, ["lft", "rgt"], as_dict=True)
	if not group_bounds or not item_bounds:
		return False
	return cint(group_bounds.lft) <= cint(item_bounds.lft) and cint(item_bounds.rgt) <= cint(group_bounds.rgt)


def get_vehicle_rows(doc):
	return [row for row in doc.get("items", []) if is_vehicle_item(row.item_code)]


def get_serials_for_row(row):
	serials = []
	if row.get("serial_and_batch_bundle"):
		serials.extend(
			frappe.get_all(
				"Serial and Batch Entry",
				filters={"parent": row.serial_and_batch_bundle, "serial_no": ["is", "set"]},
				pluck="serial_no",
				order_by="idx asc",
			)
		)
	if row.get("serial_no"):
		serials.extend([value.strip() for value in row.serial_no.replace(",", "\n").split("\n") if value.strip()])
	return list(dict.fromkeys(serials))


def validate_import_file_for_purchase_doc(doc, method=None):
	import_file = doc.get(CUSTOM_FIELD)
	if not import_file:
		return
	vif = frappe.get_doc("Vehicle Import File", import_file)
	if vif.status == "Cancelled":
		frappe.throw(_("Cannot link cancelled Vehicle Import File {0}.").format(import_file))
	if doc.company != vif.company:
		frappe.throw(_("Company must match Vehicle Import File {0}.").format(import_file))
	if getattr(doc, "supplier", None) and doc.supplier != vif.supplier:
		frappe.throw(_("Supplier must match Vehicle Import File {0}.").format(import_file))
	if doc.doctype == "Purchase Order" and doc.currency and vif.supplier_currency and doc.currency != vif.supplier_currency:
		frappe.throw(_("Purchase Order currency must match Vehicle Import File currency."))


def before_validate_purchase_receipt(doc, method=None):
	set_purchase_receipt_import_file(doc)
	validate_purchase_receipt(doc)


def set_purchase_receipt_import_file(doc):
	files = {doc.get(CUSTOM_FIELD)} if doc.get(CUSTOM_FIELD) else set()
	for row in doc.items:
		if row.purchase_order:
			po_file = frappe.db.get_value("Purchase Order", row.purchase_order, CUSTOM_FIELD)
			if po_file:
				files.add(po_file)
	if len(files) > 1:
		frappe.throw(_("Purchase Receipt cannot contain Purchase Orders from different Vehicle Import Files."))
	if files and not doc.get(CUSTOM_FIELD):
		doc.set(CUSTOM_FIELD, next(iter(files)))


def validate_purchase_receipt(doc):
	validate_import_file_for_purchase_doc(doc)
	settings = get_settings()
	vehicle_rows = get_vehicle_rows(doc)
	if vehicle_rows and settings.require_import_file_on_vehicle_receipt and not doc.get(CUSTOM_FIELD):
		frappe.throw(_("Vehicle Import File is required for vehicle item receipts."))
	if not vehicle_rows:
		return
	vif = frappe.get_doc("Vehicle Import File", doc.get(CUSTOM_FIELD))
	if vif.status == "Cancelled":
		frappe.throw(_("Cancelled Vehicle Import Files cannot receive vehicles."))
	seen = set()
	for row in vehicle_rows:
		serials = get_serials_for_row(row)
		if not serials:
			frappe.throw(_("Row {0}, Item {1}: VIN/Serial Number is required.").format(row.idx, row.item_code))
		if len(serials) != cint(row.qty):
			frappe.throw(_("Row {0}, Item {1}: number of VINs must equal received quantity.").format(row.idx, row.item_code))
		for vin in serials:
			if vin in seen:
				frappe.throw(_("Row {0}, Item {1}: duplicate VIN {2}.").format(row.idx, row.item_code, vin))
			seen.add(vin)
			serial_item = frappe.db.get_value("Serial No", vin, "item_code")
			if serial_item and serial_item != row.item_code:
				frappe.throw(_("Row {0}, Item {1}: VIN {2} belongs to Item {3}.").format(row.idx, row.item_code, vin, serial_item))
			existing = frappe.db.get_value("Vehicle Master", {"vin": vin}, ["name", "item_code", "vehicle_import_file"], as_dict=True)
			if existing and (existing.item_code != row.item_code or existing.vehicle_import_file != doc.get(CUSTOM_FIELD)):
				frappe.throw(_("VIN {0} is already linked to another Item or Vehicle Import File.").format(vin))

	expected = flt(vif.total_expected_vehicles)
	if expected and flt(vif.total_received_vehicles) + len(seen) > expected and not frappe.has_role("System Manager"):
		frappe.throw(_("Received VIN count would exceed expected vehicles for Vehicle Import File {0}.").format(vif.name))


def on_submit_purchase_receipt(doc, method=None):
	if not doc.get(CUSTOM_FIELD) or not get_settings().auto_create_vehicle_master:
		return
	created = existing = 0
	for row in get_vehicle_rows(doc):
		for vin in get_serials_for_row(row):
			if create_or_update_vehicle_master(doc, row, vin):
				created += 1
			else:
				existing += 1
	refresh_import_file(doc.get(CUSTOM_FIELD))
	frappe.msgprint(_("{0} Vehicle Master records created. {1} Vehicle Master records already existed.").format(created, existing))


def create_or_update_vehicle_master(doc, row, vin):
	existing = frappe.db.exists("Vehicle Master", {"vin": vin})
	company_currency = frappe.db.get_value("Company", doc.company, "default_currency")
	values = {
		"vin": vin,
		"chassis_number": vin,
		"item_code": row.item_code,
		"item_name": row.item_name,
		"company": doc.company,
		"supplier": doc.supplier,
		"vehicle_import_file": doc.get(CUSTOM_FIELD),
		"purchase_order": row.purchase_order,
		"purchase_receipt": doc.name,
		"purchase_receipt_item": row.name,
		"warehouse": row.warehouse,
		"receipt_date": doc.posting_date,
		"purchase_valuation_rate": flt(row.get("base_net_rate")) or flt(row.get("base_rate")) or flt(row.get("valuation_rate")),
		"cost_currency": company_currency,
		"vehicle_status": "Received",
		"disabled": 0,
	}
	if existing:
		vm = frappe.get_doc("Vehicle Master", existing)
		if vm.item_code != row.item_code:
			frappe.throw(_("VIN {0} already belongs to Item {1}.").format(vin, vm.item_code))
		if vm.vehicle_import_file and vm.vehicle_import_file != doc.get(CUSTOM_FIELD):
			frappe.throw(_("VIN {0} already belongs to another Vehicle Import File.").format(vin))
		if vm.vehicle_status == "Receipt Cancelled":
			values["vehicle_status"] = "Received"
			vm.update(values)
			vm.save(ignore_permissions=True)
		return False
	frappe.get_doc({"doctype": "Vehicle Master", **values}).insert(ignore_permissions=True)
	return True


def on_cancel_purchase_receipt(doc, method=None):
	blocked = []
	for vm in frappe.get_all("Vehicle Master", filters={"purchase_receipt": doc.name}, fields=["name", "vin", "vehicle_status"]):
		if vm.vehicle_status in DOWNSTREAM_STATUSES:
			blocked.append(f"{vm.vin} ({vm.vehicle_status})")
	if blocked:
		frappe.throw(_("Cannot cancel Purchase Receipt because vehicles have downstream status: {0}").format(", ".join(blocked)))
	for name in frappe.get_all("Vehicle Master", filters={"purchase_receipt": doc.name}, pluck="name"):
		vm = frappe.get_doc("Vehicle Master", name)
		vm.vehicle_status = "Receipt Cancelled"
		vm.disabled = 1
		vm.save(ignore_permissions=True)
	if doc.get(CUSTOM_FIELD):
		refresh_import_file(doc.get(CUSTOM_FIELD))


def refresh_import_file(import_file):
	if not import_file:
		return
	vif = frappe.get_doc("Vehicle Import File", import_file)
	vif.refresh_totals(update_status=True)
	vif.save(ignore_permissions=True)


def validate_purchase_invoice(doc, method=None):
	files = {doc.get(CUSTOM_FIELD)} if doc.get(CUSTOM_FIELD) else set()
	for row in doc.items:
		if row.purchase_receipt:
			files.add(frappe.db.get_value("Purchase Receipt", row.purchase_receipt, CUSTOM_FIELD))
		if row.purchase_order:
			files.add(frappe.db.get_value("Purchase Order", row.purchase_order, CUSTOM_FIELD))
	files.discard(None)
	if len(files) > 1:
		frappe.throw(_("Purchase Invoice cannot contain documents from different Vehicle Import Files."))
	if files and not doc.get(CUSTOM_FIELD):
		doc.set(CUSTOM_FIELD, next(iter(files)))
	validate_import_file_for_purchase_doc(doc)


def validate_landed_cost_voucher(doc, method=None):
	files = set()
	for row in doc.get("purchase_receipts", []):
		if row.receipt_document_type == "Purchase Receipt" and row.receipt_document:
			files.add(frappe.db.get_value("Purchase Receipt", row.receipt_document, CUSTOM_FIELD))
	files.discard(None)
	if len(files) > 1:
		frappe.throw(_("Landed Cost Voucher cannot contain Purchase Receipts from different Vehicle Import Files."))
	if files and not doc.get(CUSTOM_FIELD):
		doc.set(CUSTOM_FIELD, next(iter(files)))
	validate_import_file_for_purchase_doc(doc)


def on_landed_cost_change(doc, method=None):
	validate_landed_cost_voucher(doc)
	for row in doc.get("purchase_receipts", []):
		if row.receipt_document_type == "Purchase Receipt" and row.receipt_document:
			for name in frappe.get_all("Vehicle Master", filters={"purchase_receipt": row.receipt_document}, pluck="name"):
				vm = frappe.get_doc("Vehicle Master", name)
				vm.refresh_costs()
				vm.save(ignore_permissions=True)
	if doc.get(CUSTOM_FIELD):
		refresh_import_file(doc.get(CUSTOM_FIELD))


def validate_payment_entry(doc, method=None):
	files = set()
	for row in doc.get("references", []):
		if row.reference_doctype == "Purchase Invoice":
			files.add(frappe.db.get_value("Purchase Invoice", row.reference_name, CUSTOM_FIELD))
		if row.reference_doctype == "Sales Invoice":
			files.add(frappe.db.get_value("Sales Invoice", row.reference_name, CUSTOM_FIELD))
	files.discard(None)
	if len(files) == 1 and not doc.get(CUSTOM_FIELD):
		doc.set(CUSTOM_FIELD, next(iter(files)))
	elif len(files) > 1:
		doc.set(CUSTOM_FIELD, None)


def validate_vehicle_registration(doc, method=None):
	if not (doc.get("custom_vehicle_master") or doc.get("custom_vin") or doc.get(CUSTOM_FIELD)):
		return
	if doc.get("custom_vehicle_master"):
		vm = frappe.get_doc("Vehicle Master", doc.custom_vehicle_master)
		if vm.disabled:
			frappe.throw(_("Cannot register disabled Vehicle Master {0}.").format(vm.name))
		doc.custom_vin = doc.get("custom_vin") or vm.vin
		doc.set(CUSTOM_FIELD, doc.get(CUSTOM_FIELD) or vm.vehicle_import_file)
		doc.chassis_no = doc.chassis_no or vm.chassis_number or vm.vin
		doc.make = doc.make or vm.brand or vm.item_name or vm.item_code
		doc.model = doc.model or vm.model or vm.item_name or vm.item_code
		doc.color = doc.color or vm.color
		doc.company = doc.company or vm.company
	if doc.get("custom_vin"):
		existing = frappe.db.get_value("Vehicle", {"custom_vin": doc.custom_vin, "name": ["!=", doc.name]}, "name")
		if existing and not (frappe.has_role("System Manager") or frappe.has_role("AN Truck Manager")):
			frappe.throw(_("VIN {0} is already registered on Vehicle {1}.").format(doc.custom_vin, existing))


def on_submit_sales_order(doc, method=None):
	for row in doc.get("items", []):
		if row.get("custom_vehicle_master"):
			vm = frappe.get_doc("Vehicle Master", row.custom_vehicle_master)
			if vm.vehicle_status not in {"Received", "Available"}:
				frappe.throw(_("Vehicle {0} is not available for reservation.").format(vm.vin))
			vm.vehicle_status = "Reserved"
			vm.customer = doc.customer
			vm.sales_order = doc.name
			vm.selling_rate = row.rate
			vm.save(ignore_permissions=True)
	if doc.get(CUSTOM_FIELD):
		refresh_import_file(doc.get(CUSTOM_FIELD))


def on_cancel_sales_order(doc, method=None):
	for row in doc.get("items", []):
		if row.get("custom_vehicle_master"):
			vm = frappe.get_doc("Vehicle Master", row.custom_vehicle_master)
			if vm.vehicle_status == "Reserved" and vm.sales_order == doc.name and not (vm.delivery_note or vm.sales_invoice):
				vm.vehicle_status = "Available"
				vm.sales_order = None
				vm.customer = None
				vm.selling_rate = 0
				vm.save(ignore_permissions=True)
	if doc.get(CUSTOM_FIELD):
		refresh_import_file(doc.get(CUSTOM_FIELD))


def on_submit_delivery_note(doc, method=None):
	for row in doc.get("items", []):
		if row.get("custom_vehicle_master"):
			vm = frappe.get_doc("Vehicle Master", row.custom_vehicle_master)
			vm.vehicle_status = "Delivered"
			vm.customer = doc.customer
			vm.delivery_note = doc.name
			vm.save(ignore_permissions=True)
	if doc.get(CUSTOM_FIELD):
		refresh_import_file(doc.get(CUSTOM_FIELD))
	from an_truck.warranty.activation import activate_warranties_from_delivery

	activate_warranties_from_delivery(doc)


def on_cancel_delivery_note(doc, method=None):
	from an_truck.warranty.activation import cancel_warranties_for_source

	cancel_warranties_for_source("Delivery Note", doc.name)
	for row in doc.get("items", []):
		if row.get("custom_vehicle_master"):
			vm = frappe.get_doc("Vehicle Master", row.custom_vehicle_master)
			if vm.delivery_note == doc.name and vm.vehicle_status == "Delivered" and not vm.sales_invoice:
				vm.vehicle_status = "Reserved" if vm.sales_order else "Available"
				vm.delivery_note = None
				vm.save(ignore_permissions=True)
	if doc.get(CUSTOM_FIELD):
		refresh_import_file(doc.get(CUSTOM_FIELD))


def on_submit_sales_invoice(doc, method=None):
	for row in doc.get("items", []):
		if row.get("custom_vehicle_master"):
			vm = frappe.get_doc("Vehicle Master", row.custom_vehicle_master)
			if vm.vehicle_status != "Delivered":
				vm.vehicle_status = "Sold"
			vm.customer = doc.customer
			vm.sales_invoice = doc.name
			vm.selling_rate = row.rate
			vm.save(ignore_permissions=True)
	if doc.get(CUSTOM_FIELD):
		refresh_import_file(doc.get(CUSTOM_FIELD))
	from an_truck.warranty.activation import activate_warranties_from_sales_invoice

	activate_warranties_from_sales_invoice(doc)


def on_cancel_sales_invoice(doc, method=None):
	from an_truck.warranty.activation import cancel_warranties_for_source

	cancel_warranties_for_source("Sales Invoice", doc.name)
	for row in doc.get("items", []):
		if row.get("custom_vehicle_master"):
			vm = frappe.get_doc("Vehicle Master", row.custom_vehicle_master)
			if vm.sales_invoice == doc.name and vm.vehicle_status == "Sold":
				vm.vehicle_status = "Reserved" if vm.sales_order else "Available"
				vm.sales_invoice = None
				vm.save(ignore_permissions=True)
	if doc.get(CUSTOM_FIELD):
		refresh_import_file(doc.get(CUSTOM_FIELD))
