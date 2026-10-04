from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import frappe
from frappe import _
from frappe.core.doctype.user_permission.user_permission import get_permitted_documents
from frappe.utils import add_days, cint, flt, get_first_day, get_last_day, getdate

from an_truck.warranty.access import is_provider_user
from an_truck.warranty.setup import INTERNAL_MANAGER, INTERNAL_USER, PROVIDER_USER
from an_truck.warranty.timezone import get_company_warranty_timezone


INTERNAL_REPORT_ROLES = {"System Manager", "AN Truck Manager", INTERNAL_MANAGER, INTERNAL_USER}


def require_internal_reporting_access():
	roles = set(frappe.get_roles())
	if is_provider_user() or not roles.intersection(INTERNAL_REPORT_ROLES):
		frappe.throw(_("You are not permitted to access internal warranty reporting."), frappe.PermissionError)


def _filters(filters=None):
	require_internal_reporting_access()
	return frappe._dict(filters or {})


def _conditions(filters, alias, params, mappings, date_field=None):
	conditions = []
	for filter_name, field_name in mappings.items():
		if filters.get(filter_name):
			params[filter_name] = filters[filter_name]
			conditions.append(f"{alias}.`{field_name}` = %({filter_name})s")
	if date_field:
		if filters.get("from_date"):
			params["from_date"] = filters.from_date
			conditions.append(f"{alias}.`{date_field}` >= %(from_date)s")
		if filters.get("to_date"):
			params["to_date"] = filters.to_date
			conditions.append(f"{alias}.`{date_field}` <= %(to_date)s")
	_conditions_for_company(filters, alias, params, conditions)
	return (" and " + " and ".join(conditions)) if conditions else ""


def _conditions_for_company(filters, alias, params, conditions):
	permitted = get_permitted_documents("Company")
	if filters.get("company"):
		if permitted and filters.company not in permitted:
			frappe.throw(_("You are not permitted to report on Company {0}.").format(filters.company), frappe.PermissionError)
		params["company"] = filters.company
		conditions.append(f"{alias}.company = %(company)s")
	elif permitted:
		params["permitted_companies"] = tuple(permitted)
		conditions.append(f"{alias}.company in %(permitted_companies)s")


def _currency_column(label, fieldname, width=140):
	return {"label": _(label), "fieldname": fieldname, "fieldtype": "Currency", "options": "currency", "width": width}


def active_vehicle_warranties(filters=None):
	filters = _filters(filters)
	params = {}
	condition = _conditions(
		filters, "w", params,
		{"vin": "vin", "customer": "customer", "provider": "warranty_provider", "vehicle_model": "vehicle_model", "company": "company"},
	)
	if filters.get("from_expiry_date"):
		params["from_expiry_date"] = filters.from_expiry_date
		condition += " and w.warranty_expiry_date >= %(from_expiry_date)s"
	if filters.get("to_expiry_date"):
		params["to_expiry_date"] = filters.to_expiry_date
		condition += " and w.warranty_expiry_date <= %(to_expiry_date)s"
	rows = frappe.db.sql(
		f"""select w.vin, w.vehicle_master as vehicle, w.vehicle_model, w.customer,
			w.warranty_provider as provider, w.warranty_start_date as start_date,
			w.warranty_expiry_date as expiry_date, w.status, w.company
		from `tabVehicle Warranty` w where w.status='Active' {condition}
		order by w.warranty_expiry_date, w.vin""",
		params,
		as_dict=True,
	)
	today_by_company = _company_dates({row.company for row in rows})
	for row in rows:
		row.remaining_days = (getdate(row.expiry_date) - today_by_company[row.company]).days
	return _active_columns(), rows


def _active_columns():
	return [
		{"label": _("VIN"), "fieldname": "vin", "fieldtype": "Link", "options": "Serial No", "width": 180},
		{"label": _("Vehicle"), "fieldname": "vehicle", "fieldtype": "Link", "options": "Vehicle Master", "width": 150},
		{"label": _("Model"), "fieldname": "vehicle_model", "width": 170},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 180},
		{"label": _("Warranty Provider"), "fieldname": "provider", "fieldtype": "Link", "options": "Warranty Provider", "width": 180},
		{"label": _("Start Date"), "fieldname": "start_date", "fieldtype": "Date", "width": 105},
		{"label": _("Expiry Date"), "fieldname": "expiry_date", "fieldtype": "Date", "width": 105},
		{"label": _("Remaining Days"), "fieldname": "remaining_days", "fieldtype": "Int", "width": 115},
		{"label": _("Warranty Status"), "fieldname": "status", "width": 115},
	]


