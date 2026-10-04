import frappe


def execute():
	frappe.db.add_index(
		"Vehicle Warranty",
		["company", "status", "warranty_expiry_date"],
		index_name="warranty_company_status_expiry",
	)
	frappe.db.add_index(
		"Warranty Claim",
		["company", "complaint_date", "custom_claim_status"],
		index_name="warranty_claim_company_date_status",
	)
	frappe.db.add_index(
		"Warranty Claim",
		["custom_warranty_provider", "custom_warranty_provider_branch", "complaint_date"],
		index_name="warranty_claim_provider_branch_date",
	)
