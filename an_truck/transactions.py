import json
import uuid

import frappe
from frappe import _
from frappe.utils import cint, flt, nowdate, nowtime

from an_truck.services import CUSTOM_FIELD, get_vehicle_rows, is_vehicle_item, refresh_import_file


def _dict(data):
	if isinstance(data, str):
		data = json.loads(data or "{}")
	return frappe._dict(data or {})


def _require_import_file(name, permtype="read"):
	if not name:
		frappe.throw(_("Vehicle Import File is required."))
	if not frappe.has_permission("Vehicle Import File", permtype, name):
		frappe.throw(_("Not permitted for Vehicle Import File {0}.").format(name), frappe.PermissionError)
	return frappe.get_doc("Vehicle Import File", name)


def _require_create(doctype):
	if not frappe.has_permission(doctype, "create"):
		frappe.throw(_("Not permitted to create {0}.").format(_(doctype)), frappe.PermissionError)


def _finish(doc, submit_now=False, import_file=None):
	doc.insert()
	if cint(submit_now):
		doc.submit()
	if import_file:
		refresh_import_file(import_file)
	return {"doctype": doc.doctype, "name": doc.name, "docstatus": doc.docstatus, "status": doc.get("status")}


def _with_idempotency(action, import_file, key, factory):
	if not key:
		key = str(uuid.uuid4())
	cache_key = f"an_truck:{action}:{import_file}:{key}"
	existing = frappe.cache().get_value(cache_key)
	if existing:
		return existing
	result = factory()
	frappe.cache().set_value(cache_key, result, expires_in_sec=60 * 60)
	return result


def _set_if_present(doc, values):
	for fieldname, value in values.items():
		if value is not None and fieldname in doc.meta.get_fieldnames():
			doc.set(fieldname, value)


def _assert_import_doc(doctype, name, import_file, submitted=True):
	doc = frappe.get_doc(doctype, name)
	if submitted and doc.docstatus != 1:
		frappe.throw(_("{0} {1} must be submitted.").format(_(doctype), name))
	if doc.get(CUSTOM_FIELD) != import_file:
		frappe.throw(_("{0} {1} is not linked to Vehicle Import File {2}.").format(_(doctype), name, import_file))
	return doc


@frappe.whitelist()
def get_unified_screen_data(vehicle_import_file):
	vif = _require_import_file(vehicle_import_file)
	return {
		"summary": _get_summary(vif),
		"documents": _get_documents(vif.name),
		"vehicles": _get_vehicles(vif.name),
		"permissions": _get_permissions(),
	}


def _get_permissions():
	doctypes = [
		"Purchase Order",
		"Purchase Receipt",
		"Purchase Invoice",
		"Payment Entry",
		"Landed Cost Voucher",
		"Quotation",
		"Sales Order",
		"Delivery Note",
		"Sales Invoice",
		"Vehicle Master",
	]
	return {doctype: {"create": frappe.has_permission(doctype, "create"), "read": frappe.has_permission(doctype, "read")} for doctype in doctypes}


def _get_summary(vif):
	return {
		"status": vif.status,
		"expected": vif.total_expected_vehicles,
		"received": vif.total_received_vehicles,
		"remaining": vif.total_remaining_vehicles,
		"created": vif.total_created_vehicles,
		"currency": vif.company_currency,
		"contract_amount": vif.total_contract_amount_company_currency,
	}