def expiring_warranties(filters=None):
	filters = _filters(filters)
	days = max(min(cint(filters.get("days_to_expiry") or 30), 3650), 0)
	params = {}
	condition = _conditions(
		filters, "w", params,
		{"provider": "warranty_provider", "customer": "customer", "vehicle_model": "vehicle_model", "company": "company"},
	)
	rows = frappe.db.sql(
		f"""select w.vin, w.vehicle_master as vehicle, w.vehicle_model, w.customer,
			w.warranty_provider as provider, w.warranty_start_date as start_date,
			w.warranty_expiry_date as expiry_date, w.status, w.company
		from `tabVehicle Warranty` w where w.status='Active' {condition}
		order by w.warranty_expiry_date, w.vin""",
		params,
		as_dict=True,
	)
	today_by_company = _company_dates({row.company for row in rows})
	result = []
	for row in rows:
		row.remaining_days = (getdate(row.expiry_date) - today_by_company[row.company]).days
		if 0 <= row.remaining_days <= days:
			result.append(row)
	return _active_columns(), result


def warranty_claims(filters=None):
	filters = _filters(filters)
	params = {}
	condition = _conditions(
		filters, "c", params,
		{"vin": "serial_no", "customer": "customer", "provider": "custom_warranty_provider", "branch": "custom_warranty_provider_branch", "claim_status": "custom_claim_status", "company": "company"},
		"complaint_date",
	)
	rows = frappe.db.sql(
		f"""select c.name as claim_number, c.serial_no as vin, c.customer,
			c.custom_warranty_provider as provider, c.custom_warranty_provider_branch as branch,
			c.complaint_date as claim_date, coalesce(nullif(c.custom_root_cause,''), c.complaint) as component,
			c.custom_claim_status as status, c.custom_total_repair_cost as total_repair_cost,
			c.custom_warranty_covered_amount as warranty_covered_amount,
			c.custom_customer_payable_amount as customer_payable,
			c.custom_provider_claim_amount as provider_claim_amount, c.custom_currency as currency
		from `tabWarranty Claim` c where c.docstatus < 2 {condition}
		order by c.complaint_date desc, c.name desc""",
		params,
		as_dict=True,
	)
	columns = [
		{"label": _("Claim Number"), "fieldname": "claim_number", "fieldtype": "Link", "options": "Warranty Claim", "width": 160},
		{"label": _("VIN"), "fieldname": "vin", "fieldtype": "Link", "options": "Serial No", "width": 170},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 160},
		{"label": _("Provider"), "fieldname": "provider", "fieldtype": "Link", "options": "Warranty Provider", "width": 160},
		{"label": _("Branch"), "fieldname": "branch", "fieldtype": "Link", "options": "Warranty Provider Branch", "width": 160},
		{"label": _("Claim Date"), "fieldname": "claim_date", "fieldtype": "Date", "width": 105},
		{"label": _("Component / Main Failure"), "fieldname": "component", "width": 220},
		{"label": _("Status"), "fieldname": "status", "width": 150},
		_currency_column("Total Repair Cost", "total_repair_cost"),
		_currency_column("Warranty Covered Amount", "warranty_covered_amount"),
		_currency_column("Customer Payable", "customer_payable"),
		_currency_column("Provider Claim Amount", "provider_claim_amount"),
	]
	return columns, rows


def warranty_cost_by_vin(filters=None):
	filters = _filters(filters)
	params = {}
	condition = _conditions(filters, "c", params, {"vin": "serial_no", "customer": "customer", "company": "company"}, "complaint_date")
	rows = frappe.db.sql(
		f"""select c.serial_no as vin, max(c.custom_vehicle_master) as vehicle, max(c.customer) as customer,
			count(*) as number_of_claims, sum(c.custom_total_repair_cost) as total_repair_cost,
			sum(c.custom_warranty_covered_amount) as warranty_covered_cost,
			sum(c.custom_customer_payable_amount) as customer_payable,
			sum(c.custom_provider_claim_amount) as provider_claim_amount, max(c.custom_currency) as currency
		from `tabWarranty Claim` c where c.docstatus < 2 {condition}
		group by c.serial_no order by total_repair_cost desc""", params, as_dict=True)
	columns = [
		{"label": _("VIN"), "fieldname": "vin", "fieldtype": "Link", "options": "Serial No", "width": 180},
		{"label": _("Vehicle"), "fieldname": "vehicle", "fieldtype": "Link", "options": "Vehicle Master", "width": 150},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 170},
		{"label": _("Number of Claims"), "fieldname": "number_of_claims", "fieldtype": "Int", "width": 120},
		_currency_column("Total Repair Cost", "total_repair_cost"), _currency_column("Warranty Covered Cost", "warranty_covered_cost"),
		_currency_column("Customer Payable", "customer_payable"), _currency_column("Provider Claim Amount", "provider_claim_amount"),
	]
	return columns, rows


