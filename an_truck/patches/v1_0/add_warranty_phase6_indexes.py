import frappe


def execute():
	# Supports historical-backfill scans without creating any historical records.
	frappe.db.add_index(
		"Vehicle Master",
		["vehicle_status", "disabled", "company"],
		index_name="vehicle_warranty_backfill_status_company",
	)
