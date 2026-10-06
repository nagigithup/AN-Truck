"""Permission-aware search shared by the portal and its compatibility endpoint."""
import frappe
from frappe import _


@frappe.whitelist()
def search(q, company=None):
	if frappe.session.user == "Guest":
		frappe.throw(_("Not permitted"), frappe.AuthenticationError)
	if not {"AN Truck Portal User", "System Manager"}.intersection(frappe.get_roles()):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if company:
		frappe.get_doc("Company", company).check_permission("read")
	q = (q or "").strip()[:100]
	if len(q) < 2:
		return []
	result = []
	for doctype, fields in (
		("Vehicle Import File", ["name", "import_title"]),
		("Vehicle Master", ["name", "vin", "item_name"]),
		("Supplier", ["name", "supplier_name"]),
		("Customer", ["name", "customer_name"]),
		("Purchase Order", ["name"]), ("Purchase Receipt", ["name"]),
		("Sales Order", ["name"]), ("Sales Invoice", ["name"]),
	):
		if not frappe.db.exists("DocType", doctype) or not frappe.has_permission(doctype, "read"):
			continue
		meta = frappe.get_meta(doctype)
		fields = [f for f in fields if f == "name" or meta.has_field(f)]
		filters = {"company": company} if company and meta.has_field("company") else {}
		result_fields = list(fields)
		if doctype == "Vehicle Master":
			result_fields += ["vehicle_import_file", "vehicle_status"]
		for row in frappe.get_list(doctype, filters=filters, or_filters=[[doctype, f, "like", f"%{q}%"] for f in fields], fields=result_fields, page_length=5):
			result.append({
				"doctype": doctype,
				"name": row.name,
				"label": next((row.get(f) for f in fields[1:] if row.get(f)), row.name),
				"vehicle_import_file": row.get("vehicle_import_file"),
				"status": row.get("vehicle_status"),
			})
	return result[:20]


@frappe.whitelist()
def get_vin_summary(vin):
	"""Return the exact VIN result used by workspace scanner/search flows."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Not permitted"), frappe.AuthenticationError)
	if not {"AN Truck Portal User", "System Manager"}.intersection(frappe.get_roles()):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	vin = (vin or "").strip()[:140]
	if not vin:
		return None
	if not frappe.has_permission("Vehicle Master", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	rows = frappe.get_list(
		"Vehicle Master",
		filters={"vin": vin},
		fields=[
			"name", "vin", "item_code", "item_name", "model", "color", "supplier",
			"vehicle_import_file", "purchase_receipt", "vehicle_status", "warehouse",
			"customer", "sales_order", "sales_invoice", "delivery_note", "disabled",
		],
		limit=1,
	)
	if not rows:
		return None
	row = rows[0]
	return {
		"vin": row.vin,
		"vehicle_master": row.name,
		"vehicle": row.item_name or row.item_code,
		"item_code": row.item_code,
		"model": row.model,
		"color": row.color,
		"import_file": row.vehicle_import_file,
		"supplier": row.supplier,
		"purchase_receipt": row.purchase_receipt,
		"vehicle_master_status": "Disabled" if row.disabled else "Created",
		"receiving_status": "Receipt Cancelled" if row.disabled else "Received" if row.purchase_receipt else "Pending",
		"sale_status": "Delivered" if row.delivery_note else "Sold" if row.sales_invoice else "Reserved" if row.sales_order else "Available",
		"current_location": row.warehouse,
		"vehicle_status": row.vehicle_status,
	}
