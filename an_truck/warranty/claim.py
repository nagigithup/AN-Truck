import json

import frappe
from frappe import _
from frappe.utils import flt, getdate, now_datetime

from an_truck.warranty.access import get_provider_access, is_provider_user
from an_truck.warranty.timezone import get_company_local_date


INTERNAL_FIELDS = (
	"custom_internal_decision",
	"custom_internal_decision_reason",
	"custom_internal_notes",
	"custom_approved_provider_claim_amount",
)
def before_validate_warranty_claim(doc, method=None):
	# ERPNext's WarrantyClaim controller requires Customer during validate, so linked
	# warranty values must be populated in before_validate rather than a validate hook.
	populate_from_warranty(doc)


def validate_warranty_claim(doc, method=None):
	previous = doc.get_doc_before_save()
	validate_closed_claim(doc, previous)
	populate_from_warranty(doc)
	validate_provider_access(doc, previous)
	validate_branch(doc, previous)
	validate_dates(doc)
	calculate_costs(doc)
	validate_coverage(doc)
	validate_internal_approval(doc, previous)
	validate_documents(doc)
	sync_standard_status(doc)


def populate_from_warranty(doc):
	if not doc.custom_vehicle_warranty:
		return
	warranty = frappe.db.get_value(
		"Vehicle Warranty",
		doc.custom_vehicle_warranty,
		["vin", "vehicle_master", "customer", "item_code", "company", "currency", "warranty_provider", "warranty_expiry_date", "status"],
		as_dict=True,
	)
	if not warranty:
		frappe.throw(_("Vehicle Warranty does not exist."))
	if warranty.status == "Cancelled":
		frappe.throw(_("Claims cannot be created against a cancelled Vehicle Warranty."))
	doc.serial_no = warranty.vin
	doc.custom_vehicle_master = warranty.vehicle_master
	doc.customer = warranty.customer
	doc.item_code = warranty.item_code
	doc.company = warranty.company
	doc.custom_currency = warranty.currency
	doc.custom_warranty_provider = warranty.warranty_provider
	doc.warranty_expiry_date = warranty.warranty_expiry_date
	doc.warranty_amc_status = (
		"Under Warranty"
		if warranty.status == "Active"
		and getdate(warranty.warranty_expiry_date) >= get_company_local_date(warranty.company)
		else "Out of Warranty"
	)


def validate_provider_access(doc, previous=None):
	if not is_provider_user():
		return
	access = get_provider_access()
	if not access:
		frappe.throw(_("No active Warranty Provider access is configured for this user."), frappe.PermissionError)
	if doc.custom_warranty_provider != access.warranty_provider:
		frappe.throw(_("The Vehicle Warranty does not belong to your Warranty Provider."), frappe.PermissionError)
	if previous and previous.custom_vehicle_warranty != doc.custom_vehicle_warranty:
		frappe.throw(_("Warranty Provider users cannot change the Vehicle Warranty after claim creation."), frappe.PermissionError)
	if access.all_branches:
		if not doc.custom_warranty_provider_branch:
			frappe.throw(_("Warranty Provider Branch is required."))
	else:
		if doc.custom_warranty_provider_branch and doc.custom_warranty_provider_branch != access.warranty_provider_branch:
			frappe.throw(_("You cannot create or move a claim to another branch."), frappe.PermissionError)
		doc.custom_warranty_provider_branch = access.warranty_provider_branch
	for fieldname in INTERNAL_FIELDS:
		if doc.get(fieldname) and (not previous or doc.get(fieldname) != previous.get(fieldname)):
			frappe.throw(_("Warranty Provider users cannot set internal approval fields."), frappe.PermissionError)


