from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import frappe
from frappe import _


COMPANY_TIMEZONE_FIELD = "custom_warranty_timezone"


def validate_company_warranty_timezone(doc, method=None):
	value = (doc.get(COMPANY_TIMEZONE_FIELD) or "").strip()
	if not value:
		return
	try:
		ZoneInfo(value)
	except ZoneInfoNotFoundError:
		frappe.throw(_("{0} is not a valid IANA time zone.").format(value))


def get_company_warranty_timezone(company, required=True):
	value = frappe.db.get_value("Company", company, COMPANY_TIMEZONE_FIELD)
	value = (value or "").strip()
	if not value:
		if required:
			frappe.throw(
				_("Configure Warranty Processing Time Zone on Company {0}.").format(company)
			)
		return None
	try:
		ZoneInfo(value)
	except ZoneInfoNotFoundError:
		if required:
			frappe.throw(_("Company {0} has an invalid warranty time zone: {1}.").format(company, value))
		return None
	return value


def get_company_local_date(company, now_utc=None):
	"""Return the company's calendar date without converting warranty DATE fields."""
	time_zone = get_company_warranty_timezone(company)
	instant = now_utc or datetime.now(timezone.utc)
	if instant.tzinfo is None:
		instant = instant.replace(tzinfo=timezone.utc)
	return instant.astimezone(ZoneInfo(time_zone)).date()
