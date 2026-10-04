from frappe import _

from an_truck.warranty.quality import get_warranty_data_quality


def execute(filters=None):
	columns = [
		{"label": _("Severity"), "fieldname": "severity", "width": 90},
		{"label": _("Issue"), "fieldname": "issue_type", "width": 260},
		{"label": _("Document Type"), "fieldname": "document_type", "width": 165},
		{"label": _("Document"), "fieldname": "document_name", "fieldtype": "Dynamic Link", "options": "document_type", "width": 180},
		{"label": _("VIN"), "fieldname": "vin", "width": 180},
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 150},
		{"label": _("Details"), "fieldname": "details", "width": 320},
	]
	return columns, get_warranty_data_quality(filters)
