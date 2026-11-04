import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields({
		"AN Truck Settings": [{"fieldname": "voucher_company", "fieldtype": "Link", "options": "Company",
			"label": "Financial Voucher Company", "insert_after": "vehicle_item_group"}],
		"Payment Entry": [
			{"fieldname": "custom_portal_voucher_request", "fieldtype": "Data", "label": "Portal Voucher Request",
			 "hidden": 1, "read_only": 1, "no_copy": 1, "unique": 1, "print_hide": 1},
			{"fieldname": "custom_portal_voucher_payload", "fieldtype": "Data", "label": "Portal Voucher Payload",
			 "hidden": 1, "read_only": 1, "no_copy": 1, "print_hide": 1},
		],
	}, update=True)
	if not frappe.db.get_single_value("AN Truck Settings", "voucher_company"):
		companies = frappe.get_all("Vehicle Master", filters={"company": ["is", "set"]},
			fields=["company"], group_by="company", limit=2)
		if len(companies) == 1 and companies[0].company == frappe.defaults.get_global_default("company"):
			frappe.db.set_single_value("AN Truck Settings", "voucher_company", companies[0].company)
	_setup_roles()
	from pathlib import Path
	if not frappe.db.exists("Print Format", "AN Truck Voucher"):
		frappe.get_doc({"doctype": "Print Format", "name": "AN Truck Voucher", "module": "AN Truck",
			"doc_type": "Payment Entry", "standard": "No", "custom_format": 1, "print_format_type": "Jinja",
			"pdf_generator": "chrome", "html": Path(frappe.get_app_path("an_truck", "print_formats", "an_truck_voucher.html")).read_text()}).insert()


def _setup_roles():
	from frappe.permissions import add_permission, update_permission_property
	from an_truck.voucher_permissions import VIEWER, CREATOR
	for role in (VIEWER, CREATOR):
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert()
		grants = {"Payment Entry": ["read", "print"], "Company": ["read"], "Address": ["read"], "Contact": ["read"]}
		if role == CREATOR:
			grants["Payment Entry"] += ["create", "write"]
			grants.update({dt: ["read"] for dt in ("Account", "Customer", "Supplier", "Mode of Payment", "Sales Invoice", "Purchase Invoice")})
		for doctype, permissions in grants.items():
			if frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0}):
				continue
			# The supported API first copies all existing grants unchanged.
			add_permission(doctype, role)
			for permission in permissions:
				update_permission_property(doctype, role, 0, permission, 1)
