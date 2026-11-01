"""Install the supplied custom format without overwriting site customizations."""
import json

import frappe


def execute():
	if frappe.db.exists("Print Format", "sale invoices"):
		return
	# This format uses KSA Compliance's Phase 1 settings and QR helper. Keep
	# sites that do not use that optional app unaffected.
	if not all(frappe.db.exists("DocType", name) for name in (
		"ZATCA Phase 1 Business Settings", "Additional Buyer IDs"
	)) or not frappe.db.exists("Module Def", "KSA Compliance"):
		return
	with open(frappe.get_app_path("an_truck", "print_formats", "sale_invoices.json"), encoding="utf-8") as handle:
		values = json.load(handle)
	frappe.get_doc(values).insert()
