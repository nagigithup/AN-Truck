import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("VIN"), "fieldname": "vin", "fieldtype": "Link", "options": "Serial No", "width": 170},
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 140},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 180},
		{"label": _("Status"), "fieldname": "vehicle_status", "fieldtype": "Data", "width": 120},
		{"label": _("Import File"), "fieldname": "vehicle_import_file", "fieldtype": "Link", "options": "Vehicle Import File", "width": 160},
		{"label": _("Purchase Receipt"), "fieldname": "purchase_receipt", "fieldtype": "Link", "options": "Purchase Receipt", "width": 160},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 160},
		{"label": _("Warehouse"), "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 150},
		{"label": _("Receipt Date"), "fieldname": "receipt_date", "fieldtype": "Date", "width": 110},
		{"label": _("Purchase Cost"), "fieldname": "purchase_valuation_rate", "fieldtype": "Currency", "options": "cost_currency", "width": 120},
		{"label": _("Landed Cost"), "fieldname": "landed_cost_added", "fieldtype": "Currency", "options": "cost_currency", "width": 120},
		{"label": _("Final Cost"), "fieldname": "final_vehicle_cost", "fieldtype": "Currency", "options": "cost_currency", "width": 120},
	]


def get_data(filters):
	query_filters = {"disabled": 0}
	for fieldname in ("company", "supplier", "vehicle_import_file", "item_code", "vehicle_status"):
		if filters.get(fieldname):
			query_filters[fieldname] = filters[fieldname]
	if filters.get("from_date") and filters.get("to_date"):
		query_filters["receipt_date"] = ["between", [filters.from_date, filters.to_date]]
	elif filters.get("from_date"):
		query_filters["receipt_date"] = [">=", filters.from_date]
	elif filters.get("to_date"):
		query_filters["receipt_date"] = ["<=", filters.to_date]

	return frappe.get_all(
		"Vehicle Master",
		filters=query_filters,
		fields=[
			"vin",
			"item_code",
			"item_name",
			"vehicle_status",
			"vehicle_import_file",
			"purchase_receipt",
			"supplier",
			"warehouse",
			"receipt_date",
			"purchase_valuation_rate",
			"landed_cost_added",
			"final_vehicle_cost",
			"cost_currency",
		],
		order_by="receipt_date desc, modified desc",
	)
