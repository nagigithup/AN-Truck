from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from an_truck.patches.v1_0.create_custom_fields_and_roles import get_custom_fields


def execute():
	create_custom_fields(get_custom_fields(), ignore_validate=True, update=True)