def warranty_cost_by_provider(filters=None):
	filters = _filters(filters)
	params = {}
	company_conditions = []
	_conditions_for_company(filters, "w", params, company_conditions)
	company_sql = (" and " + " and ".join(company_conditions)) if company_conditions else ""
	claim_params = dict(params)
	claim_condition = _conditions(filters, "c", claim_params, {"provider": "custom_warranty_provider", "company": "company"}, "complaint_date")
	if filters.get("provider"):
		params["provider"] = filters.provider
		company_sql += " and w.warranty_provider=%(provider)s"
	warranties = {row.provider: row.active_warranties for row in frappe.db.sql(
		f"""select w.warranty_provider as provider, count(*) as active_warranties
		from `tabVehicle Warranty` w where w.status='Active' {company_sql} group by w.warranty_provider""", params, as_dict=True)}
	rows = frappe.db.sql(
		f"""select c.custom_warranty_provider as provider, count(*) as number_of_claims,
			sum(c.custom_claim_status='Approved') as approved_claims,
			sum(c.custom_claim_status='Rejected') as rejected_claims,
			sum(c.custom_total_repair_cost) as total_repair_cost,
			sum(c.custom_warranty_covered_amount) as warranty_covered_amount,
			sum(c.custom_provider_claim_amount) as provider_claim_amount,
			avg(c.custom_total_repair_cost) as average_claim_cost, max(c.custom_currency) as currency
		from `tabWarranty Claim` c where c.docstatus < 2 {claim_condition}
		group by c.custom_warranty_provider order by total_repair_cost desc""", claim_params, as_dict=True)
	by_provider = {row.provider: row for row in rows}
	for provider, active_count in warranties.items():
		row = by_provider.setdefault(provider, frappe._dict(
			provider=provider, number_of_claims=0, approved_claims=0, rejected_claims=0,
			total_repair_cost=0, warranty_covered_amount=0, provider_claim_amount=0,
			average_claim_cost=0, currency=None,
		))
		row.active_warranties = active_count
	for row in by_provider.values():
		row.active_warranties = warranties.get(row.provider, 0)
	rows = sorted(by_provider.values(), key=lambda row: flt(row.total_repair_cost), reverse=True)
	columns = [
		{"label": _("Provider"), "fieldname": "provider", "fieldtype": "Link", "options": "Warranty Provider", "width": 190},
		{"label": _("Active Warranties"), "fieldname": "active_warranties", "fieldtype": "Int", "width": 125},
		{"label": _("Number of Claims"), "fieldname": "number_of_claims", "fieldtype": "Int", "width": 115},
		{"label": _("Approved Claims"), "fieldname": "approved_claims", "fieldtype": "Int", "width": 110},
		{"label": _("Rejected Claims"), "fieldname": "rejected_claims", "fieldtype": "Int", "width": 110},
		_currency_column("Total Repair Cost", "total_repair_cost"), _currency_column("Warranty Covered Amount", "warranty_covered_amount"),
		_currency_column("Provider Claim Amount", "provider_claim_amount"), _currency_column("Average Claim Cost", "average_claim_cost"),
	]
	return columns, rows


def warranty_cost_by_branch(filters=None):
	filters = _filters(filters)
	params = {}
	condition = _conditions(filters, "c", params, {"provider": "custom_warranty_provider", "branch": "custom_warranty_provider_branch", "company": "company"}, "complaint_date")
	rows = frappe.db.sql(
		f"""select c.custom_warranty_provider as provider, c.custom_warranty_provider_branch as branch,
			count(*) as number_of_claims, sum(c.custom_total_repair_cost) as total_repair_cost,
			sum(c.custom_warranty_covered_amount) as warranty_covered_amount,
			sum(c.custom_provider_claim_amount) as provider_claim_amount,
			avg(c.custom_total_repair_cost) as average_claim_cost, max(c.custom_currency) as currency
		from `tabWarranty Claim` c where c.docstatus < 2 and c.custom_warranty_provider_branch is not null {condition}
		group by c.custom_warranty_provider, c.custom_warranty_provider_branch order by total_repair_cost desc""",
		params, as_dict=True)
	columns = [
		{"label": _("Provider"), "fieldname": "provider", "fieldtype": "Link", "options": "Warranty Provider", "width": 180},
		{"label": _("Branch"), "fieldname": "branch", "fieldtype": "Link", "options": "Warranty Provider Branch", "width": 180},
		{"label": _("Number of Claims"), "fieldname": "number_of_claims", "fieldtype": "Int", "width": 115},
		_currency_column("Total Repair Cost", "total_repair_cost"), _currency_column("Warranty Covered Amount", "warranty_covered_amount"),
		_currency_column("Provider Claim Amount", "provider_claim_amount"), _currency_column("Average Claim Cost", "average_claim_cost"),
	]
	return columns, rows


