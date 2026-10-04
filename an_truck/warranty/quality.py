import frappe
from frappe import _
from frappe.core.doctype.user_permission.user_permission import get_permitted_documents

from an_truck.warranty.reporting import require_internal_reporting_access


def get_warranty_data_quality(filters=None):
	require_internal_reporting_access()
	filters = frappe._dict(filters or {})
	issues = []
	company_sql = ""
	params = {}
	permitted_companies = get_permitted_documents("Company")
	if filters.get("company"):
		if permitted_companies and filters.company not in permitted_companies:
			frappe.throw(
				_("You are not permitted to review Company {0}.").format(filters.company),
				frappe.PermissionError,
			)
		company_sql = " and {alias}.company=%(company)s"
		params["company"] = filters.company
	elif permitted_companies:
		company_sql = " and {alias}.company in %(permitted_companies)s"
		params["permitted_companies"] = tuple(permitted_companies)

	def add_query(severity, issue_type, doctype, sql, query_params=None):
		for row in frappe.db.sql(sql, query_params or params, as_dict=True):
			issues.append({
				"severity": severity, "issue_type": issue_type, "document_type": doctype,
				"document_name": row.name, "vin": row.get("vin"), "company": row.get("company"),
				"details": row.get("details") or issue_type,
			})

	add_query("Warning", "Sold/delivered VIN without Vehicle Warranty", "Vehicle Master", f"""
		select v.name, v.vin, v.company, 'Historical warranty review required' as details
		from `tabVehicle Master` v left join `tabVehicle Warranty` w on w.vehicle_master=v.name
		where v.disabled=0 and v.vehicle_status in ('Sold','Delivered') and w.name is null
		{company_sql.format(alias='v')}""")
	add_query("Critical", "Active warranty without provider", "Vehicle Warranty", f"""
		select w.name,w.vin,w.company,'Warranty Provider is missing' details from `tabVehicle Warranty` w
		where w.status='Active' and (w.warranty_provider is null or w.warranty_provider='') {company_sql.format(alias='w')}""")
	add_query("Critical", "Active warranty without coverage snapshot", "Vehicle Warranty", f"""
		select w.name,w.vin,w.company,'Coverage snapshot has no rows' details from `tabVehicle Warranty` w
		left join `tabVehicle Warranty Coverage Item` ci on ci.parent=w.name and ci.parenttype='Vehicle Warranty'
		where w.status='Active' {company_sql.format(alias='w')} group by w.name having count(ci.name)=0""")
	add_query("Critical", "Warranty without customer", "Vehicle Warranty", f"""
		select w.name,w.vin,w.company,'Customer is missing' details from `tabVehicle Warranty` w
		where (w.customer is null or w.customer='') {company_sql.format(alias='w')}""")
	add_query("Critical", "Warranty without valid Vehicle Master", "Vehicle Warranty", f"""
		select w.name,w.vin,w.company,'Vehicle Master link is missing or invalid' details from `tabVehicle Warranty` w
		left join `tabVehicle Master` v on v.name=w.vehicle_master where v.name is null {company_sql.format(alias='w')}""")
	add_query("Critical", "VIN mismatch between warranty and vehicle/serial", "Vehicle Warranty", f"""
		select w.name,w.vin,w.company,concat('Vehicle VIN: ',coalesce(v.vin,'MISSING'),'; Serial: ',coalesce(s.name,'MISSING')) details
		from `tabVehicle Warranty` w left join `tabVehicle Master` v on v.name=w.vehicle_master
		left join `tabSerial No` s on s.name=w.vin
		where (v.name is null or v.vin<>w.vin or s.name is null) {company_sql.format(alias='w')}""")
	add_query("Critical", "Duplicate active warranties", "Vehicle Warranty", f"""
		select min(w.name) name,w.vin,max(w.company) company,concat(count(*),' active warranties') details
		from `tabVehicle Warranty` w where w.status='Active' {company_sql.format(alias='w')}
		group by w.vin having count(*)>1""")
	add_query("Critical", "Warranty start date after expiry", "Vehicle Warranty", f"""
		select w.name,w.vin,w.company,concat(w.warranty_start_date,' > ',w.warranty_expiry_date) details
		from `tabVehicle Warranty` w where w.warranty_start_date>w.warranty_expiry_date {company_sql.format(alias='w')}""")
	add_query("Critical", "Warranty linked to wrong provider contract", "Vehicle Warranty", f"""
		select w.name,w.vin,w.company,concat('Warranty provider ',w.warranty_provider,'; contract provider ',coalesce(pc.warranty_provider,'MISSING')) details
		from `tabVehicle Warranty` w left join `tabWarranty Provider Contract` pc on pc.name=w.provider_contract
		where (pc.name is null or pc.warranty_provider<>w.warranty_provider) {company_sql.format(alias='w')}""")
	add_query("Warning", "Provider contract invalid for warranty start date", "Vehicle Warranty", f"""
		select w.name,w.vin,w.company,concat('Contract status/period does not cover ',w.warranty_start_date) details
		from `tabVehicle Warranty` w inner join `tabWarranty Provider Contract` pc on pc.name=w.provider_contract
		where (pc.status not in ('Active','Expired') or w.warranty_start_date<pc.start_date or (pc.end_date is not null and w.warranty_start_date>pc.end_date))
		{company_sql.format(alias='w')}""")
	add_query("Critical", "Claim provider inconsistent with warranty", "Warranty Claim", f"""
		select c.name,c.serial_no vin,c.company,concat(c.custom_warranty_provider,' != ',coalesce(w.warranty_provider,'MISSING')) details
		from `tabWarranty Claim` c left join `tabVehicle Warranty` w on w.name=c.custom_vehicle_warranty
		where w.name is not null and c.custom_warranty_provider<>w.warranty_provider {company_sql.format(alias='c')}""")
	add_query("Critical", "Claim branch does not belong to provider", "Warranty Claim", f"""
		select c.name,c.serial_no vin,c.company,concat('Branch provider ',coalesce(b.warranty_provider,'MISSING')) details
		from `tabWarranty Claim` c left join `tabWarranty Provider Branch` b on b.name=c.custom_warranty_provider_branch
		where c.custom_warranty_provider_branch is not null and (b.name is null or b.warranty_provider<>c.custom_warranty_provider)
		{company_sql.format(alias='c')}""")
	add_query("Critical", "Claim without Vehicle Warranty", "Warranty Claim", f"""
		select c.name,c.serial_no vin,c.company,'Vehicle Warranty link is missing or invalid' details
		from `tabWarranty Claim` c left join `tabVehicle Warranty` w on w.name=c.custom_vehicle_warranty
		where w.name is null {company_sql.format(alias='c')}""")
	add_query("Critical", "Claim financial totals inconsistent with child rows", "Warranty Claim", f"""
		select c.name,c.serial_no vin,c.company,'Stored claim totals do not reconcile with parts/services/other charges' details
		from `tabWarranty Claim` c
		left join (select parent,sum(total_cost) total,sum(covered_amount) covered,sum(customer_payable_amount) customer from `tabWarranty Claim Part` where parenttype='Warranty Claim' group by parent) p on p.parent=c.name
		left join (select parent,sum(amount) total,sum(covered_amount) covered,sum(customer_payable_amount) customer from `tabWarranty Claim Service` where parenttype='Warranty Claim' group by parent) s on s.parent=c.name
		where (abs(c.custom_total_repair_cost-(coalesce(p.total,0)+coalesce(s.total,0)+coalesce(c.custom_other_charges,0)))>0.01
		or abs(c.custom_warranty_covered_amount-(coalesce(p.covered,0)+coalesce(s.covered,0)+coalesce(c.custom_other_covered_amount,0)))>0.01
		or abs(c.custom_customer_payable_amount-(coalesce(p.customer,0)+coalesce(s.customer,0)+coalesce(c.custom_other_charges,0)-coalesce(c.custom_other_covered_amount,0)))>0.01
		or abs(c.custom_provider_claim_amount-c.custom_warranty_covered_amount)>0.01) {company_sql.format(alias='c')}""")
	add_query("Critical", "Non-private Warranty Claim attachment", "Warranty Claim", f"""
		select c.name,c.serial_no vin,c.company,concat('File ',f.name,' is public') details
		from `tabFile` f inner join `tabWarranty Claim` c on c.name=f.attached_to_name
		where f.attached_to_doctype='Warranty Claim' and f.is_private=0 {company_sql.format(alias='c')}""")

	for row in frappe.db.sql("""select a.name,a.warranty_provider,a.warranty_provider_branch,
		p.status provider_status,p.active provider_active,b.active branch_active,b.warranty_provider branch_provider
		from `tabWarranty Provider User Access` a
		left join `tabWarranty Provider` p on p.name=a.warranty_provider
		left join `tabWarranty Provider Branch` b on b.name=a.warranty_provider_branch
		where a.active=1 and (p.name is null or p.active=0 or p.status!='Active' or
		(a.all_branches=0 and (b.name is null or b.active=0 or b.warranty_provider<>a.warranty_provider)))""", as_dict=True):
		issues.append({"severity":"Critical", "issue_type":"Active provider access linked to inactive provider/branch",
			"document_type":"Warranty Provider User Access", "document_name":row.name, "vin":None, "company":None,
			"details": _("Provider or fixed branch is inactive, missing, or inconsistent.")})

	severity_order = {"Critical": 0, "Warning": 1, "Information": 2}
	issues.sort(key=lambda row: (severity_order[row["severity"]], row["issue_type"], row["document_name"] or ""))
	return issues
