import base64
import binascii
import json
import os

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, now_datetime
from frappe.utils.file_manager import save_file

from an_truck.warranty.access import get_provider_access, is_provider_user
from an_truck.warranty.setup import PROVIDER_USER
from an_truck.warranty.timezone import get_company_local_date


PROVIDER_TRANSITIONS = {
	"Draft": {"Submit Claim": "Submitted by Provider"},
	"Need More Information": {"Resubmit": "Submitted by Provider"},
	"Approved": {"Start Repair": "Repair In Progress"},
	"Partially Approved": {"Start Repair": "Repair In Progress"},
	"Repair In Progress": {"Complete Repair": "Repair Completed"},
	"Repair Completed": {"Submit Final Documents": "Final Documents Submitted"},
}
EDITABLE_STATES = {
	"Draft",
	"Need More Information",
	"Approved",
	"Partially Approved",
	"Repair In Progress",
	"Repair Completed",
}
CLAIM_FIELDS = {
	"complaint",
	"description",
	"custom_current_odometer",
	"custom_failure_date",
	"custom_inspection_date",
	"custom_technician_name",
	"custom_diagnosis",
	"custom_inspection_details",
	"custom_root_cause",
	"custom_provider_recommendation",
	"custom_provider_reason",
	"custom_provider_technical_notes",
	"custom_other_charges",
	"custom_other_covered_amount",
}
PART_FIELDS = {
	"coverage_category", "item", "part_number", "description", "qty", "uom",
	"unit_cost", "coverage_status", "covered_amount", "notes",
}
SERVICE_FIELDS = {
	"coverage_category", "service_type", "description", "technician", "hours",
	"rate", "coverage_status", "covered_amount", "notes",
}
UPLOAD_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _access():
	if frappe.session.user == "Guest" or not is_provider_user():
		frappe.throw(_("Warranty Provider login is required."), frappe.PermissionError)
	access = get_provider_access()
	if not access:
		frappe.throw(_("Your Warranty Provider access is disabled or not configured."), frappe.PermissionError)
	provider = frappe.db.get_value(
		"Warranty Provider", access.warranty_provider, ["provider_name", "status", "active"], as_dict=True
	)
	if not provider or not provider.active or provider.status != "Active":
		frappe.throw(_("This Warranty Provider account is not active."), frappe.PermissionError)
	if not access.all_branches:
		branch = frappe.db.get_value(
			"Warranty Provider Branch",
			access.warranty_provider_branch,
			["warranty_provider", "active"],
			as_dict=True,
		)
		if not branch or branch.warranty_provider != access.warranty_provider or not branch.active:
			frappe.throw(_("The assigned branch is invalid."), frappe.PermissionError)
	access.provider_name = provider.provider_name
	return access


def _branch_options(access):
	filters = {"warranty_provider": access.warranty_provider, "active": 1}
	if not access.all_branches:
		filters["name"] = access.warranty_provider_branch
	return frappe.get_all(
		"Warranty Provider Branch",
		filters=filters,
		fields=["name", "branch_name", "branch_code", "city"],
		order_by="branch_name asc",
	)


def _resolve_branch(access, branch=None):
	if not access.all_branches:
		if branch and branch != access.warranty_provider_branch:
			frappe.throw(_("You cannot select another Warranty Provider Branch."), frappe.PermissionError)
		branch = access.warranty_provider_branch
	if not branch:
		frappe.throw(_("Warranty Provider Branch is required."))
	row = frappe.db.get_value(
		"Warranty Provider Branch", branch, ["warranty_provider", "active"], as_dict=True
	)
	if not row or row.warranty_provider != access.warranty_provider or not row.active:
		frappe.throw(_("Select an active branch belonging to your Warranty Provider."), frappe.PermissionError)
	return branch


