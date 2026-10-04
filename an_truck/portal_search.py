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
		for row in frappe.get_list(doctype, filters=filters, or_filters=[[doctype, f, "like", f"%{q}%"] for f in fields], fields=fields, page_length=5):
			result.append({"doctype": doctype, "name": row.name, "label": next((row.get(f) for f in fields[1:] if row.get(f)), row.name)})
	return result[:20]
