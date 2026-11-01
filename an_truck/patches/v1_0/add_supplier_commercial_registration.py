import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	meta = frappe.get_meta("Supplier")
	if any(meta.has_field(field) for field in (
		"commercial_registration_number", "custom_commercial_registration_number"
	)):
		return
	create_custom_fields({"Supplier": [{
		"fieldname": "custom_commercial_registration_number",
		"label": "Commercial Registration Number",
		"fieldtype": "Data",
		"insert_after": "tax_id",
		"translatable": 0,
	}]}, update=True)