def _get_documents(import_file):
	def rows(doctype, filters=None, fields=None):
		filters = filters or {}
		filters[CUSTOM_FIELD] = import_file
		return frappe.get_all(doctype, filters=filters, fields=fields, order_by="modified desc", limit=50)

	common_purchase = ["name", "transaction_date as date", "supplier as party", "currency", "grand_total as amount", "status", "docstatus"]
	common_stock = ["name", "posting_date as date", "supplier as party", "currency", "grand_total as amount", "status", "docstatus"]
	common_sales = ["name", "transaction_date as date", "customer as party", "currency", "grand_total as amount", "status", "docstatus"]
	quotation_fields = ["name", "transaction_date as date", "party_name as party", "currency", "grand_total as amount", "status", "docstatus"]
	return {
		"purchase_orders": rows("Purchase Order", fields=common_purchase + ["per_received", "per_billed"]),
		"purchase_receipts": rows("Purchase Receipt", fields=common_stock),
		"purchase_invoices": rows("Purchase Invoice", fields=["name", "posting_date as date", "supplier as party", "currency", "grand_total as amount", "outstanding_amount", "status", "docstatus"]),
		"supplier_payments": rows("Payment Entry", {"payment_type": "Pay"}, ["name", "posting_date as date", "party", "paid_from_account_currency as currency", "paid_amount as amount", "status", "docstatus"]),
		"landed_cost_vouchers": rows("Landed Cost Voucher", fields=["name", "posting_date as date", "company as party", "total_taxes_and_charges as amount", "docstatus"]),
		"quotations": rows("Quotation", fields=quotation_fields),
		"sales_orders": rows("Sales Order", fields=common_sales + ["per_delivered", "per_billed"]),
		"delivery_notes": rows("Delivery Note", fields=["name", "posting_date as date", "customer as party", "currency", "grand_total as amount", "status", "docstatus"]),
		"sales_invoices": rows("Sales Invoice", fields=["name", "posting_date as date", "customer as party", "currency", "grand_total as amount", "outstanding_amount", "status", "docstatus"]),
		"customer_payments": rows("Payment Entry", {"payment_type": "Receive"}, ["name", "posting_date as date", "party", "paid_to_account_currency as currency", "received_amount as amount", "status", "docstatus"]),
	}


def _get_vehicles(import_file):
	return frappe.get_all(
		"Vehicle Master",
		filters={"vehicle_import_file": import_file},
		fields=[
			"name",
			"vin",
			"item_code",
			"item_name",
			"brand",
			"model",
			"model_year",
			"color",
			"warehouse",
			"vehicle_status",
			"final_valuation_rate",
			"selling_rate",
			"customer",
		],
		order_by="modified desc",
		limit=200,
	)


@frappe.whitelist()
def get_purchase_order_items(purchase_order, vehicle_import_file):
	po = _assert_import_doc("Purchase Order", purchase_order, vehicle_import_file)
	rows = []
	for row in po.items:
		remaining = flt(row.qty) - flt(row.received_qty)
		if remaining > 0:
			rows.append(
				{
					"purchase_order_item": row.name,
					"item_code": row.item_code,
					"item_name": row.item_name,
					"description": row.description,
					"ordered_qty": row.qty,
					"received_qty": row.received_qty,
					"remaining_qty": remaining,
					"qty": remaining,
					"uom": row.uom,
					"rate": row.rate,
					"warehouse": row.warehouse,
					"is_vehicle_item": is_vehicle_item(row.item_code),
				}
			)
	return rows


@frappe.whitelist()
def create_purchase_order(vehicle_import_file, data=None, submit_now=0, idempotency_key=None):
	vif = _require_import_file(vehicle_import_file)
	_require_create("Purchase Order")
	data = _dict(data)

	def make():
		doc = frappe.new_doc("Purchase Order")
		doc.company = vif.company
		doc.supplier = vif.supplier
		doc.currency = vif.supplier_currency
		doc.schedule_date = data.get("required_by_date") or nowdate()
		doc.transaction_date = nowdate()
		doc.set(CUSTOM_FIELD, vif.name)
		_set_if_present(
			doc,
			{
				"supplier_quotation_no": data.get("supplier_quotation_number"),
				"supplier_quotation_date": data.get("supplier_quotation_date"),
				"taxes_and_charges": data.get("taxes_template"),
				"remarks": data.get("notes"),
			},
		)
		for item in data.get("items") or []:
			item = _dict(item)
			qty = flt(item.qty)
			rate = flt(item.rate)
			if not item.item_code or qty <= 0:
				frappe.throw(_("Each Purchase Order row must have Item Code and positive Quantity."))
			doc.append(
				"items",
				{
					"item_code": item.item_code,
					"item_name": item.get("item_name"),
					"description": item.get("description"),
					"qty": qty,
					"uom": item.get("uom"),
					"rate": rate,
					"amount": qty * rate,
					"schedule_date": item.get("schedule_date") or data.get("required_by_date") or nowdate(),
					"warehouse": item.get("warehouse"),
				},
			)
		return _finish(doc, submit_now, vif.name)

	return _with_idempotency("po", vif.name, idempotency_key, make)


