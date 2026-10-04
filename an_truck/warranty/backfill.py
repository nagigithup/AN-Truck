import frappe
from frappe import _
from frappe.core.doctype.user_permission.user_permission import get_permitted_documents
from frappe.utils import getdate

from an_truck.warranty.activation import (
	activate_vehicle_warranty,
	calculate_warranty_expiry,
	get_valid_contract,
)
from an_truck.warranty.reporting import require_internal_reporting_access
from an_truck.warranty.setup import INTERNAL_MANAGER


READY = "READY"
MANUAL_REVIEW = "REQUIRES MANUAL REVIEW"
MISSING_DELIVERY_DATE = "MISSING DELIVERY DATE"


def preview_historical_warranties(filters=None):
	require_internal_reporting_access()
	filters = frappe._dict(filters or {})
	conditions = ["v.disabled=0", "v.vehicle_status in ('Sold','Delivered')"]
	params = {}
	permitted_companies = get_permitted_documents("Company")
	if filters.get("company"):
		if permitted_companies and filters.company not in permitted_companies:
			frappe.throw(
				_("You are not permitted to review Company {0}.").format(filters.company),
				frappe.PermissionError,
			)
		params["company"] = filters.company
		conditions.append("v.company=%(company)s")
	elif permitted_companies:
		params["permitted_companies"] = tuple(permitted_companies)
		conditions.append("v.company in %(permitted_companies)s")
	if filters.get("vin"):
		params["vin"] = filters.vin
		conditions.append("v.vin=%(vin)s")
	vehicles = frappe.db.sql(
		f"""select v.name, v.vin, v.customer, v.item_code, v.company, v.delivery_note,
			v.sales_invoice, v.vehicle_status
		from `tabVehicle Master` v where {' and '.join(conditions)} order by v.vin""",
		params,
		as_dict=True,
	)
	settings = frappe.get_single("AN Truck Settings")
	item_codes = list({row.item_code for row in vehicles if row.item_code})
	item_config = {
		row.name: row for row in frappe.get_all(
			"Item",
			filters={"name": ["in", item_codes]},
			fields=["name", "custom_warranty_provider", "custom_warranty_coverage_template"],
		)
	} if item_codes else {}
	return [_evaluate_vehicle(vehicle, settings, item_config.get(vehicle.item_code)) for vehicle in vehicles]


def _evaluate_vehicle(vehicle, settings, item_config=None):
	row = frappe._dict(
		vin=vehicle.vin,
		vehicle_master=vehicle.name,
		customer=vehicle.customer,
		company=vehicle.company,
		delivery_source=None,
		delivery_document=None,
		delivery_date=None,
		warranty_provider=None,
		provider_contract=None,
		coverage_template=None,
		calculated_start_date=None,
		calculated_expiry_date=None,
		result=None,
		eligibility=None,
	)
	if not vehicle.vin or not frappe.db.exists("Serial No", vehicle.vin):
		return _result(row, "INVALID VIN / VEHICLE LINK", _("VIN is missing or is not a Serial No."))
	serial_item = frappe.db.get_value("Serial No", vehicle.vin, "item_code")
	if serial_item != vehicle.item_code:
		return _result(row, "INVALID VIN / VEHICLE LINK", _("Vehicle Master and Serial No item links do not match."))
	existing = frappe.db.get_value("Vehicle Warranty", {"vin": vehicle.vin}, "name", order_by="warranty_start_date desc")
	if existing:
		return _result(row, "WARRANTY ALREADY EXISTS", existing)
	if not vehicle.customer:
		return _result(row, MANUAL_REVIEW, _("Customer is missing."))

	delivery = _delivery_source(vehicle)
	if not delivery:
		return _result(row, MISSING_DELIVERY_DATE, MANUAL_REVIEW)
	row.update(delivery)
	row.calculated_start_date = row.delivery_date
	item_config = item_config or frappe._dict()
	row.warranty_provider = item_config.get("custom_warranty_provider") or settings.default_warranty_provider
	row.coverage_template = item_config.get("custom_warranty_coverage_template") or settings.default_warranty_coverage_template
	if not row.warranty_provider:
		return _result(row, "MISSING WARRANTY PROVIDER", _("No Item or default Warranty Provider is configured."))
	if not row.coverage_template or not frappe.db.get_value("Warranty Coverage Template", row.coverage_template, "active"):
		return _result(row, "MISSING COVERAGE TEMPLATE", _("No active Item or default Coverage Template is configured."))
	row.provider_contract = get_valid_contract(row.warranty_provider, row.delivery_date)
	if not row.provider_contract:
		return _result(row, "NO VALID PROVIDER CONTRACT", _("No active provider contract covers the delivery date."))
	row.calculated_expiry_date = calculate_warranty_expiry(row.delivery_date, row.coverage_template)
	return _result(row, READY, _("Eligible for controlled historical backfill."))


