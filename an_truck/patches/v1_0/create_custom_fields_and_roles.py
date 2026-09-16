import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


ROLES = (
	"AN Truck Manager",
	"AN Truck Import User",
	"AN Truck Receiving User",
	"AN Truck Viewer",
)


def execute():
	for role in ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc(
				{
					"doctype": "Role",
					"role_name": role,
					"desk_access": 1,
				}
			).insert(ignore_permissions=True)

	create_custom_fields(get_custom_fields(), ignore_validate=True, update=True)


def get_custom_fields():
	field = {
		"fieldname": "custom_vehicle_import_file",
		"label": "Vehicle Import File",
		"fieldtype": "Link",
		"options": "Vehicle Import File",
		"insert_after": "supplier",
		"in_list_view": 1,
		"in_standard_filter": 1,
		"search_index": 1,
		"translatable": 0,
	}
	child_fields = [
		{
			"fieldname": "custom_vehicle_master",
			"label": "Vehicle Master",
			"fieldtype": "Link",
			"options": "Vehicle Master",
			"insert_after": "item_code",
			"in_list_view": 1,
			"in_standard_filter": 1,
			"search_index": 1,
			"translatable": 0,
		},
		{
			"fieldname": "custom_vin",
			"label": "VIN",
			"fieldtype": "Link",
			"options": "Serial No",
			"insert_after": "custom_vehicle_master",
			"in_list_view": 1,
			"in_standard_filter": 1,
			"search_index": 1,
			"translatable": 0,
		},
		{
			"fieldname": "custom_vehicle_import_file",
			"label": "Vehicle Import File",
			"fieldtype": "Link",
			"options": "Vehicle Import File",
			"insert_after": "custom_vin",
			"in_standard_filter": 1,
			"search_index": 1,
			"translatable": 0,
		},
	]
	vehicle_fields = [
		{
			"fieldname": "custom_vehicle_import_file",
			"label": "Vehicle Import File",
			"fieldtype": "Link",
			"options": "Vehicle Import File",
			"insert_after": "company",
			"in_list_view": 1,
			"in_standard_filter": 1,
			"search_index": 1,
			"translatable": 0,
		},
		{
			"fieldname": "custom_vehicle_master",
			"label": "Vehicle Master",
			"fieldtype": "Link",
			"options": "Vehicle Master",
			"insert_after": "custom_vehicle_import_file",
			"in_list_view": 1,
			"in_standard_filter": 1,
			"search_index": 1,
			"translatable": 0,
		},
		{
			"fieldname": "custom_vin",
			"label": "VIN",
			"fieldtype": "Link",
			"options": "Serial No",
			"insert_after": "custom_vehicle_master",
			"in_list_view": 1,
			"in_standard_filter": 1,
			"search_index": 1,
			"translatable": 0,
		},
		{
			"fieldname": "custom_registration_status",
			"label": "Registration Status",
			"fieldtype": "Select",
			"options": "\nAwaiting Registration\nRegistered\nCorrection Required\nCancelled",
			"insert_after": "custom_vin",
			"in_list_view": 1,
			"in_standard_filter": 1,
			"translatable": 0,
		},
	]
	return {
		"Purchase Order": [field],
		"Purchase Receipt": [{**field, "insert_after": "supplier"}],
		"Purchase Invoice": [{**field, "insert_after": "supplier"}],
		"Landed Cost Voucher": [{**field, "insert_after": "company"}],
		"Payment Entry": [{**field, "insert_after": "party"}],
		"Quotation": [{**field, "insert_after": "party_name"}],
		"Sales Order": [{**field, "insert_after": "customer"}],
		"Delivery Note": [{**field, "insert_after": "customer"}],
		"Sales Invoice": [{**field, "insert_after": "customer"}],
		"Quotation Item": child_fields,
		"Sales Order Item": child_fields,
		"Delivery Note Item": child_fields,
		"Sales Invoice Item": child_fields,
		"Vehicle": vehicle_fields,
	}