@frappe.whitelist()
def create_purchase_receipt(vehicle_import_file, data=None, submit_now=0, idempotency_key=None):
	from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt

	vif = _require_import_file(vehicle_import_file)
	_require_create("Purchase Receipt")
	data = _dict(data)
	po = _assert_import_doc("Purchase Order", data.purchase_order, vif.name)

	def make():
		doc = make_purchase_receipt(po.name)
		doc.set(CUSTOM_FIELD, vif.name)
		doc.posting_date = data.get("posting_date") or nowdate()
		doc.posting_time = data.get("posting_time") or nowtime()
		item_map = {row.get("purchase_order_item") or row.get("item_code"): _dict(row) for row in data.get("items") or []}
		vin_map = {}
		for row in data.get("vins") or []:
			row = _dict(row)
			if not row.vin:
				frappe.throw(_("VIN is required."))
			vin_map.setdefault(row.item_code, []).append(row)
		for row in list(doc.items):
			source = item_map.get(row.purchase_order_item) or item_map.get(row.item_code)
			if not source:
				doc.remove(row)
				continue
			row.qty = flt(source.qty)
			row.warehouse = source.get("warehouse") or row.warehouse
			if is_vehicle_item(row.item_code):
				if not cint(frappe.db.get_value("Item", row.item_code, "has_serial_no")):
					frappe.throw(_("Item {0} must be serialized before receiving vehicles.").format(row.item_code))
				vins = [v.vin for v in vin_map.get(row.item_code, [])]
				if len(vins) != cint(row.qty):
					frappe.throw(_("VIN count must equal quantity for Item {0}.").format(row.item_code))
				_validate_new_vins(vins)
				row.serial_no = "\n".join(vins)
		if not doc.items:
			frappe.throw(_("No receivable items selected."))
		return _finish(doc, submit_now, vif.name)

	return _with_idempotency("pr", vif.name, idempotency_key, make)


def _validate_new_vins(vins):
	seen = set()
	for vin in vins:
		if vin in seen:
			frappe.throw(_("Duplicate VIN {0}.").format(vin))
		seen.add(vin)
		if frappe.db.exists("Serial No", vin) or frappe.db.exists("Vehicle Master", {"vin": vin}):
			frappe.throw(_("VIN {0} already exists.").format(vin))


@frappe.whitelist()
def create_purchase_invoice(vehicle_import_file, data=None, submit_now=0, idempotency_key=None):
	vif = _require_import_file(vehicle_import_file)
	_require_create("Purchase Invoice")
	data = _dict(data)
	source_type = data.get("source_type")
	source_name = data.get("source_name")

	def make():
		if source_type == "Purchase Receipt":
			from erpnext.stock.doctype.purchase_receipt.purchase_receipt import make_purchase_invoice
		elif source_type == "Purchase Order":
			from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_invoice
		else:
			frappe.throw(_("Select Purchase Order or Purchase Receipt as source."))
		_assert_import_doc(source_type, source_name, vif.name)
		doc = make_purchase_invoice(source_name)
		doc.set(CUSTOM_FIELD, vif.name)
		doc.bill_no = data.get("supplier_invoice_number")
		doc.bill_date = data.get("supplier_invoice_date")
		doc.posting_date = data.get("posting_date") or nowdate()
		doc.due_date = data.get("due_date")
		_set_if_present(doc, {"conversion_rate": data.get("exchange_rate"), "taxes_and_charges": data.get("taxes_template"), "remarks": data.get("remarks")})
		return _finish(doc, submit_now, vif.name)

	return _with_idempotency("pi", vif.name, idempotency_key, make)


@frappe.whitelist()
def create_payment_entry(vehicle_import_file, data=None, submit_now=0, idempotency_key=None):
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	vif = _require_import_file(vehicle_import_file)
	_require_create("Payment Entry")
	data = _dict(data)
	reference_doctype = data.reference_doctype
	if reference_doctype not in {"Purchase Invoice", "Sales Invoice"}:
		frappe.throw(_("Payment source must be Purchase Invoice or Sales Invoice."))
	_assert_import_doc(reference_doctype, data.reference_name, vif.name)

	def make():
		doc = get_payment_entry(reference_doctype, data.reference_name, bank_amount=flt(data.get("paid_amount")) or None)
		doc.set(CUSTOM_FIELD, vif.name)
		doc.posting_date = data.get("posting_date") or nowdate()
		_set_if_present(
			doc,
			{
				"paid_from": data.get("paid_from_account"),
				"paid_to": data.get("paid_to_account") or data.get("received_to_account"),
				"mode_of_payment": data.get("mode_of_payment"),
				"reference_no": data.get("reference_number"),
				"reference_date": data.get("reference_date"),
				"remarks": data.get("remarks"),
			},
		)
		if flt(data.get("paid_amount")):
			doc.paid_amount = flt(data.paid_amount)
			doc.received_amount = flt(data.paid_amount)
		return _finish(doc, submit_now, vif.name)

	return _with_idempotency("pe", vif.name, idempotency_key, make)


