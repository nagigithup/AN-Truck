import frappe


def execute():
	frappe.db.add_index(
		"Vehicle Master", ["specification_template", "company", "vehicle_status"],
		"vehicle_template_company_status",
	)
	frappe.db.add_unique(
		"Vehicle Specification Template", ["template_name", "revision"],
		"unique_vehicle_specification_revision",
	)