def warranty_cost_by_vehicle_model(filters=None):
	filters = _filters(filters)
	params = {}
	company_conditions = []
	_conditions_for_company(filters, "w", params, company_conditions)
	warranty_condition = (" and " + " and ".join(company_conditions)) if company_conditions else ""
	if filters.get("vehicle_model"):
		params["vehicle_model"] = filters.vehicle_model
		warranty_condition += " and w.vehicle_model=%(vehicle_model)s"
	if filters.get("provider"):
		params["provider"] = filters.provider
		warranty_condition += " and w.warranty_provider=%(provider)s"
	claim_params = dict(params)
	claim_condition = _conditions(filters, "c", claim_params, {"provider": "custom_warranty_provider", "company": "company"}, "complaint_date")
	if filters.get("vehicle_model"):
		claim_condition += " and coalesce(nullif(w.vehicle_model,''), w.item_code)=%(vehicle_model)s"
	warranty_rows = frappe.db.sql(
		f"""select coalesce(nullif(w.vehicle_model,''), w.item_code) as vehicle_model,
			max(w.item_code) as item_code, count(distinct w.vehicle_master) as warranted_vehicles
		from `tabVehicle Warranty` w where w.status != 'Cancelled' {warranty_condition}
		group by coalesce(nullif(w.vehicle_model,''), w.item_code)""", params, as_dict=True)
	claim_rows = frappe.db.sql(
		f"""select coalesce(nullif(w.vehicle_model,''), w.item_code) as vehicle_model,
			count(*) as warranty_claims, count(distinct c.serial_no) as vehicles_with_claims,
			sum(c.custom_warranty_covered_amount) as total_warranty_cost,
			avg(c.custom_warranty_covered_amount) as average_cost_per_claim, max(c.custom_currency) as currency
		from `tabWarranty Claim` c inner join `tabVehicle Warranty` w on w.name=c.custom_vehicle_warranty
		where c.docstatus < 2 {claim_condition}
		group by coalesce(nullif(w.vehicle_model,''), w.item_code)""", claim_params, as_dict=True)
	by_model = {row.vehicle_model: row for row in warranty_rows}
	for claim_row in claim_rows:
		row = by_model.setdefault(claim_row.vehicle_model, frappe._dict(vehicle_model=claim_row.vehicle_model, warranted_vehicles=0))
		row.update(claim_row)
	rows = list(by_model.values())
	for row in rows:
		row.warranty_claims = cint(row.get("warranty_claims"))
		row.vehicles_with_claims = cint(row.get("vehicles_with_claims"))
		row.claim_rate = flt(row.vehicles_with_claims * 100 / row.warranted_vehicles, 2) if row.warranted_vehicles else 0
		row.average_cost_per_warranted_vehicle = flt(row.get("total_warranty_cost")) / row.warranted_vehicles if row.warranted_vehicles else 0
	rows.sort(key=lambda row: flt(row.get("total_warranty_cost")), reverse=True)
	columns = [
		{"label": _("Vehicle Model / Item"), "fieldname": "vehicle_model", "width": 210},
		{"label": _("Warranted Vehicles"), "fieldname": "warranted_vehicles", "fieldtype": "Int", "width": 125},
		{"label": _("Warranty Claims"), "fieldname": "warranty_claims", "fieldtype": "Int", "width": 110},
		{"label": _("Claim Rate"), "fieldname": "claim_rate", "fieldtype": "Percent", "width": 100},
		_currency_column("Total Warranty Cost", "total_warranty_cost"), _currency_column("Average Warranty Cost per Claim", "average_cost_per_claim", 180),
		_currency_column("Average Warranty Cost per Warranted Vehicle", "average_cost_per_warranted_vehicle", 220),
	]
	return columns, rows


def warranty_cost_by_component(filters=None):
	filters = _filters(filters)
	params = {}
	condition = _conditions(filters, "c", params, {"provider": "custom_warranty_provider", "branch": "custom_warranty_provider_branch", "company": "company"}, "complaint_date")
	if filters.get("coverage_category"):
		params["coverage_category"] = filters.coverage_category
		category_condition = " and x.coverage_category=%(coverage_category)s"
	else:
		category_condition = ""
	rows = frappe.db.sql(
		f"""select x.coverage_category as component, count(distinct x.claim) as number_of_claims,
			count(*) as number_of_parts_services, sum(x.total_cost) as total_cost,
			sum(x.covered_amount) as warranty_covered_cost, avg(x.total_cost) as average_cost,
			max(x.currency) as currency
		from (
			select p.coverage_category, p.parent as claim, p.total_cost, p.covered_amount, c.custom_currency as currency
			from `tabWarranty Claim Part` p inner join `tabWarranty Claim` c on c.name=p.parent
			where p.parenttype='Warranty Claim' and c.docstatus < 2 {condition}
			union all
			select s.coverage_category, s.parent as claim, s.amount as total_cost, s.covered_amount, c.custom_currency as currency
			from `tabWarranty Claim Service` s inner join `tabWarranty Claim` c on c.name=s.parent
			where s.parenttype='Warranty Claim' and c.docstatus < 2 {condition}
		) x where x.coverage_category is not null {category_condition}
		group by x.coverage_category order by total_cost desc""", params, as_dict=True)
	columns = [
		{"label": _("Component / Category"), "fieldname": "component", "fieldtype": "Link", "options": "Warranty Coverage Category", "width": 200},
		{"label": _("Number of Claims"), "fieldname": "number_of_claims", "fieldtype": "Int", "width": 115},
		{"label": _("Number of Parts/Services"), "fieldname": "number_of_parts_services", "fieldtype": "Int", "width": 155},
		_currency_column("Total Cost", "total_cost"), _currency_column("Warranty Covered Cost", "warranty_covered_cost"), _currency_column("Average Cost", "average_cost"),
	]
	return columns, rows


