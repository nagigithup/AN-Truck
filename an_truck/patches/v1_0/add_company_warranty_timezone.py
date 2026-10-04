import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Company": [
				{
					"fieldname": "custom_warranty_timezone",
					"label": "Warranty Processing Time Zone",
					"fieldtype": "Data",
					"description": "IANA time zone used for date-based vehicle warranty processing, for example Asia/Riyadh.",
					"insert_after": "country",
				},
			]
		},
		update=True,
	)

	# Seed configuration, not business logic: Saudi companies which actually own
	# Vehicle Master records are configured without relying on a company name.
	companies = frappe.get_all(
		"Vehicle Master",
		filters={"company": ["is", "set"]},
		pluck="company",
		distinct=True,
	)
	for company in companies:
		if (
			frappe.db.get_value("Company", company, "country") == "Saudi Arabia"
			and not frappe.db.get_value("Company", company, "custom_warranty_timezone")
		):
			frappe.db.set_value(
				"Company", company, "custom_warranty_timezone", "Asia/Riyadh", update_modified=False
			)
