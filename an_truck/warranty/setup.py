import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


INTERNAL_MANAGER = "AN Truck Warranty Manager"
INTERNAL_USER = "AN Truck Warranty User"
PROVIDER_USER = "AN Truck Warranty Provider User"


def execute():
	create_roles()
	create_custom_fields(get_custom_fields(), ignore_validate=True, update=True)
	configure_warranty_claim_permissions()
	create_workflow()
	frappe.clear_cache()


def create_roles():
	for role, desk_access in ((INTERNAL_MANAGER, 1), (INTERNAL_USER, 1), (PROVIDER_USER, 0)):
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": desk_access}).insert(ignore_permissions=True)


def get_custom_fields():
	return {
		"Item": [
			{"fieldname": "custom_warranty_section", "label": "Vehicle Warranty", "fieldtype": "Section Break", "insert_after": "warranty_period", "collapsible": 1},
			{"fieldname": "custom_warranty_coverage_template", "label": "Warranty Coverage Template", "fieldtype": "Link", "options": "Warranty Coverage Template", "insert_after": "custom_warranty_section"},
			{"fieldname": "custom_warranty_provider", "label": "Warranty Provider", "fieldtype": "Link", "options": "Warranty Provider", "insert_after": "custom_warranty_coverage_template"},
		],
		"Warranty Claim": claim_custom_fields(),
	}