def outside_warranty_repairs(filters=None):
	filters = _filters(filters)
	params = {}
	condition = _conditions(filters, "c", params, {"vin": "serial_no", "provider": "custom_warranty_provider", "branch": "custom_warranty_provider_branch", "company": "company"}, "complaint_date")
	rows = frappe.db.sql(
		f"""select x.claim, x.vin, x.customer, x.provider, x.branch, x.item_type,
			x.part_service, x.qty, x.total, x.covered_amount, x.customer_payable, x.claim_date, x.currency
		from (
			select c.name as claim, c.serial_no as vin, c.customer, c.custom_warranty_provider as provider,
				c.custom_warranty_provider_branch as branch, 'Part' as item_type,
				p.description as part_service, p.qty, p.total_cost as total, p.covered_amount,
				p.customer_payable_amount as customer_payable, c.complaint_date as claim_date, c.custom_currency as currency
			from `tabWarranty Claim Part` p inner join `tabWarranty Claim` c on c.name=p.parent
			where p.parenttype='Warranty Claim' and p.coverage_status in ('Outside Warranty','Partially Covered') and c.docstatus < 2 {condition}
			union all
			select c.name, c.serial_no, c.customer, c.custom_warranty_provider,
				c.custom_warranty_provider_branch, 'Service', s.service_type, s.hours, s.amount,
				s.covered_amount, s.customer_payable_amount, c.complaint_date, c.custom_currency
			from `tabWarranty Claim Service` s inner join `tabWarranty Claim` c on c.name=s.parent
			where s.parenttype='Warranty Claim' and s.coverage_status in ('Outside Warranty','Partially Covered') and c.docstatus < 2 {condition}
		) x order by x.claim_date desc, x.claim""", params, as_dict=True)
	columns = [
		{"label": _("Claim"), "fieldname": "claim", "fieldtype": "Link", "options": "Warranty Claim", "width": 155},
		{"label": _("VIN"), "fieldname": "vin", "fieldtype": "Link", "options": "Serial No", "width": 170},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 160},
		{"label": _("Provider"), "fieldname": "provider", "fieldtype": "Link", "options": "Warranty Provider", "width": 160},
		{"label": _("Branch"), "fieldname": "branch", "fieldtype": "Link", "options": "Warranty Provider Branch", "width": 160},
		{"label": _("Type"), "fieldname": "item_type", "width": 75}, {"label": _("Part/Service"), "fieldname": "part_service", "width": 200},
		{"label": _("Qty / Hours"), "fieldname": "qty", "fieldtype": "Float", "width": 95}, _currency_column("Total", "total"),
		_currency_column("Covered Amount", "covered_amount"), _currency_column("Customer Payable", "customer_payable"),
		{"label": _("Date"), "fieldname": "claim_date", "fieldtype": "Date", "width": 105},
	]
	return columns, rows


