import frappe


def execute():
	# Exact provider-scoped VIN lookup, including historical warranties.
	frappe.db.add_index(
		"Vehicle Warranty",
		["vin", "warranty_provider", "warranty_start_date"],
		index_name="warranty_vin_provider_start",
	)
	# Portal list ordering and dashboard status aggregation at claim-scale.
	frappe.db.add_index(
		"Warranty Claim",
		["custom_warranty_provider", "custom_warranty_provider_branch", "modified"],
		index_name="warranty_claim_provider_branch_modified",
	)
	frappe.db.add_index(
		"Warranty Claim",
		["company", "custom_claim_status"],
		index_name="warranty_claim_company_status",
	)
