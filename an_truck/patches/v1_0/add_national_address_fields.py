import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	meta = frappe.get_meta("Address")
	fields = [
		{
			"fieldname": "custom_area",
			"label": "Area/District",
			"fieldtype": "Data",
			"insert_after": "city",
			"translatable": 0,
		},
		{
			"fieldname": "custom_building_number",
			"label": "Building Number",
			"fieldtype": "Data",
			"insert_after": "address_line1",
			"translatable": 0,
		},
		{
			"fieldname": "custom_additional_number",
			"label": "Additional Number",
			"fieldtype": "Data",
			"insert_after": "custom_building_number",
			"translatable": 0,
		},
		{
			"fieldname": "custom_short_address",
			"label": "Short Address",
			"fieldtype": "Data",
			"insert_after": "custom_additional_number",
			"translatable": 0,
		},
	]
	create_custom_fields(
		{"Address": [field for field in fields if not meta.has_field(field["fieldname"])]},
		ignore_validate=True,
		update=True,
	)