def warranty_claim_history_by_vin(filters=None):
	filters = _filters(filters)
	vin = (filters.get("vin") or "").strip()
	if not vin:
		frappe.throw(_("VIN is required."))
	params = {"vin": vin}
	company_conditions = []
	_conditions_for_company(filters, "w", params, company_conditions)
	company_sql = (" and " + " and ".join(company_conditions)) if company_conditions else ""
	warranty = frappe.db.sql(
		f"""select w.name, w.vin, w.vehicle_master, w.vehicle_model, w.customer, w.warranty_provider,
			w.coverage_template, w.warranty_start_date, w.warranty_expiry_date, w.status, w.company
		from `tabVehicle Warranty` w where w.vin=%(vin)s {company_sql}
		order by w.warranty_start_date desc limit 1""", params, as_dict=True)
	if not warranty:
		frappe.throw(_("No accessible Vehicle Warranty was found for this VIN."), frappe.DoesNotExistError)
	warranty = warranty[0]
	coverage = frappe.get_all(
		"Vehicle Warranty Coverage Item",
		filters={"parent": warranty.name, "parenttype": "Vehicle Warranty"},
		fields=["coverage_category", "covered"],
		order_by="idx",
	)
	claim_params = {"vin": vin}
	claim_conditions = []
	_conditions_for_company(filters, "c", claim_params, claim_conditions)
	claim_sql = (" and " + " and ".join(claim_conditions)) if claim_conditions else ""
	rows = frappe.db.sql(
		f"""select c.name as claim, c.complaint_date as claim_date,
			c.custom_warranty_provider_branch as branch, c.complaint, c.custom_diagnosis as diagnosis,
			c.custom_root_cause as root_cause, c.custom_claim_status as status,
			coalesce((select sum(p.total_cost) from `tabWarranty Claim Part` p where p.parent=c.name and p.parenttype='Warranty Claim'),0) as parts_cost,
			coalesce((select sum(s.amount) from `tabWarranty Claim Service` s where s.parent=c.name and s.parenttype='Warranty Claim'),0) as labor_cost,
			c.custom_warranty_covered_amount as warranty_covered, c.custom_customer_payable_amount as customer_payable,
			c.custom_provider_claim_amount as provider_claim_amount, c.custom_currency as currency
		from `tabWarranty Claim` c where c.serial_no=%(vin)s and c.docstatus < 2 {claim_sql}
		order by c.complaint_date, c.creation""", claim_params, as_dict=True)
	columns = [
		{"label": _("Claim"), "fieldname": "claim", "fieldtype": "Link", "options": "Warranty Claim", "width": 155},
		{"label": _("Date"), "fieldname": "claim_date", "fieldtype": "Date", "width": 105},
		{"label": _("Branch"), "fieldname": "branch", "fieldtype": "Link", "options": "Warranty Provider Branch", "width": 150},
		{"label": _("Complaint"), "fieldname": "complaint", "width": 220}, {"label": _("Diagnosis"), "fieldname": "diagnosis", "width": 220},
		{"label": _("Root Cause"), "fieldname": "root_cause", "width": 160}, {"label": _("Status"), "fieldname": "status", "width": 145},
		_currency_column("Parts Cost", "parts_cost"), _currency_column("Labor Cost", "labor_cost"),
		_currency_column("Warranty Covered", "warranty_covered"), _currency_column("Customer Payable", "customer_payable"),
		_currency_column("Provider Claim Amount", "provider_claim_amount"),
	]
	covered = ", ".join(row.coverage_category for row in coverage if row.covered) or _("No covered categories")
	message = frappe.render_template(
		"""<div class="vehicle-history-summary"><b>{{ _("Vehicle") }}:</b> {{ vehicle }} &nbsp; <b>{{ _("Model") }}:</b> {{ model }} &nbsp;
		<b>{{ _("Customer") }}:</b> {{ customer }} &nbsp; <b>{{ _("Warranty") }}:</b> {{ warranty }} ({{ status }})<br>
		<b>{{ _("Provider") }}:</b> {{ provider }} &nbsp; <b>{{ _("Coverage Template") }}:</b> {{ template }} &nbsp;
		<b>{{ _("Start Date") }}:</b> {{ start }} &nbsp; <b>{{ _("Expiry Date") }}:</b> {{ expiry }}<br>
		<b>{{ _("Covered Categories") }}:</b> {{ covered }}</div>""",
		{
			"vehicle": warranty.vehicle_master, "model": warranty.vehicle_model, "customer": warranty.customer,
			"warranty": warranty.name, "status": warranty.status, "provider": warranty.warranty_provider,
			"template": warranty.coverage_template, "start": warranty.warranty_start_date,
			"expiry": warranty.warranty_expiry_date, "covered": covered,
		},
	)
	return columns, rows, message


def provider_performance(filters=None):
	filters = _filters(filters)
	params = {}
	condition = _conditions(filters, "c", params, {"provider": "custom_warranty_provider", "branch": "custom_warranty_provider_branch", "company": "company"}, "complaint_date")
	rows = frappe.db.sql(
		f"""select c.custom_warranty_provider as provider, c.custom_warranty_provider_branch as branch,
			count(distinct c.custom_vehicle_warranty) as assigned_warranties, count(*) as claims_received,
			sum(c.custom_claim_status='Approved') as approved,
			sum(c.custom_claim_status='Partially Approved') as partially_approved,
			sum(c.custom_claim_status='Rejected') as rejected,
			sum(c.custom_claim_status not in ('Closed','Rejected')) as open_claims,
			sum(c.custom_claim_status='Closed') as closed_claims,
			avg(c.custom_total_repair_cost) as average_claim_cost,
			sum(c.custom_provider_claim_amount) as total_provider_claim_amount,
			max(c.custom_currency) as currency
		from `tabWarranty Claim` c where c.docstatus < 2 {condition}
		group by c.custom_warranty_provider, c.custom_warranty_provider_branch
		order by claims_received desc, provider, branch""", params, as_dict=True)
	columns = [
		{"label": _("Provider"), "fieldname": "provider", "fieldtype": "Link", "options": "Warranty Provider", "width": 180},
		{"label": _("Branch"), "fieldname": "branch", "fieldtype": "Link", "options": "Warranty Provider Branch", "width": 180},
		{"label": _("Assigned Warranties"), "fieldname": "assigned_warranties", "fieldtype": "Int", "width": 125},
		{"label": _("Claims Received"), "fieldname": "claims_received", "fieldtype": "Int", "width": 110},
		{"label": _("Approved"), "fieldname": "approved", "fieldtype": "Int", "width": 85},
		{"label": _("Partially Approved"), "fieldname": "partially_approved", "fieldtype": "Int", "width": 125},
		{"label": _("Rejected"), "fieldname": "rejected", "fieldtype": "Int", "width": 85},
		{"label": _("Open Claims"), "fieldname": "open_claims", "fieldtype": "Int", "width": 95},
		{"label": _("Closed Claims"), "fieldname": "closed_claims", "fieldtype": "Int", "width": 100},
		_currency_column("Average Claim Cost", "average_claim_cost"), _currency_column("Total Provider Claim Amount", "total_provider_claim_amount", 175),
	]
	return columns, rows