def _claim_for_access(name, access=None):
	access = access or _access()
	claim = frappe.get_doc("Warranty Claim", name)
	if claim.custom_warranty_provider != access.warranty_provider:
		frappe.throw(_("Warranty Claim not found."), frappe.PermissionError)
	if not access.all_branches and claim.custom_warranty_provider_branch != access.warranty_provider_branch:
		frappe.throw(_("Warranty Claim not found."), frappe.PermissionError)
	return claim, access


def _warranty_for_access(name, access=None):
	access = access or _access()
	warranty = frappe.get_doc("Vehicle Warranty", name)
	if warranty.warranty_provider != access.warranty_provider:
		frappe.throw(_("Vehicle Warranty not found."), frappe.PermissionError)
	return warranty, access


def _contract_allows_claim(warranty, today):
	contract = frappe.db.get_value(
		"Warranty Provider Contract",
		warranty.provider_contract,
		["warranty_provider", "status", "start_date", "end_date"],
		as_dict=True,
	)
	return bool(
		contract
		and contract.warranty_provider == warranty.warranty_provider
		and contract.status == "Active"
		and getdate(contract.start_date) <= today
		and (not contract.end_date or getdate(contract.end_date) >= today)
	)


def _can_create_claim(warranty):
	today = get_company_local_date(warranty.company)
	return bool(
		warranty.status == "Active"
		and getdate(warranty.warranty_expiry_date) >= today
		and _contract_allows_claim(warranty, today)
	)


@frappe.whitelist()
def get_portal_context():
	access = _access()
	return {
		"user": frappe.session.user,
		"provider": {"name": access.warranty_provider, "label": access.provider_name},
		"branch_mode": "all" if access.all_branches else "fixed",
		"branches": _branch_options(access),
	}


@frappe.whitelist()
def get_dashboard():
	access = _access()
	filters = {"custom_warranty_provider": access.warranty_provider}
	if not access.all_branches:
		filters["custom_warranty_provider_branch"] = access.warranty_provider_branch
	rows = frappe.get_all(
		"Warranty Claim",
		filters=filters,
		fields=["name", "custom_claim_status", "modified", "serial_no", "custom_warranty_provider_branch"],
		order_by="modified desc",
		limit_page_length=10,
		ignore_permissions=True,
	)
	counts = frappe.get_all(
		"Warranty Claim",
		filters=filters,
		fields=["custom_claim_status as status", "count(name) as count"],
		group_by="custom_claim_status",
		ignore_permissions=True,
	)
	return {"counts": {row.status: row.count for row in counts}, "recent_claims": rows}


@frappe.whitelist()
def search_vin(vin):
	access = _access()
	vin = (vin or "").strip()
	if len(vin) < 5 or len(vin) > 64 or any(char in vin for char in ("%", "_", "*")):
		frappe.throw(_("Enter a complete VIN / chassis number."))
	name = frappe.db.get_value(
		"Vehicle Warranty",
		{"vin": vin, "warranty_provider": access.warranty_provider},
		"name",
		order_by="warranty_start_date desc",
	)
	if not name:
		frappe.throw(_("No accessible warranty was found for that exact VIN."), frappe.DoesNotExistError)
	return _warranty_response(frappe.get_doc("Vehicle Warranty", name), access)


@frappe.whitelist()
def get_warranty(name):
	warranty, access = _warranty_for_access(name)
	return _warranty_response(warranty, access)


def _warranty_response(warranty, access):
	coverage = [
		{
			"category": row.coverage_category,
			"description": row.description,
			"covered": bool(row.covered),
			"coverage_limit": flt(row.coverage_limit),
			"mileage_limit": flt(row.mileage_limit),
			"conditions": row.conditions,
			"exclusions": row.exclusions,
		}
		for row in warranty.coverage_snapshot
	]
	customer_name = frappe.db.get_value("Customer", warranty.customer, "customer_name")
	return {
		"name": warranty.name,
		"vin": warranty.vin,
		"vehicle_model": warranty.vehicle_model,
		"customer_name": customer_name,
		"delivery_date": warranty.delivery_date,
		"start_date": warranty.warranty_start_date,
		"expiry_date": warranty.warranty_expiry_date,
		"status": warranty.status,
		"currency": warranty.currency,
		"coverage": coverage,
		"can_create_claim": _can_create_claim(warranty),
		"branches": _branch_options(access),
	}


