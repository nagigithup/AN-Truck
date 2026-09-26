from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

CHINESE_SHARE = 0.49
SHOWROOM_SHARE = 0.51
DISTRIBUTION_ROLES = ("System Manager", "AN Truck Manager")
SOLD_STATUSES = ("Sold", "Delivered")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	return get_columns(), data, None, None, get_report_summary(data)


def calculate_partner_shares(final_cost, selling_rate, precision=2):
	profit_loss = flt(flt(selling_rate) - flt(final_cost), precision)
	chinese_share = flt(profit_loss * CHINESE_SHARE, precision)
	# Derive the second share from the rounded total so the two shares always reconcile.
	showroom_share = flt(profit_loss - chinese_share, precision)
	return profit_loss, chinese_share, showroom_share


def get_columns():
	return [
		{"label": _("VIN"), "fieldname": "vehicle_master", "fieldtype": "Link", "options": "Vehicle Master", "width": 135},
		{"label": _("Vehicle / Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 130},
		{"label": _("Vehicle Model"), "fieldname": "model", "fieldtype": "Data", "width": 115},
		{"label": _("Vehicle Import File"), "fieldname": "vehicle_import_file", "fieldtype": "Link", "options": "Vehicle Import File", "width": 150},
		{"label": _("Vehicle Status"), "fieldname": "vehicle_status", "fieldtype": "Data", "width": 110},
		{"label": _("Sale Date"), "fieldname": "sale_date", "fieldtype": "Date", "width": 105},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 140},
		{"label": _("Sales Invoice"), "fieldname": "sales_invoice", "fieldtype": "Link", "options": "Sales Invoice", "width": 145},
		{"label": _("Delivery Note"), "fieldname": "delivery_note", "fieldtype": "Link", "options": "Delivery Note", "width": 135},
		{"label": _("Purchase Valuation Rate"), "fieldname": "purchase_valuation_rate", "fieldtype": "Currency", "options": "cost_currency", "width": 145},
		{"label": _("Landed Cost Added"), "fieldname": "landed_cost_added", "fieldtype": "Currency", "options": "cost_currency", "width": 125},
		{"label": _("Final Valuation Rate"), "fieldname": "final_valuation_rate", "fieldtype": "Currency", "options": "cost_currency", "width": 135},
		{"label": _("Selling Rate"), "fieldname": "selling_rate", "fieldtype": "Currency", "options": "cost_currency", "width": 120},
		{"label": _("Profit / Loss"), "fieldname": "profit_loss", "fieldtype": "Currency", "options": "cost_currency", "width": 120},
		{"label": _("Chinese Partner Share (49%)"), "fieldname": "chinese_share", "fieldtype": "Currency", "options": "cost_currency", "width": 165},
		{"label": _("Abu Turki / Showroom Share (51%)"), "fieldname": "showroom_share", "fieldtype": "Currency", "options": "cost_currency", "width": 190},
		{"label": _("Profit Distribution Status"), "fieldname": "distribution_status", "fieldtype": "Data", "width": 145},
		{"label": _("Distributed On"), "fieldname": "profit_distributed_on", "fieldtype": "Datetime", "width": 155},
		{"label": _("Distributed By"), "fieldname": "profit_distributed_by", "fieldtype": "Link", "options": "User", "width": 155},
	]


def get_data(filters):
	conditions = ["vm.disabled = 0"]
	values = {}

	filter_map = {
		"vin": "vm.name",
		"vehicle": "vm.item_code",
		"customer": "vm.customer",
		"vehicle_import_file": "vm.vehicle_import_file",
		"vehicle_status": "vm.vehicle_status",
	}
	for fieldname, column in filter_map.items():
		if filters.get(fieldname):
			conditions.append(f"{column} = %({fieldname})s")
			values[fieldname] = filters.get(fieldname)

	if filters.get("from_date"):
		conditions.append("si.posting_date >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("si.posting_date <= %(to_date)s")
		values["to_date"] = filters.to_date

	distribution_status = filters.get("distribution_status") or "Not Distributed"
	if distribution_status == "Not Distributed":
		conditions.append("COALESCE(vm.profit_distributed, 0) = 0")
	elif distribution_status == "Distributed":
		conditions.append("COALESCE(vm.profit_distributed, 0) = 1")

	rows = frappe.db.sql(
		f"""
			SELECT
				vm.name AS vehicle_master,
				vm.vin,
				vm.item_code,
				vm.model,
				vm.vehicle_import_file,
				vm.vehicle_status,
				vm.customer,
				vm.sales_invoice,
				vm.delivery_note,
				vm.purchase_valuation_rate,
				vm.landed_cost_added,
				vm.final_valuation_rate,
				vm.selling_rate,
				vm.cost_currency,
				COALESCE(vm.profit_distributed, 0) AS profit_distributed,
				vm.profit_distributed_on,
				vm.profit_distributed_by,
				si.posting_date AS sale_date,
				si.docstatus AS sales_invoice_docstatus
			FROM `tabVehicle Master` vm
			LEFT JOIN `tabSales Invoice` si
				ON si.name = vm.sales_invoice AND si.docstatus = 1
			WHERE {" AND ".join(conditions)}
			ORDER BY si.posting_date DESC, vm.modified DESC
		""",
		values,
		as_dict=True,
	)

	precision = frappe.get_precision("Vehicle Master", "selling_rate")
	for row in rows:
		row.is_sold = cint(row.sales_invoice_docstatus) == 1 and row.vehicle_status in SOLD_STATUSES
		if row.is_sold:
			row.profit_loss, row.chinese_share, row.showroom_share = calculate_partner_shares(
				row.final_valuation_rate, row.selling_rate, precision
			)
		else:
			row.profit_loss = row.chinese_share = row.showroom_share = None
		row.distribution_status = _("Distributed") if row.profit_distributed else _("Not Distributed")
	return rows


def get_report_summary(data):
	sold_rows = [row for row in data if row.is_sold]
	precision = frappe.get_precision("Vehicle Master", "selling_rate")
	total_sales = flt(sum(flt(row.selling_rate) for row in sold_rows), precision)
	total_cost = flt(sum(flt(row.final_valuation_rate) for row in sold_rows), precision)
	total_profit = flt(sum(flt(row.profit_loss) for row in sold_rows), precision)
	chinese_total = flt(sum(flt(row.chinese_share) for row in sold_rows), precision)
	showroom_total = flt(total_profit - chinese_total, precision)
	not_distributed = [row for row in sold_rows if not row.profit_distributed]
	distributed = [row for row in sold_rows if row.profit_distributed]
	currency = next((row.cost_currency for row in sold_rows if row.cost_currency), None)

	return [
		{"value": len(sold_rows), "label": _("Sold Vehicles"), "datatype": "Int", "indicator": "Blue"},
		_summary_currency(total_sales, _("Total Sales"), currency, "Green"),
		_summary_currency(total_cost, _("Total Final Cost"), currency, "Blue"),
		_summary_currency(total_profit, _("Net Profit / Loss"), currency, "Green" if total_profit >= 0 else "Red"),
		_summary_currency(chinese_total, _("Chinese Partner Share 49%"), currency, "Green" if chinese_total >= 0 else "Red"),
		_summary_currency(showroom_total, _("Abu Turki / Showroom Share 51%"), currency, "Green" if showroom_total >= 0 else "Red"),
		_summary_currency(sum(flt(row.profit_loss) for row in not_distributed), _("Not Distributed ({0})").format(len(not_distributed)), currency, "Orange"),
		_summary_currency(sum(flt(row.profit_loss) for row in distributed), _("Distributed ({0})").format(len(distributed)), currency, "Green"),
	]


def _summary_currency(value, label, currency, indicator):
	return {"value": value, "label": label, "datatype": "Currency", "currency": currency, "indicator": indicator}


@frappe.whitelist()
def mark_profit_distributed(vehicle_names):
	frappe.only_for(DISTRIBUTION_ROLES)
	vehicle_names = _normalize_vehicle_names(vehicle_names)
	if not vehicle_names:
		frappe.throw(_("Please select at least one vehicle."))
	if len(vehicle_names) > 500:
		frappe.throw(_("A maximum of 500 vehicles can be processed at once."))

	rows = _get_distribution_rows(vehicle_names, for_update=True)
	_validate_distribution_rows(vehicle_names, rows, check_permissions=True)
	precision = frappe.get_precision("Vehicle Master", "selling_rate")
	totals = _distribution_totals(rows, precision)
	distributed_on = now_datetime()

	for row in rows:
		frappe.db.set_value(
			"Vehicle Master",
			row.name,
			{
				"profit_distributed": 1,
				"profit_distributed_on": distributed_on,
				"profit_distributed_by": frappe.session.user,
			},
		)

	return {
		"count": len(rows),
		"profit_loss": totals[0],
		"chinese_share": totals[1],
		"showroom_share": totals[2],
		"distributed_on": distributed_on,
		"distributed_by": frappe.session.user,
	}


def _normalize_vehicle_names(vehicle_names):
	if isinstance(vehicle_names, str):
		try:
			vehicle_names = json.loads(vehicle_names)
		except (TypeError, ValueError):
			vehicle_names = [vehicle_names]
	if not isinstance(vehicle_names, (list, tuple)):
		return []
	return list(dict.fromkeys(str(name).strip() for name in vehicle_names if str(name).strip()))


def _get_distribution_rows(vehicle_names, for_update=False):
	placeholders = ", ".join(["%s"] * len(vehicle_names))
	lock = " FOR UPDATE" if for_update else ""
	return frappe.db.sql(
		f"""
			SELECT
				vm.name, vm.vin, vm.vehicle_status, vm.sales_invoice,
				vm.selling_rate, vm.final_valuation_rate,
				COALESCE(vm.profit_distributed, 0) AS profit_distributed,
				si.docstatus AS sales_invoice_docstatus
			FROM `tabVehicle Master` vm
			LEFT JOIN `tabSales Invoice` si ON si.name = vm.sales_invoice
			WHERE vm.name IN ({placeholders}){lock}
		""",
		tuple(vehicle_names),
		as_dict=True,
	)


def _validate_distribution_rows(vehicle_names, rows, check_permissions=False):
	rows_by_name = {row.name: row for row in rows}
	missing = [name for name in vehicle_names if name not in rows_by_name]
	if missing:
		frappe.throw(_("Vehicle Master {0} does not exist.").format(missing[0]))

	for name in vehicle_names:
		row = rows_by_name[name]
		vin = row.vin or row.name
		if check_permissions and not frappe.has_permission("Vehicle Master", "write", doc=row.name):
			frappe.throw(_("You do not have permission to update VIN {0}.").format(vin), frappe.PermissionError)
		if cint(row.profit_distributed):
			frappe.throw(_("VIN {0} has already been marked as profit distributed.").format(vin))
		if row.vehicle_status not in SOLD_STATUSES or cint(row.sales_invoice_docstatus) != 1:
			frappe.throw(_("VIN {0} is not sold and cannot be marked as profit distributed.").format(vin))
		if flt(row.final_valuation_rate) <= 0:
			frappe.throw(_("VIN {0} does not have a valid Final Valuation Rate.").format(vin))
		if flt(row.selling_rate) <= 0:
			frappe.throw(_("VIN {0} does not have a valid Selling Rate.").format(vin))


def _distribution_totals(rows, precision=2):
	profit_total = chinese_total = 0
	for row in rows:
		profit_loss, chinese_share, _showroom_share = calculate_partner_shares(
			row.final_valuation_rate, row.selling_rate, precision
		)
		profit_total += profit_loss
		chinese_total += chinese_share
	profit_total = flt(profit_total, precision)
	chinese_total = flt(chinese_total, precision)
	return profit_total, chinese_total, flt(profit_total - chinese_total, precision)