@frappe.whitelist()
def get_warranty_dashboard(company=None):
	filters = _filters({"company": company} if company else {})
	companies = _report_companies(filters)
	claim_condition, params = _dashboard_company_condition(companies, "c")
	warranty_condition, warranty_params = _dashboard_company_condition(companies, "w")
	status_rows = frappe.db.sql(
		f"""select c.custom_claim_status as status, count(*) as count from `tabWarranty Claim` c
		where c.docstatus < 2 {claim_condition} group by c.custom_claim_status""", params, as_dict=True)
	status_counts = {row.status: row.count for row in status_rows}
	active = frappe.db.sql(
		f"select count(*) from `tabVehicle Warranty` w where w.status='Active' {warranty_condition}", warranty_params
	)[0][0]
	expiring = _count_expiring(companies, 30)
	open_claims = sum(count for status, count in status_counts.items() if status not in {"Closed", "Rejected"})
	kpis = [
		_kpi("Active Warranties", active, "Vehicle Warranty", {"status": "Active"}),
		_kpi("Warranties Expiring in Next 30 Days", expiring, "Vehicle Warranty", {"status": "Active"}),
		_kpi("Open Warranty Claims", open_claims, "Warranty Claim", {"status": ["!=", "Closed"]}),
	]
	for state in ("Under Internal Review", "Need More Information", "Approved", "Partially Approved", "Rejected", "Repair In Progress", "Closed"):
		kpis.append(_kpi(f"{state} Claims" if state in {"Approved", "Partially Approved", "Rejected", "Closed"} else state, status_counts.get(state, 0), "Warranty Claim", {"custom_claim_status": state}))
	financial = _financial_kpis(companies)
	return {"kpis": kpis, "financial_kpis": financial, "charts": _dashboard_charts(companies), "companies": companies}


def _financial_kpis(companies):
	totals = defaultdict(lambda: defaultdict(float))
	for company in companies:
		currency = frappe.db.get_value("Company", company, "default_currency")
		today = _company_dates({company})[company]
		row = frappe.db.sql(
			"""select
				sum(case when complaint_date between %(month_start)s and %(month_end)s then custom_warranty_covered_amount else 0 end) as cost_month,
				sum(case when complaint_date between %(year_start)s and %(year_end)s then custom_warranty_covered_amount else 0 end) as cost_year,
				sum(case when complaint_date between %(month_start)s and %(month_end)s then custom_provider_claim_amount else 0 end) as provider_month,
				sum(case when complaint_date between %(month_start)s and %(month_end)s then custom_customer_payable_amount else 0 end) as customer_month
			from `tabWarranty Claim` where company=%(company)s and docstatus < 2""",
			{"company": company, "month_start": get_first_day(today), "month_end": get_last_day(today), "year_start": today.replace(month=1, day=1), "year_end": today.replace(month=12, day=31)},
			as_dict=True,
		)[0]
		for key in ("cost_month", "cost_year", "provider_month", "customer_month"):
			totals[currency][key] += flt(row.get(key))
	result = []
	for currency, values in totals.items():
		result.extend([
			{"label": _("Total Warranty Cost This Month"), "value": values["cost_month"], "currency": currency},
			{"label": _("Total Warranty Cost This Year"), "value": values["cost_year"], "currency": currency},
			{"label": _("Provider Claim Amount This Month"), "value": values["provider_month"], "currency": currency},
			{"label": _("Customer Payable Amount This Month"), "value": values["customer_month"], "currency": currency},
		])
	return result