def claim_custom_fields():
	return [
		{"fieldname":"custom_claim_status","label":"Warranty Claim Status","fieldtype":"Select","options":"Draft\nSubmitted by Provider\nUnder Internal Review\nNeed More Information\nApproved\nPartially Approved\nRejected\nRepair In Progress\nRepair Completed\nFinal Documents Submitted\nClosed","default":"Draft","insert_after":"status","in_list_view":1,"in_standard_filter":1,"search_index":1},
		{"fieldname":"custom_vehicle_warranty_section","label":"Vehicle Warranty","fieldtype":"Section Break","insert_after":"section_break_7"},
		{"fieldname":"custom_vehicle_warranty","label":"Vehicle Warranty","fieldtype":"Link","options":"Vehicle Warranty","insert_after":"custom_vehicle_warranty_section","reqd":1,"in_list_view":1,"in_standard_filter":1,"search_index":1},
		{"fieldname":"custom_vehicle_master","label":"Vehicle Master","fieldtype":"Link","options":"Vehicle Master","insert_after":"custom_vehicle_warranty","read_only":1,"in_standard_filter":1},
		{"fieldname":"custom_warranty_provider","label":"Warranty Provider","fieldtype":"Link","options":"Warranty Provider","insert_after":"custom_vehicle_master","read_only":1,"in_list_view":1,"in_standard_filter":1,"search_index":1},
		{"fieldname":"custom_warranty_provider_branch","label":"Warranty Provider Branch","fieldtype":"Link","options":"Warranty Provider Branch","insert_after":"custom_warranty_provider","in_list_view":1,"in_standard_filter":1,"search_index":1},
		{"fieldname":"custom_current_odometer","label":"Current Mileage / Odometer","fieldtype":"Float","insert_after":"custom_warranty_provider_branch","non_negative":1},
		{"fieldname":"custom_failure_date","label":"Failure Date","fieldtype":"Date","insert_after":"custom_current_odometer"},
		{"fieldname":"custom_inspection_section","label":"Inspection and Diagnosis","fieldtype":"Section Break","insert_after":"description"},
		{"fieldname":"custom_inspection_date","label":"Inspection Date","fieldtype":"Date","insert_after":"custom_inspection_section"},
		{"fieldname":"custom_technician_name","label":"Technician Name","fieldtype":"Data","insert_after":"custom_inspection_date"},
		{"fieldname":"custom_diagnosis","label":"Diagnosis","fieldtype":"Text Editor","insert_after":"custom_technician_name"},
		{"fieldname":"custom_inspection_details","label":"Inspection Details","fieldtype":"Text Editor","insert_after":"custom_diagnosis"},
		{"fieldname":"custom_root_cause","label":"Root Cause","fieldtype":"Small Text","insert_after":"custom_inspection_details"},
		{"fieldname":"custom_provider_assessment_section","label":"Provider Assessment","fieldtype":"Section Break","insert_after":"custom_root_cause"},
		{"fieldname":"custom_provider_recommendation","label":"Provider Recommendation","fieldtype":"Select","options":"\nCovered\nPartially Covered\nNot Covered\nRequires Company Review","insert_after":"custom_provider_assessment_section","in_standard_filter":1},
		{"fieldname":"custom_provider_reason","label":"Reason","fieldtype":"Small Text","insert_after":"custom_provider_recommendation"},
		{"fieldname":"custom_provider_technical_notes","label":"Technical Notes","fieldtype":"Text Editor","insert_after":"custom_provider_reason"},
		{"fieldname":"custom_internal_approval_section","label":"Internal Company Approval","fieldtype":"Section Break","insert_after":"custom_provider_technical_notes","permlevel":1},
		{"fieldname":"custom_internal_decision","label":"Internal Decision","fieldtype":"Select","options":"\nApproved\nPartially Approved\nRejected\nNeed More Information","insert_after":"custom_internal_approval_section","permlevel":1,"in_standard_filter":1},
		{"fieldname":"custom_internal_decision_reason","label":"Decision Reason","fieldtype":"Small Text","insert_after":"custom_internal_decision","permlevel":1},
		{"fieldname":"custom_internal_notes","label":"Confidential Internal Notes","fieldtype":"Text Editor","insert_after":"custom_internal_decision_reason","permlevel":1},
		{"fieldname":"custom_approved_by","label":"Approved / Decided By","fieldtype":"Link","options":"User","insert_after":"custom_internal_notes","read_only":1,"permlevel":1},
		{"fieldname":"custom_approval_date","label":"Approval Date","fieldtype":"Datetime","insert_after":"custom_approved_by","read_only":1,"permlevel":1},
		{"fieldname":"custom_approved_provider_claim_amount","label":"Approved Provider Claim Amount","fieldtype":"Currency","options":"custom_currency","insert_after":"custom_approval_date","permlevel":1,"non_negative":1},
		{"fieldname":"custom_cost_section","label":"Parts, Services and Cost Summary","fieldtype":"Section Break","insert_after":"custom_approved_provider_claim_amount"},
		{"fieldname":"custom_currency","label":"Currency","fieldtype":"Link","options":"Currency","insert_after":"custom_cost_section","read_only":1},
		{"fieldname":"custom_parts","label":"Spare Parts","fieldtype":"Table","options":"Warranty Claim Part","insert_after":"custom_currency"},
		{"fieldname":"custom_services","label":"Labor / Services","fieldtype":"Table","options":"Warranty Claim Service","insert_after":"custom_parts"},
		{"fieldname":"custom_other_charges","label":"Other Charges","fieldtype":"Currency","options":"custom_currency","insert_after":"custom_services","non_negative":1},
		{"fieldname":"custom_other_covered_amount","label":"Other Charges Covered","fieldtype":"Currency","options":"custom_currency","insert_after":"custom_other_charges","non_negative":1},
		{"fieldname":"custom_parts_inside_warranty","label":"Parts Inside Warranty","fieldtype":"Currency","options":"custom_currency","insert_after":"custom_other_covered_amount","read_only":1},
		{"fieldname":"custom_parts_outside_warranty","label":"Parts Outside Warranty","fieldtype":"Currency","options":"custom_currency","insert_after":"custom_parts_inside_warranty","read_only":1},
		{"fieldname":"custom_labor_inside_warranty","label":"Labor Inside Warranty","fieldtype":"Currency","options":"custom_currency","insert_after":"custom_parts_outside_warranty","read_only":1},
		{"fieldname":"custom_labor_outside_warranty","label":"Labor Outside Warranty","fieldtype":"Currency","options":"custom_currency","insert_after":"custom_labor_inside_warranty","read_only":1},
		{"fieldname":"custom_total_repair_cost","label":"Total Repair Cost","fieldtype":"Currency","options":"custom_currency","insert_after":"custom_labor_outside_warranty","read_only":1},
		{"fieldname":"custom_warranty_covered_amount","label":"Warranty Covered Amount","fieldtype":"Currency","options":"custom_currency","insert_after":"custom_total_repair_cost","read_only":1},
		{"fieldname":"custom_customer_payable_amount","label":"Customer Payable Amount","fieldtype":"Currency","options":"custom_currency","insert_after":"custom_warranty_covered_amount","read_only":1},
		{"fieldname":"custom_provider_claim_amount","label":"Provider Claim Amount","fieldtype":"Currency","options":"custom_currency","insert_after":"custom_customer_payable_amount","read_only":1},
		{"fieldname":"custom_documents_section","label":"Private Documents and Invoices","fieldtype":"Section Break","insert_after":"custom_provider_claim_amount"},
		{"fieldname":"custom_documents","label":"Documents","fieldtype":"Table","options":"Warranty Claim Document","insert_after":"custom_documents_section"},
	]


