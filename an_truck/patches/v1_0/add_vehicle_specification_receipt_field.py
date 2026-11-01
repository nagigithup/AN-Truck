import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Purchase Receipt Item": [
				{
					"fieldname": "custom_vehicle_specification_template",
					"label": "Vehicle Specification Template",
					"fieldtype": "Link",
					"options": "Vehicle Specification Template",
					"insert_after": "serial_and_batch_bundle",
				}
			]
		},
		ignore_validate=True,
		update=True,
	)