def _dashboard_charts(companies):
	condition, params = _dashboard_company_condition(companies, "c")
	monthly = frappe.db.sql(
		f"""select date_format(c.complaint_date, '%%Y-%%m') as label, count(*) as claims,
			sum(c.custom_warranty_covered_amount) as cost
		from `tabWarranty Claim` c where c.docstatus < 2 and c.complaint_date >= date_sub(curdate(), interval 12 month) {condition}
		group by date_format(c.complaint_date, '%%Y-%%m') order by label""", params, as_dict=True)
	provider = _chart_group("c.custom_warranty_provider", "provider", condition, params)
	branch = _chart_group("c.custom_warranty_provider_branch", "branch", condition, params)
	models = frappe.db.sql(
		f"""select coalesce(nullif(w.vehicle_model,''),w.item_code) as label,
			sum(c.custom_warranty_covered_amount) as value from `tabWarranty Claim` c
		inner join `tabVehicle Warranty` w on w.name=c.custom_vehicle_warranty
		where c.docstatus < 2 {condition} group by label order by value desc limit 10""", params, as_dict=True)
	components = frappe.db.sql(
		f"""select x.label, sum(x.value) as value from (
			select p.coverage_category as label, sum(p.total_cost) as value from `tabWarranty Claim Part` p
			inner join `tabWarranty Claim` c on c.name=p.parent where c.docstatus < 2 {condition} group by p.coverage_category
			union all select s.coverage_category, sum(s.amount) from `tabWarranty Claim Service` s
			inner join `tabWarranty Claim` c on c.name=s.parent where c.docstatus < 2 {condition} group by s.coverage_category
		) x where x.label is not null group by x.label order by value desc limit 10""", params, as_dict=True)
	covered = frappe.db.sql(
		f"""select sum(c.custom_warranty_covered_amount) as covered,
			sum(c.custom_customer_payable_amount) as customer from `tabWarranty Claim` c where c.docstatus < 2 {condition}""", params, as_dict=True)[0]
	return [
		{"title": _("Warranty Cost by Month"), "type": "line", "labels": [row.label for row in monthly], "datasets": [{"name": _("Warranty Cost"), "values": [flt(row.cost) for row in monthly]}]},
		{"title": _("Claims by Month"), "type": "bar", "labels": [row.label for row in monthly], "datasets": [{"name": _("Claims"), "values": [row.claims for row in monthly]}]},
		_chart("Claims by Provider", provider), _chart("Claims by Branch", branch),
		_chart("Top Vehicle Models by Warranty Cost", models), _chart("Top Failure/Coverage Categories", components),
		{"title": _("Covered vs Customer-Payable Cost"), "type": "donut", "labels": [_('Warranty Covered'), _('Customer Payable')], "datasets": [{"values": [flt(covered.covered), flt(covered.customer)]}]},
	]


def _chart_group(field, label, condition, params):
	return frappe.db.sql(
		f"""select {field} as label, count(*) as value from `tabWarranty Claim` c
		where c.docstatus < 2 and {field} is not null {condition}
		group by {field} order by value desc limit 10""", params, as_dict=True)


def _chart(title, rows):
	return {"title": _(title), "type": "bar", "labels": [row.label for row in rows], "datasets": [{"name": _("Claims / Cost"), "values": [flt(row.value) for row in rows]}]}


def _kpi(label, value, doctype, filters):
	return {"label": _(label), "value": value, "doctype": doctype, "filters": filters}


def _company_dates(companies, now_utc=None):
	instant = now_utc or datetime.now(timezone.utc)
	return {company: instant.astimezone(ZoneInfo(get_company_warranty_timezone(company))).date() for company in companies}


def _report_companies(filters):
	permitted = get_permitted_documents("Company")
	if filters.get("company"):
		if permitted and filters.company not in permitted:
			frappe.throw(_("You are not permitted to report on this Company."), frappe.PermissionError)
		return [filters.company]
	companies = permitted or frappe.get_all("Company", pluck="name")
	return [company for company in companies if frappe.db.get_value("Company", company, "custom_warranty_timezone")]


def _dashboard_company_condition(companies, alias):
	if not companies:
		return " and 1=0", {}
	return f" and {alias}.company in %(companies)s", {"companies": tuple(companies)}


def _count_expiring(companies, days):
	total = 0
	for company, today in _company_dates(set(companies)).items():
		total += frappe.db.count("Vehicle Warranty", {"company": company, "status": "Active", "warranty_expiry_date": ["between", [today, add_days(today, days)]]})
	return total


@frappe.whitelist()
def get_vehicle_warranty_summary(vehicle_master=None, vin=None):
	_filters()
	if not vehicle_master and not vin:
		frappe.throw(_("Vehicle Master or VIN is required."))
	vehicle = frappe.db.get_value(
		"Vehicle Master", vehicle_master or {"vin": vin}, ["name", "vin", "company", "customer", "item_name"], as_dict=True
	)
	if not vehicle:
		frappe.throw(_("Vehicle Master was not found."), frappe.DoesNotExistError)
	permitted = get_permitted_documents("Company")
	if permitted and vehicle.company not in permitted:
		frappe.throw(_("You are not permitted to access this vehicle."), frappe.PermissionError)
	warranty = frappe.db.get_value(
		"Vehicle Warranty", {"vehicle_master": vehicle.name},
		["name", "status", "warranty_provider", "warranty_start_date", "warranty_expiry_date", "coverage_template"],
		order_by="warranty_start_date desc", as_dict=True,
	)
	claim_totals = frappe.db.sql(
		"""select count(*) as number_of_claims, sum(custom_total_repair_cost) as total_warranty_cost,
			sum(custom_claim_status not in ('Closed','Rejected')) as open_claims
		from `tabWarranty Claim` where custom_vehicle_master=%s and docstatus < 2""", vehicle.name, as_dict=True)[0]
	return {
		"vehicle": vehicle,
		"warranty": warranty,
		"number_of_claims": cint(claim_totals.number_of_claims),
		"total_warranty_cost": flt(claim_totals.total_warranty_cost),
		"open_claims": cint(claim_totals.open_claims),
	}