@frappe.whitelist()
def create_landed_cost_voucher(vehicle_import_file, data=None, submit_now=0, idempotency_key=None):
	vif = _require_import_file(vehicle_import_file)
	_require_create("Landed Cost Voucher")
	data = _dict(data)

	def make():
		doc = frappe.new_doc("Landed Cost Voucher")
		doc.company = vif.company
		doc.posting_date = data.get("posting_date") or nowdate()
		doc.distribute_charges_based_on = data.get("allocation_basis") or "Qty"
		doc.set(CUSTOM_FIELD, vif.name)
		for receipt in data.get("purchase_receipts") or []:
			receipt = _dict(receipt)
			_assert_import_doc("Purchase Receipt", receipt.receipt_document, vif.name)
			doc.append("purchase_receipts", {"receipt_document_type": "Purchase Receipt", "receipt_document": receipt.receipt_document})
		for tax in data.get("taxes") or []:
			tax = _dict(tax)
			doc.append("taxes", {"description": tax.description, "expense_account": tax.expense_account, "amount": flt(tax.amount), "account_currency": tax.get("currency"), "exchange_rate": flt(tax.get("exchange_rate")) or 1})
		if not doc.purchase_receipts or not doc.taxes:
			frappe.throw(_("Select at least one Purchase Receipt and one landed cost row."))
		doc.get_items_from_purchase_receipts()
		return _finish(doc, submit_now, vif.name)

	return _with_idempotency("lcv", vif.name, idempotency_key, make)


@frappe.whitelist()
def create_customer_quotation(vehicle_import_file, data=None, submit_now=0, idempotency_key=None):
	return _create_selling_document("Quotation", vehicle_import_file, data, submit_now, idempotency_key)


@frappe.whitelist()
def create_sales_order(vehicle_import_file, data=None, submit_now=0, idempotency_key=None):
	return _create_selling_document("Sales Order", vehicle_import_file, data, submit_now, idempotency_key)


def _create_selling_document(doctype, vehicle_import_file, data=None, submit_now=0, idempotency_key=None):
	vif = _require_import_file(vehicle_import_file)
	_require_create(doctype)
	data = _dict(data)

	def make():
		doc = frappe.new_doc(doctype)
		doc.company = vif.company
		doc.customer = data.customer
		doc.currency = data.get("currency") or frappe.db.get_value("Company", vif.company, "default_currency")
		doc.conversion_rate = flt(data.get("exchange_rate")) or 1
		doc.selling_price_list = data.get("price_list") or frappe.db.get_single_value("Selling Settings", "selling_price_list")
		doc.transaction_date = data.get("transaction_date") or nowdate()
		if doctype == "Sales Order":
			doc.order_type = data.get("order_type") or "Sales"
			doc.delivery_date = data.get("delivery_date") or nowdate()
		doc.set(CUSTOM_FIELD, vif.name)
		for item in _vehicle_items_for_sale(vif.name, data.get("vehicles") or []):
			doc.append(
				"items",
				{
					"item_code": item.item_code,
					"item_name": item.item_name,
					"qty": 1,
					"rate": flt(item.get("selling_rate")) or flt(item.get("rate")) or flt(item.final_valuation_rate),
					"warehouse": item.warehouse,
					"delivery_date": data.get("delivery_date") or nowdate(),
					"custom_vehicle_master": item.name,
					"custom_vin": item.vin,
					"custom_vehicle_import_file": vif.name,
				},
			)
		if not doc.items:
			frappe.throw(_("Select at least one available vehicle."))
		result = _finish(doc, submit_now, vif.name)
		if doctype == "Quotation":
			_update_vehicle_refs(doc, "quotation")
		return result

	return _with_idempotency(doctype.lower().replace(" ", "_"), vif.name, idempotency_key, make)