@frappe.whitelist()
def list_claims(status=None, page=1, page_length=20):
	access = _access()
	page = max(cint(page), 1)
	page_length = min(max(cint(page_length), 1), 50)
	filters = {"custom_warranty_provider": access.warranty_provider}
	if not access.all_branches:
		filters["custom_warranty_provider_branch"] = access.warranty_provider_branch
	if status:
		filters["custom_claim_status"] = status
	rows = frappe.get_all(
		"Warranty Claim",
		filters=filters,
		fields=[
			"name", "serial_no as vin", "complaint_date", "custom_claim_status as status",
			"custom_warranty_provider_branch as branch", "modified",
		],
		order_by="modified desc",
		limit_start=(page - 1) * page_length,
		limit_page_length=page_length,
		ignore_permissions=True,
	)
	return {"claims": rows, "page": page, "page_length": page_length}


@frappe.whitelist()
def get_claim(name):
	claim, _access_row = _claim_for_access(name)
	return _claim_response(claim)


@frappe.whitelist(methods=["POST"])
def create_claim(vehicle_warranty, complaint, branch=None, complaint_date=None, payload=None):
	access = _access()
	warranty, _access_row = _warranty_for_access(vehicle_warranty, access)
	if not _can_create_claim(warranty):
		frappe.throw(_("This warranty or its provider contract is not eligible for a new claim."))
	branch = _resolve_branch(access, branch)
	data = _parse_payload(payload)
	data["complaint"] = complaint
	claim = frappe.get_doc({
		"doctype": "Warranty Claim",
		"custom_vehicle_warranty": warranty.name,
		"custom_warranty_provider_branch": branch,
		"complaint_date": complaint_date or get_company_local_date(warranty.company),
		"complaint": _limited_text(data.pop("complaint"), "Complaint", 10000),
	})
	_apply_claim_payload(claim, data)
	claim.insert(ignore_permissions=True)
	return _claim_response(claim)


@frappe.whitelist(methods=["POST"])
def update_claim(name, payload):
	claim, access = _claim_for_access(name)
	if claim.custom_claim_status not in EDITABLE_STATES:
		frappe.throw(_("This claim cannot be edited in its current status."), frappe.PermissionError)
	data = _parse_payload(payload)
	if "custom_warranty_provider_branch" in data:
		claim.custom_warranty_provider_branch = _resolve_branch(access, data.pop("custom_warranty_provider_branch"))
	_apply_claim_payload(claim, data)
	claim.save(ignore_permissions=True)
	return _claim_response(claim)


def _apply_claim_payload(claim, data):
	unknown = set(data) - CLAIM_FIELDS - {"parts", "services"}
	if unknown:
		frappe.throw(_("Unsupported claim fields: {0}").format(", ".join(sorted(unknown))), frappe.PermissionError)
	for fieldname in CLAIM_FIELDS:
		if fieldname in data:
			value = data[fieldname]
			if isinstance(value, str):
				value = _limited_text(value, fieldname, 20000)
			claim.set(fieldname, value)
	if "parts" in data:
		claim.set("custom_parts", [_allow_row(row, PART_FIELDS, "part") for row in data["parts"]])
	if "services" in data:
		claim.set("custom_services", [_allow_row(row, SERVICE_FIELDS, "service") for row in data["services"]])


def _allow_row(row, allowed, label):
	if not isinstance(row, dict) or set(row) - allowed:
		frappe.throw(_("Unsupported {0} fields.").format(label), frappe.PermissionError)
	return {key: (_limited_text(value, key, 5000) if isinstance(value, str) else value) for key, value in row.items()}