def configure_warranty_claim_permissions():
	from frappe.permissions import add_permission, update_permission_property

	for role in (INTERNAL_MANAGER, INTERNAL_USER):
		if not frappe.db.exists("Custom DocPerm", {"parent": "Warranty Claim", "role": role, "permlevel": 0}):
			add_permission("Warranty Claim", role, 0, "read")
		for ptype in ("read", "write", "create", "print", "report"):
			update_permission_property("Warranty Claim", role, 0, ptype, 1, validate=False)
	if not frappe.db.exists("Custom DocPerm", {"parent": "Warranty Claim", "role": INTERNAL_MANAGER, "permlevel": 1}):
		add_permission("Warranty Claim", INTERNAL_MANAGER, 1, "read")
	for ptype in ("read", "write"):
		update_permission_property("Warranty Claim", INTERNAL_MANAGER, 1, ptype, 1, validate=False)
	# Enable standard Version audit entries without changing ERPNext source files.
	if not frappe.db.exists("Property Setter", {"doc_type": "Warranty Claim", "property": "track_changes"}):
		frappe.make_property_setter({"doctype": "Warranty Claim", "doctype_or_field": "DocType", "property": "track_changes", "value": "1", "property_type": "Check"}, ignore_validate=True)


def create_workflow():
	states = [
		("Draft", INTERNAL_USER),
		("Submitted by Provider", INTERNAL_MANAGER),
		("Under Internal Review", INTERNAL_MANAGER),
		("Need More Information", INTERNAL_USER),
		("Approved", INTERNAL_MANAGER),
		("Partially Approved", INTERNAL_MANAGER),
		("Rejected", INTERNAL_MANAGER),
		("Repair In Progress", INTERNAL_USER),
		("Repair Completed", INTERNAL_USER),
		("Final Documents Submitted", INTERNAL_MANAGER),
		("Closed", INTERNAL_MANAGER),
	]
	for state, _role in states:
		if not frappe.db.exists("Workflow State", state):
			frappe.get_doc({"doctype": "Workflow State", "workflow_state_name": state}).insert(ignore_permissions=True)
	actions = {"Submit Claim", "Start Review", "Request More Information", "Resubmit", "Approve", "Partially Approve", "Reject", "Start Repair", "Complete Repair", "Submit Final Documents", "Close"}
	for action in actions:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": action}).insert(ignore_permissions=True)
	transitions = [
		("Draft", "Submit Claim", "Submitted by Provider", INTERNAL_USER),
		("Draft", "Submit Claim", "Submitted by Provider", PROVIDER_USER),
		("Submitted by Provider", "Start Review", "Under Internal Review", INTERNAL_MANAGER),
		("Under Internal Review", "Request More Information", "Need More Information", INTERNAL_MANAGER),
		("Need More Information", "Resubmit", "Submitted by Provider", INTERNAL_USER),
		("Need More Information", "Resubmit", "Submitted by Provider", PROVIDER_USER),
		("Under Internal Review", "Approve", "Approved", INTERNAL_MANAGER),
		("Under Internal Review", "Partially Approve", "Partially Approved", INTERNAL_MANAGER),
		("Under Internal Review", "Reject", "Rejected", INTERNAL_MANAGER),
		("Approved", "Start Repair", "Repair In Progress", INTERNAL_USER),
		("Approved", "Start Repair", "Repair In Progress", PROVIDER_USER),
		("Partially Approved", "Start Repair", "Repair In Progress", INTERNAL_USER),
		("Partially Approved", "Start Repair", "Repair In Progress", PROVIDER_USER),
		("Repair In Progress", "Complete Repair", "Repair Completed", INTERNAL_USER),
		("Repair In Progress", "Complete Repair", "Repair Completed", PROVIDER_USER),
		("Repair Completed", "Submit Final Documents", "Final Documents Submitted", INTERNAL_USER),
		("Repair Completed", "Submit Final Documents", "Final Documents Submitted", PROVIDER_USER),
		("Final Documents Submitted", "Close", "Closed", INTERNAL_MANAGER),
		("Rejected", "Close", "Closed", INTERNAL_MANAGER),
	]
	data = {
		"doctype": "Workflow",
		"workflow_name": "AN Truck Warranty Claim Workflow",
		"document_type": "Warranty Claim",
		"is_active": 1,
		"override_status": 1,
		"send_email_alert": 0,
		"workflow_state_field": "custom_claim_status",
		"states": [{"state": state, "doc_status": "0", "allow_edit": role, "send_email": 0} for state, role in states],
		"transitions": [{"state": state, "action": action, "next_state": next_state, "allowed": role, "allow_self_approval": 1} for state, action, next_state, role in transitions],
	}
	if frappe.db.exists("Workflow", data["workflow_name"]):
		doc = frappe.get_doc("Workflow", data["workflow_name"])
		doc.update(data)
		doc.save(ignore_permissions=True)
	else:
		frappe.get_doc(data).insert(ignore_permissions=True)