def _vehicle_items_for_sale(import_file, vehicles):
	names = [v.get("vehicle_master") or v.get("name") for v in map(_dict, vehicles)]
	names = [name for name in names if name]
	if not names:
		return []
	result = []
	for vm in frappe.get_all("Vehicle Master", filters={"name": ["in", names], "vehicle_import_file": import_file}, fields=["*"]):
		if vm.vehicle_status not in {"Received", "Available"}:
			frappe.throw(_("Vehicle {0} is not available for sale.").format(vm.vin))
		result.append(vm)
	return result


def _update_vehicle_refs(doc, fieldname):
	for row in doc.items:
		if row.get("custom_vehicle_master"):
			frappe.db.set_value("Vehicle Master", row.custom_vehicle_master, fieldname, doc.name, update_modified=False)


@frappe.whitelist()
def create_delivery_note(vehicle_import_file, data=None, submit_now=0, idempotency_key=None):
	from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note

	vif = _require_import_file(vehicle_import_file)
	_require_create("Delivery Note")
	data = _dict(data)
	so = _assert_import_doc("Sales Order", data.sales_order, vif.name)

	def make():
		doc = make_delivery_note(so.name)
		doc.set(CUSTOM_FIELD, vif.name)
		doc.posting_date = data.get("posting_date") or nowdate()
		doc.posting_time = data.get("posting_time") or nowtime()
		selected = {v.get("vehicle_master") or v.get("name") for v in map(_dict, data.get("vehicles") or [])}
		for row in list(doc.items):
			if row.get("custom_vehicle_master") and selected and row.custom_vehicle_master not in selected:
				doc.remove(row)
				continue
			if row.get("custom_vin"):
				row.serial_no = row.custom_vin
			if data.get("source_warehouse"):
				row.warehouse = data.source_warehouse
		if not doc.items:
			frappe.throw(_("Select at least one vehicle to deliver."))
		return _finish(doc, submit_now, vif.name)

	return _with_idempotency("dn", vif.name, idempotency_key, make)


@frappe.whitelist()
def create_sales_invoice(vehicle_import_file, data=None, submit_now=0, idempotency_key=None):
	vif = _require_import_file(vehicle_import_file)
	_require_create("Sales Invoice")
	data = _dict(data)
	source_type = data.source_type
	source_name = data.source_name

	def make():
		if source_type == "Delivery Note":
			from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice
		elif source_type == "Sales Order":
			from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
		else:
			frappe.throw(_("Select Sales Order or Delivery Note as source."))
		_assert_import_doc(source_type, source_name, vif.name)
		doc = make_sales_invoice(source_name)
		doc.set(CUSTOM_FIELD, vif.name)
		doc.posting_date = data.get("posting_date") or nowdate()
		doc.due_date = data.get("due_date")
		_set_if_present(doc, {"conversion_rate": data.get("exchange_rate"), "taxes_and_charges": data.get("taxes_template"), "remarks": data.get("remarks")})
		return _finish(doc, submit_now, vif.name)

	return _with_idempotency("si", vif.name, idempotency_key, make)


@frappe.whitelist()
def complete_vehicle_information(vehicle_import_file, data=None):
	vif = _require_import_file(vehicle_import_file, "write")
	data = _dict(data)
	for row in data.get("vehicles") or []:
		row = _dict(row)
		vm = frappe.get_doc("Vehicle Master", row.name)
		if vm.vehicle_import_file != vif.name:
			frappe.throw(_("Vehicle {0} is not linked to this import file.").format(vm.name))
		for fieldname in ("brand", "model", "model_year", "color", "engine_number", "notes"):
			if fieldname in row:
				vm.set(fieldname, row.get(fieldname))
		vm.save()
	return {"updated": len(data.get("vehicles") or [])}


@frappe.whitelist()
def start_vehicle_inspection(vehicle_import_file, data=None):
	vif = _require_import_file(vehicle_import_file, "write")
	data = _dict(data)
	names = [v.get("vehicle_master") or v.get("name") for v in map(_dict, data.get("vehicles") or [])]
	for name in names:
		vm = frappe.get_doc("Vehicle Master", name)
		if vm.vehicle_import_file != vif.name:
			frappe.throw(_("Vehicle {0} is not linked to this import file.").format(vm.name))
		if vm.vehicle_status in {"Received", "Available"}:
			vm.vehicle_status = "Under Inspection"
			vm.save()
	refresh_import_file(vif.name)
	return {"updated": len(names)}