def _delivery_source(vehicle):
	if vehicle.delivery_note:
		delivery = frappe.db.get_value(
			"Delivery Note", vehicle.delivery_note, ["docstatus", "posting_date"], as_dict=True
		)
		linked = frappe.db.exists(
			"Delivery Note Item", {"parent": vehicle.delivery_note, "custom_vehicle_master": vehicle.name}
		)
		if delivery and delivery.docstatus == 1 and delivery.posting_date and linked:
			return frappe._dict(
				delivery_source="Delivery Note", delivery_document=vehicle.delivery_note,
				delivery_date=getdate(delivery.posting_date),
			)
	if vehicle.sales_invoice:
		invoice = frappe.db.get_value(
			"Sales Invoice", vehicle.sales_invoice, ["docstatus", "custom_delivery_date"], as_dict=True
		)
		linked = frappe.db.exists(
			"Sales Invoice Item", {"parent": vehicle.sales_invoice, "custom_vehicle_master": vehicle.name}
		)
		if invoice and invoice.docstatus == 1 and invoice.custom_delivery_date and linked:
			return frappe._dict(
				delivery_source="Sales Invoice Delivery Date", delivery_document=vehicle.sales_invoice,
				delivery_date=getdate(invoice.custom_delivery_date),
			)
	return None


def _result(row, result, eligibility):
	row.result = result
	row.eligibility = eligibility
	return row


@frappe.whitelist(methods=["POST"])
def execute_historical_backfill(company=None, vin=None):
	_require_backfill_manager()
	preview = preview_historical_warranties({"company": company, "vin": vin})
	manual_results = {MANUAL_REVIEW, MISSING_DELIVERY_DATE}
	summary = {
		"eligible": sum(row.result == READY for row in preview),
		"created": 0,
		"skipped": sum(row.result != READY and row.result not in manual_results for row in preview),
		"failed": 0,
		"manual_review": sum(row.result in manual_results for row in preview),
		"results": [],
	}
	for index, row in enumerate(preview):
		if row.result != READY:
			continue
		savepoint = f"warranty_backfill_{index}"
		frappe.db.savepoint(savepoint)
		try:
			name = activate_vehicle_warranty(
				row.vehicle_master,
				row.delivery_date,
				delivery_note=row.delivery_document if row.delivery_source == "Delivery Note" else None,
				sales_invoice=row.delivery_document if row.delivery_source == "Sales Invoice Delivery Date" else None,
				activation_source=row.delivery_source,
			)
			if not name:
				raise frappe.ValidationError(_("Warranty activation returned no document."))
			frappe.get_doc({
				"doctype": "Comment", "comment_type": "Info", "reference_doctype": "Vehicle Warranty",
				"reference_name": name,
				"content": _("Historical warranty backfilled from {0} {1} by {2}.").format(
					row.delivery_source, row.delivery_document, frappe.session.user
				),
			}).insert(ignore_permissions=True)
			summary["created"] += 1
			summary["results"].append({"vin": row.vin, "warranty": name, "result": "CREATED"})
		except Exception as exc:
			frappe.db.rollback(save_point=savepoint)
			summary["failed"] += 1
			summary["results"].append({"vin": row.vin, "result": "FAILED", "reason": str(exc)})
	return summary


def _require_backfill_manager():
	if frappe.session.user != "Administrator" and not {"System Manager", INTERNAL_MANAGER}.intersection(frappe.get_roles()):
		frappe.throw(_("Only a Warranty Manager or System Manager can execute historical backfill."), frappe.PermissionError)