@frappe.whitelist(methods=["POST"])
def apply_claim_action(name, action):
	claim, _access_row = _claim_for_access(name)
	next_state = _provider_actions(claim.custom_claim_status).get(action)
	if not next_state:
		frappe.throw(_("This workflow action is not available."), frappe.PermissionError)
	_validate_provider_action(claim, action)
	old_state = claim.custom_claim_status
	standard_status = "Work In Progress" if next_state in {"Repair In Progress", "Repair Completed", "Final Documents Submitted"} else "Open"
	frappe.db.set_value(
		"Warranty Claim",
		claim.name,
		{"custom_claim_status": next_state, "status": standard_status},
		update_modified=True,
	)
	frappe.get_doc({
		"doctype": "Version",
		"ref_doctype": "Warranty Claim",
		"docname": claim.name,
		"data": frappe.as_json({"changed": [["custom_claim_status", old_state, next_state]]}),
	}).insert(ignore_permissions=True)
	claim.reload()
	return _claim_response(claim)


def _validate_provider_action(claim, action):
	if action in {"Submit Claim", "Resubmit"} and (not claim.complaint or not claim.custom_failure_date):
		frappe.throw(_("Complaint and Failure Date are required before submission."))
	if action == "Complete Repair" and not (claim.custom_parts or claim.custom_services):
		frappe.throw(_("Add at least one part or service before completing repair."))
	if action == "Submit Final Documents" and not claim.custom_documents:
		frappe.throw(_("Upload at least one final private document before submission."))


def _provider_actions(state):
	configured = PROVIDER_TRANSITIONS.get(state, {})
	if not configured:
		return {}
	workflow = frappe.db.get_value(
		"Workflow", {"document_type": "Warranty Claim", "is_active": 1}, "name"
	)
	if not workflow:
		return {}
	actual = frappe.get_all(
		"Workflow Transition",
		filters={"parent": workflow, "state": state, "allowed": PROVIDER_USER},
		fields=["action", "next_state"],
	)
	return {
		row.action: row.next_state
		for row in actual
		if configured.get(row.action) == row.next_state
	}


@frappe.whitelist(methods=["POST"])
def upload_claim_file(name, file_name, content, document_type, invoice_number=None, invoice_date=None, invoice_amount=0, vat_amount=0, notes=None):
	claim, _access_row = _claim_for_access(name)
	if claim.custom_claim_status not in EDITABLE_STATES:
		frappe.throw(_("Files cannot be added in the current claim status."), frappe.PermissionError)
	extension = os.path.splitext(file_name or "")[1].lower()
	if extension not in UPLOAD_EXTENSIONS:
		frappe.throw(_("Only PDF, PNG, JPG, JPEG, and WEBP files are allowed."))
	try:
		encoded = content.split(",", 1)[-1] if isinstance(content, str) else content
		decoded = base64.b64decode(encoded, validate=True)
	except (binascii.Error, ValueError, TypeError):
		frappe.throw(_("The uploaded file is not valid base64 content."))
	if not decoded or len(decoded) > MAX_UPLOAD_BYTES:
		frappe.throw(_("The uploaded file must be no larger than 10 MB."))
	file_doc = save_file(file_name, decoded, "Warranty Claim", claim.name, is_private=1)
	try:
		claim.append("custom_documents", {
			"document_type": document_type,
			"file": file_doc.file_url,
			"invoice_number": invoice_number,
			"invoice_date": invoice_date,
			"invoice_amount": flt(invoice_amount),
			"vat_amount": flt(vat_amount),
			"notes": _limited_text(notes, "Notes", 5000),
		})
		claim.save(ignore_permissions=True)
	except Exception:
		frappe.delete_doc("File", file_doc.name, ignore_permissions=True, force=True)
		raise
	return _claim_response(claim)


