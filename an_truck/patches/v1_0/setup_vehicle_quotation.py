"""Add optional quotation references; leave existing quotations and vehicles untouched."""
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields({
		"Quotation Item": [
			{"fieldname": "custom_vehicle_specification_template", "label": "Vehicle Specification Template",
			 "fieldtype": "Link", "options": "Vehicle Specification Template", "insert_after": "item_name"},
			{"fieldname": "custom_vehicle_warranty_terms", "label": "Vehicle Warranty Terms", "fieldtype": "Small Text",
			 "insert_after": "custom_vehicle_specification_template"},
			{"fieldname": "custom_vehicle_delivery_terms", "label": "Vehicle Delivery Conditions", "fieldtype": "Small Text",
			 "insert_after": "custom_vehicle_warranty_terms"},
			{"fieldname": "custom_vehicle_quotation_snapshot", "label": "Vehicle Quotation Snapshot", "fieldtype": "Long Text",
			 "hidden": 1, "read_only": 1, "no_copy": 1, "print_hide": 1, "insert_after": "custom_vehicle_delivery_terms"},
		],
		"Quotation": [
			{"fieldname": "custom_vehicle_quotation_notes", "label": "Notes", "fieldtype": "Small Text", "insert_after": "terms"},
			{"fieldname": "custom_company_bank_account", "label": "Company Bank Account", "fieldtype": "Link",
			 "options": "Bank Account", "insert_after": "company"},
			{"fieldname": "custom_vehicle_quotation_context", "label": "Vehicle Quotation Context", "fieldtype": "Long Text",
			 "hidden": 1, "read_only": 1, "no_copy": 1, "print_hide": 1, "insert_after": "custom_company_bank_account"},
		],
	}, update=True)
	from pathlib import Path
	from an_truck.vehicle_quotation import PRINT_FORMAT
	path = Path(frappe.get_app_path("an_truck", "print_formats", "unified_vehicle_quotation.html"))
	if not frappe.db.exists("Print Format", PRINT_FORMAT):
		frappe.get_doc({"doctype": "Print Format", "name": PRINT_FORMAT, "doc_type": "Quotation",
			"module": "AN Truck", "standard": "No", "custom_format": 1, "print_format_type": "Jinja",
			"pdf_generator": "chrome",
			"html": path.read_text(), "disabled": 0}).insert()
