import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{"label": _("Import File"), "fieldname": "name", "fieldtype": "Link", "options": "Vehicle Import File", "width": 160},
		{"label": _("Title"), "fieldname": "import_title", "fieldtype": "Data", "width": 180},
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 140},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 160},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
		{"label": _("Expected"), "fieldname": "total_expected_vehicles", "fieldtype": "Float", "width": 100},
		{"label": _("Received"), "fieldname": "total_received_vehicles", "fieldtype": "Float", "width": 100},
		{"label": _("In Stock"), "fieldname": "vehicles_in_stock", "fieldtype": "Float", "width": 100},
		{"label": _("Remaining"), "fieldname": "vehicles_remaining", "fieldtype": "Float", "width": 100},
		{"label": _("Supplier Amount"), "fieldname": "total_supplier_amount", "fieldtype": "Currency", "options": "supplier_currency", "width": 130},
		{"label": _("Company Amount"), "fieldname": "total_company_amount", "fieldtype": "Currency", "options": "company_currency", "width": 130},
		{"label": _("ETA"), "fieldname": "eta_date", "fieldtype": "Date", "width": 100},
	]


def get_data(filters):
	query_filters = {}
	for fieldname in ("company", "supplier", "status"):
		if filters.get(fieldname):
			query_filters[fieldname] = filters[fieldname]
	if filters.get("from_eta") and filters.get("to_eta"):
		query_filters["eta_date"] = ["between", [filters.from_eta, filters.to_eta]]
	elif filters.get("from_eta"):
		query_filters["eta_date"] = [">=", filters.from_eta]
	elif filters.get("to_eta"):
		query_filters["eta_date"] = ["<=", filters.to_eta]

	return frappe.get_all(
		"Vehicle Import File",
		filters=query_filters,
		fields=[
			"name",
			"import_title",
			"company",
			"supplier",
			"status",
			"total_expected_vehicles",
			"total_received_vehicles",
			"vehicles_in_stock",
			"vehicles_remaining",
			"total_supplier_amount",
			"supplier_currency",
			"total_company_amount",
			"company_currency",
			"eta_date",
		],
		order_by="modified desc",
	)