@frappe.whitelist()
def download_claim_file(file_id):
	_access_row = _access()
	file_doc = frappe.get_doc("File", file_id)
	if file_doc.attached_to_doctype != "Warranty Claim" or not file_doc.is_private:
		frappe.throw(_("File not found."), frappe.PermissionError)
	_claim_for_access(file_doc.attached_to_name, _access_row)
	frappe.local.response.filename = file_doc.file_name
	frappe.local.response.filecontent = file_doc.get_content()
	frappe.local.response.type = "download"


def _claim_response(claim):
	files_by_url = {
		row.file_url: row.name
		for row in frappe.get_all(
			"File",
			filters={"attached_to_doctype": "Warranty Claim", "attached_to_name": claim.name, "is_private": 1},
			fields=["name", "file_url"],
		)
	}
	return {
		"name": claim.name,
		"vin": claim.serial_no,
		"vehicle_warranty": claim.custom_vehicle_warranty,
		"branch": claim.custom_warranty_provider_branch,
		"status": claim.custom_claim_status,
		"complaint_date": claim.complaint_date,
		"complaint": claim.complaint,
		"description": claim.description,
		"current_odometer": flt(claim.custom_current_odometer),
		"failure_date": claim.custom_failure_date,
		"inspection": {
			"date": claim.custom_inspection_date,
			"technician": claim.custom_technician_name,
			"diagnosis": claim.custom_diagnosis,
			"details": claim.custom_inspection_details,
			"root_cause": claim.custom_root_cause,
		},
		"assessment": {
			"recommendation": claim.custom_provider_recommendation,
			"reason": claim.custom_provider_reason,
			"technical_notes": claim.custom_provider_technical_notes,
		},
		"parts": [_part_response(row) for row in claim.custom_parts],
		"services": [_service_response(row) for row in claim.custom_services],
		"documents": [
			{
				"document_type": row.document_type,
				"file_id": files_by_url.get(row.file),
				"file_name": os.path.basename(row.file or ""),
				"invoice_number": row.invoice_number,
				"invoice_date": row.invoice_date,
				"invoice_amount": flt(row.invoice_amount),
				"vat_amount": flt(row.vat_amount),
				"total_including_vat": flt(row.total_including_vat),
				"notes": row.notes,
			}
			for row in claim.custom_documents
		],
		"cost_summary": {
			"currency": claim.custom_currency,
			"other_charges": flt(claim.custom_other_charges),
			"other_covered_amount": flt(claim.custom_other_covered_amount),
			"parts_inside_warranty": flt(claim.custom_parts_inside_warranty),
			"parts_outside_warranty": flt(claim.custom_parts_outside_warranty),
			"labor_inside_warranty": flt(claim.custom_labor_inside_warranty),
			"labor_outside_warranty": flt(claim.custom_labor_outside_warranty),
			"total_repair_cost": flt(claim.custom_total_repair_cost),
			"warranty_covered_amount": flt(claim.custom_warranty_covered_amount),
			"customer_payable_amount": flt(claim.custom_customer_payable_amount),
			"provider_claim_amount": flt(claim.custom_provider_claim_amount),
		},
		"allowed_actions": list(_provider_actions(claim.custom_claim_status)),
		"editable": claim.custom_claim_status in EDITABLE_STATES,
	}


def _part_response(row):
	return {key: row.get(key) for key in [
		"coverage_category", "item", "part_number", "description", "qty", "uom",
		"unit_cost", "total_cost", "coverage_status", "covered_amount",
		"customer_payable_amount", "notes",
	]}


def _service_response(row):
	return {key: row.get(key) for key in [
		"coverage_category", "service_type", "description", "technician", "hours", "rate",
		"amount", "coverage_status", "covered_amount", "customer_payable_amount", "notes",
	]}


def _parse_payload(payload):
	if not payload:
		return {}
	data = frappe.parse_json(payload)
	if not isinstance(data, dict):
		frappe.throw(_("Claim payload must be an object."))
	return data


def _limited_text(value, label, limit):
	if value is None:
		return None
	value = str(value)
	if len(value) > limit:
		frappe.throw(_("{0} is too long.").format(label))
	return value