def validate_branch(doc, previous=None):
	provider_user = is_provider_user()
	if provider_user or doc.custom_claim_status != "Draft":
		if not doc.custom_warranty_provider_branch:
			frappe.throw(_("Warranty Provider Branch is required for provider claims."))
	if not doc.custom_warranty_provider_branch:
		return
	branch = frappe.db.get_value(
		"Warranty Provider Branch",
		doc.custom_warranty_provider_branch,
		["warranty_provider", "active"],
		as_dict=True,
	)
	if not branch or branch.warranty_provider != doc.custom_warranty_provider:
		frappe.throw(_("Warranty Provider Branch must belong to the Warranty Provider."))
	branch_changed = not previous or previous.custom_warranty_provider_branch != doc.custom_warranty_provider_branch
	if branch_changed and not branch.active:
		frappe.throw(_("A new claim must use an active Warranty Provider Branch."))


def validate_dates(doc):
	today = get_company_local_date(doc.company) if doc.company else now_datetime().date()
	if doc.custom_failure_date and getdate(doc.custom_failure_date) > today:
		frappe.throw(_("Failure Date cannot be in the future."))
	if doc.custom_inspection_date and getdate(doc.custom_inspection_date) > today:
		frappe.throw(_("Inspection Date cannot be in the future."))
	if doc.custom_failure_date and doc.custom_inspection_date and getdate(doc.custom_inspection_date) < getdate(doc.custom_failure_date):
		frappe.throw(_("Inspection Date cannot be before Failure Date."))


def calculate_costs(doc):
	parts_covered = parts_customer = services_covered = services_customer = total_parts = total_services = 0.0
	for row in doc.custom_parts:
		if flt(row.qty) <= 0 or flt(row.unit_cost) < 0:
			frappe.throw(_("Part quantity must be greater than zero and Unit Cost cannot be negative."))
		row.total_cost = flt(row.qty) * flt(row.unit_cost)
		set_row_coverage(row, row.total_cost)
		total_parts += row.total_cost
		parts_covered += flt(row.covered_amount)
		parts_customer += flt(row.customer_payable_amount)
	for row in doc.custom_services:
		if flt(row.hours) <= 0 or flt(row.rate) < 0:
			frappe.throw(_("Service hours must be greater than zero and Rate cannot be negative."))
		row.amount = flt(row.hours) * flt(row.rate)
		set_row_coverage(row, row.amount)
		total_services += row.amount
		services_covered += flt(row.covered_amount)
		services_customer += flt(row.customer_payable_amount)
	other = flt(doc.custom_other_charges)
	other_covered = flt(doc.custom_other_covered_amount)
	if other < 0 or other_covered < 0 or other_covered > other:
		frappe.throw(_("Other covered amount must be between zero and Other Charges."))
	doc.custom_parts_inside_warranty = parts_covered
	doc.custom_parts_outside_warranty = parts_customer
	doc.custom_labor_inside_warranty = services_covered
	doc.custom_labor_outside_warranty = services_customer
	doc.custom_total_repair_cost = total_parts + total_services + other
	doc.custom_warranty_covered_amount = parts_covered + services_covered + other_covered
	doc.custom_customer_payable_amount = parts_customer + services_customer + (other - other_covered)
	doc.custom_provider_claim_amount = doc.custom_warranty_covered_amount
	for row in doc.custom_documents:
		if flt(row.invoice_amount) < 0 or flt(row.vat_amount) < 0:
			frappe.throw(_("Invoice and VAT amounts cannot be negative."))
		row.total_including_vat = flt(row.invoice_amount) + flt(row.vat_amount)


def set_row_coverage(row, total):
	status = row.coverage_status
	if status == "Inside Warranty":
		row.covered_amount = total
		row.customer_payable_amount = 0
	elif status == "Outside Warranty":
		row.covered_amount = 0
		row.customer_payable_amount = total
	elif status == "Partially Covered":
		covered = flt(row.covered_amount)
		if covered < 0 or covered > total:
			frappe.throw(_("Partially covered amount must be between zero and the row total."))
		row.customer_payable_amount = total - covered
	else:
		row.covered_amount = 0
		row.customer_payable_amount = 0


