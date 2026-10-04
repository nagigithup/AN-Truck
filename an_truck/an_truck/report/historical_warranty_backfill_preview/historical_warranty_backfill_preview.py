import frappe
from frappe import _

from an_truck.warranty.backfill import preview_historical_warranties


def execute(filters=None):
	columns = [
		{"label": _("VIN"), "fieldname": "vin", "fieldtype": "Link", "options": "Serial No", "width": 180},
		{"label": _("Vehicle Master"), "fieldname": "vehicle_master", "fieldtype": "Link", "options": "Vehicle Master", "width": 160},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 160},
		{"label": _("Delivery Source"), "fieldname": "delivery_source", "width": 145},
		{"label": _("Delivery Date"), "fieldname": "delivery_date", "fieldtype": "Date", "width": 105},
		{"label": _("Warranty Provider"), "fieldname": "warranty_provider", "fieldtype": "Link", "options": "Warranty Provider", "width": 175},
		{"label": _("Provider Contract"), "fieldname": "provider_contract", "fieldtype": "Link", "options": "Warranty Provider Contract", "width": 155},
		{"label": _("Coverage Template"), "fieldname": "coverage_template", "fieldtype": "Link", "options": "Warranty Coverage Template", "width": 170},
		{"label": _("Calculated Start Date"), "fieldname": "calculated_start_date", "fieldtype": "Date", "width": 135},
		{"label": _("Calculated Expiry Date"), "fieldname": "calculated_expiry_date", "fieldtype": "Date", "width": 140},
		{"label": _("Result"), "fieldname": "result", "width": 190},
		{"label": _("Eligibility / Reason"), "fieldname": "eligibility", "width": 260},
	]
	return columns, preview_historical_warranties(filters)
