"""Restore only the named quotation format; no business records are updated."""
from pathlib import Path

import frappe


def execute():
	from an_truck.vehicle_quotation import PRINT_FORMAT
	if not frappe.db.exists("Print Format", PRINT_FORMAT):
		from an_truck.patches.v1_0.setup_vehicle_quotation import execute as setup
		setup()
	doc = frappe.get_doc("Print Format", PRINT_FORMAT)
	doc.html = Path(frappe.get_app_path("an_truck", "print_formats", "unified_vehicle_quotation.html")).read_text()
	doc.pdf_generator = "chrome"
	# Frappe's Chrome adapter reads margins from this field/longhand rules;
	# @page inside HTML alone otherwise leaves its implicit 15 mm margins.
	doc.css = "@page { size: A4; margin: 0mm; }\n.print-format { margin-top: 0mm; margin-bottom: 0mm; margin-left: 0mm; margin-right: 0mm; }"
	previous = frappe.flags.in_patch
	try:
		frappe.flags.in_patch = True
		doc.save()
	finally:
		frappe.flags.in_patch = previous