def validate_coverage(doc):
	if not doc.custom_vehicle_warranty:
		return
	covered_categories = set(frappe.get_all(
		"Vehicle Warranty Coverage Item",
		filters={"parent": doc.custom_vehicle_warranty, "parenttype": "Vehicle Warranty", "covered": 1},
		pluck="coverage_category",
	))
	for row in [*doc.custom_parts, *doc.custom_services]:
		if row.coverage_status in {"Inside Warranty", "Partially Covered"} and row.coverage_category not in covered_categories:
			frappe.throw(_("Coverage component {0} is not covered by Vehicle Warranty {1}.").format(row.coverage_category, doc.custom_vehicle_warranty))


def validate_internal_approval(doc, previous=None):
	manager = bool({"System Manager", "AN Truck Warranty Manager"}.intersection(frappe.get_roles()))
	for fieldname in INTERNAL_FIELDS:
		if previous and doc.get(fieldname) != previous.get(fieldname) and not manager:
			frappe.throw(_("Only a Warranty Manager can change internal approval fields."), frappe.PermissionError)
	state_decisions = {
		"Need More Information": "Need More Information",
		"Approved": "Approved",
		"Partially Approved": "Partially Approved",
		"Rejected": "Rejected",
	}
	state_changed = not previous or previous.custom_claim_status != doc.custom_claim_status
	if doc.custom_claim_status in state_decisions and state_changed:
		if not manager:
			frappe.throw(_("Only a Warranty Manager can make the internal coverage decision."), frappe.PermissionError)
		doc.custom_internal_decision = state_decisions[doc.custom_claim_status]
		doc.custom_approved_by = frappe.session.user
		doc.custom_approval_date = now_datetime()
		if doc.custom_claim_status == "Approved":
			doc.custom_approved_provider_claim_amount = doc.custom_provider_claim_amount
		elif doc.custom_claim_status == "Rejected":
			doc.custom_approved_provider_claim_amount = 0
		elif doc.custom_claim_status == "Partially Approved":
			amount = flt(doc.custom_approved_provider_claim_amount)
			if amount <= 0 or amount >= flt(doc.custom_provider_claim_amount):
				frappe.throw(_("A partially approved amount must be greater than zero and less than the Provider Claim Amount."))
	if flt(doc.custom_approved_provider_claim_amount) > flt(doc.custom_provider_claim_amount):
		frappe.throw(_("Approved Provider Claim Amount cannot exceed Provider Claim Amount."))


def validate_documents(doc):
	if doc.custom_claim_status in {"Final Documents Submitted", "Closed"} and not doc.custom_documents:
		frappe.throw(_("At least one final private document is required."))
	for row in doc.custom_documents:
		if not row.file:
			continue
		file_row = frappe.db.get_value("File", {"file_url": row.file}, ["name", "is_private"], as_dict=True)
		if file_row and not file_row.is_private:
			frappe.throw(_("Warranty claim documents must be uploaded as private files."))


def sync_standard_status(doc):
	if doc.custom_claim_status == "Closed":
		doc.status = "Closed"
	elif doc.custom_claim_status in {"Repair In Progress", "Repair Completed", "Final Documents Submitted"}:
		doc.status = "Work In Progress"
	else:
		doc.status = "Open"


def validate_closed_claim(doc, previous=None):
	if not previous or previous.custom_claim_status != "Closed":
		return
	if {"System Manager", "AN Truck Warranty Manager"}.intersection(frappe.get_roles()):
		return
	ignored = {"modified", "modified_by", "__last_sync_on"}
	before = {key: value for key, value in previous.as_dict().items() if key not in ignored}
	after = {key: value for key, value in doc.as_dict().items() if key not in ignored}
	if json.dumps(before, sort_keys=True, default=str) != json.dumps(after, sort_keys=True, default=str):
		frappe.throw(_("Closed Warranty Claims can only be changed by a Warranty Manager."), frappe.PermissionError)


def prevent_warranty_claim_delete(doc, method=None):
	if doc.custom_vehicle_warranty and "System Manager" not in frappe.get_roles():
		frappe.throw(_("Vehicle warranty claims are audit records and cannot be deleted. Close the claim instead."), frappe.PermissionError)


def validate_claim_file(doc, method=None):
	if doc.attached_to_doctype == "Warranty Claim" and not doc.is_private:
		frappe.throw(_("Files attached to Warranty Claims must be private."))
