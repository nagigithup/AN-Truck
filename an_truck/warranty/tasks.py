import frappe
from frappe import _
from frappe.utils import add_days, getdate, now_datetime

from an_truck.warranty.timezone import get_company_local_date


def expire_vehicle_warranties(now_utc=None, batch_size=500):
	"""Expire active warranties using each Company's local calendar date.

	A warranty remains active throughout its expiry date. Companies are isolated by
	database savepoints so bad configuration or an update failure does not prevent
	other companies from being processed.
	"""
	summary = {"companies": 0, "expired": 0, "failed_companies": []}
	companies = frappe.get_all(
		"Vehicle Warranty",
		filters={"status": "Active"},
		pluck="company",
		distinct=True,
	)
	for index, company in enumerate(filter(None, companies)):
		savepoint = f"warranty_expiry_company_{index}"
		frappe.db.savepoint(savepoint)
		try:
			local_date = get_company_local_date(company, now_utc=now_utc)
			company_total = _expire_company_warranties(company, local_date, batch_size)
			summary["companies"] += 1
			summary["expired"] += company_total
		except Exception:
			frappe.db.rollback(save_point=savepoint)
			summary["failed_companies"].append(company)
			frappe.log_error(
				title=f"Vehicle warranty expiry failed for {company}",
				message=frappe.get_traceback(),
			)
	return summary


def send_warranty_expiry_reminders(now_utc=None):
	"""Create one internal Notification Log per user/warranty/30-or-7-day milestone."""
	users = frappe.db.sql_list("""select distinct u.name from `tabUser` u
		inner join `tabHas Role` r on r.parent=u.name and r.parenttype='User'
		where u.enabled=1 and u.user_type='System User'
		and r.role in ('AN Truck Manager','AN Truck Warranty Manager','AN Truck Warranty User')""")
	if not users:
		return {"created": 0, "warranties": 0}
	company_permissions = {
		user: set(frappe.get_all(
			"User Permission", filters={"user": user, "allow": "Company"}, pluck="for_value"
		))
		for user in users
	}
	created = 0
	warranty_count = 0
	companies = frappe.get_all("Vehicle Warranty", filters={"status": "Active"}, pluck="company", distinct=True)
	for company in filter(None, companies):
		try:
			local_date = get_company_local_date(company, now_utc=now_utc)
			for days in (30, 7):
				expiry_date = add_days(local_date, days)
				warranties = frappe.get_all(
					"Vehicle Warranty",
					filters={"company": company, "status": "Active", "warranty_expiry_date": expiry_date},
					fields=["name", "vin", "warranty_expiry_date"],
				)
				warranty_count += len(warranties)
				for warranty in warranties:
					subject = f"Warranty expiry reminder | {days} | {warranty.warranty_expiry_date}"
					for user in users:
						if company_permissions[user] and company not in company_permissions[user]:
							continue
						if frappe.db.exists("Notification Log", {
							"for_user": user, "document_type": "Vehicle Warranty",
							"document_name": warranty.name, "subject": subject,
						}):
							continue
						frappe.get_doc({
							"doctype": "Notification Log", "for_user": user, "from_user": "Administrator",
							"type": "Alert", "document_type": "Vehicle Warranty", "document_name": warranty.name,
							"subject": subject,
							"title": _("Warranty {0} expires in {1} days").format(warranty.name, days),
							"description": _("VIN {0} expires on {1}.").format(warranty.vin, warranty.warranty_expiry_date),
							"link": f"/app/vehicle-warranty/{warranty.name}",
						}).insert(ignore_permissions=True)
						created += 1
		except Exception:
			frappe.log_error(title=f"Warranty expiry reminder failed for {company}", message=frappe.get_traceback())
	return {"created": created, "warranties": warranty_count}


def _expire_company_warranties(company, local_date, batch_size):
	total = 0
	while True:
		rows = frappe.get_all(
			"Vehicle Warranty",
			filters={
				"company": company,
				"status": "Active",
				"warranty_expiry_date": ["<", getdate(local_date)],
			},
			fields=["name", "vin"],
			limit=batch_size,
		)
		if not rows:
			break
		names = [row.name for row in rows]
		placeholders = ", ".join(["%s"] * len(names))
		frappe.db.sql(
			f"""update `tabVehicle Warranty`
			set status='Expired', active_vin_key=null, modified=%s, modified_by=%s
			where name in ({placeholders}) and status='Active'""",
			[now_datetime(), frappe.session.user, *names],
		)
		for vin in {row.vin for row in rows if row.vin}:
			frappe.db.set_value("Serial No", vin, "warranty_expiry_date", None, update_modified=False)
		total += len(rows)
	return total
