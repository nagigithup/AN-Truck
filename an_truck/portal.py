import frappe
from frappe import _
from frappe.utils import formatdate, today

from an_truck.services import CUSTOM_FIELD


MANAGER_ROLES = {"System Manager", "AN Truck Manager"}


def _can_read(doctype):
	return frappe.db.exists("DocType", doctype) and frappe.has_permission(doctype, "read")


def _can_create(doctype):
	return frappe.db.exists("DocType", doctype) and frappe.has_permission(doctype, "create")


def _count(doctype, filters=None):
	if not _can_read(doctype):
		return None
	try:
		return frappe.db.count(doctype, filters or {})
	except Exception:
		frappe.log_error(frappe.get_traceback(), _("AN Truck portal counter failed for {0}").format(doctype))
		return 0


def _first_company():
	default_company = frappe.defaults.get_user_default("Company")
	if default_company:
		return default_company
	return frappe.db.get_single_value("Global Defaults", "default_company") or frappe.db.get_value("Company", {}, "name")


def _visible(item):
	doctype = item.get("doctype")
	if doctype and not _can_read(doctype):
		return False
	report = item.get("report")
	if report and not frappe.db.exists("Report", report):
		return False
	roles = set(frappe.get_roles())
	allowed_roles = set(item.get("roles") or [])
	return not allowed_roles or bool(roles & allowed_roles) or bool(roles & MANAGER_ROLES)


def _doc_link(label, doctype, filters=None, roles=None, icon=None):
	return {
		"label": label,
		"doctype": doctype,
		"route": ["List", doctype],
		"filters": filters or {},
		"roles": roles or [],
		"icon": icon or "circle",
	}


def _report_link(label, report, filters=None, roles=None, icon=None):
	return {
		"label": label,
		"report": report,
		"route": ["query-report", report],
		"filters": filters or {},
		"roles": roles or [],
		"icon": icon or "bar-chart",
	}


def _new_link(label, doctype, roles=None, icon=None):
	return {
		"label": label,
		"doctype": doctype,
		"route": ["Form", doctype, "new"],
		"roles": roles or [],
		"icon": icon or "plus",
		"create": True,
	}


def _doctype_summary():
	return {
		"vehicle": "Vehicle" if frappe.db.exists("DocType", "Vehicle") else None,
		"vehicle_master": "Vehicle Master" if frappe.db.exists("DocType", "Vehicle Master") else None,
		"vehicle_registration": "Vehicle" if frappe.db.exists("DocType", "Vehicle") else None,
	}


def _menu_groups():
	return [{"label": _("Main"), "items": _sidebar_items(), "open": True}]


def _sidebar_items():
	items = [
		{"label": _("Main"), "route": ["an-truck-portal"], "icon": "menu"},
		{**_doc_link(_("Vehicle Import Files"), "Vehicle Import File", icon="archive"), "view": "purchase"},
		_doc_link(_("Supplier"), "Supplier", icon="users"),
		_doc_link(_("Purchase Order"), "Purchase Order", {CUSTOM_FIELD: ["is", "set"]}, icon="shopping-cart"),
		_doc_link(_("Purchase Receipt"), "Purchase Receipt", {CUSTOM_FIELD: ["is", "set"]}, icon="truck"),
		_doc_link(_("Purchase Invoice"), "Purchase Invoice", {CUSTOM_FIELD: ["is", "set"]}, icon="file-text"),
		_doc_link(_("Supplier Payment"), "Payment Entry", {"payment_type": "Pay", "party_type": "Supplier", CUSTOM_FIELD: ["is", "set"]}, icon="credit-card"),
		_doc_link(_("Landed Cost Voucher"), "Landed Cost Voucher", {CUSTOM_FIELD: ["is", "set"]}, icon="layers"),
		_doc_link(_("Vehicle Master"), "Vehicle Master", icon="key"),
		_doc_link(_("VIN / Serial Number"), "Serial No", icon="hash"),
		_doc_link(_("Vehicle Inspection"), "Quality Inspection", icon="search"),
		_report_link(_("ارصدة الموردين"), "Accounts Payable", icon="bar-chart"),
		_doc_link(_("Customer"), "Customer", icon="user"),
		_doc_link(_("Sales Quotations"), "Quotation", {CUSTOM_FIELD: ["is", "set"]}, icon="file"),
		_doc_link(_("Sales Orders"), "Sales Order", {CUSTOM_FIELD: ["is", "set"]}, icon="check-square"),
		_doc_link(_("Sales Invoices"), "Sales Invoice", {CUSTOM_FIELD: ["is", "set"]}, icon="receipt"),
		_doc_link(_("Customer Payments"), "Payment Entry", {"payment_type": "Receive", "party_type": "Customer", CUSTOM_FIELD: ["is", "set"]}, icon="credit-card"),
		_report_link(_("ارصدة العملاء"), "Accounts Receivable", icon="bar-chart"),
	]
	return [item for item in items if _visible(item)]


def _kpis():
	cards = [
		{
			"label": _("Open Vehicle Import Files"),
			"value": _count("Vehicle Import File", {"status": ["not in", ["Completed", "Cancelled"]]}),
			"doctype": "Vehicle Import File",
			"filters": {"status": ["not in", ["Completed", "Cancelled"]]},
			"icon": "activity",
		},
		{"label": _("Trucks Awaiting Purchase"), "value": _count("Vehicle Import File", {"status": "Draft"}), "doctype": "Vehicle Import File", "filters": {"status": "Draft"}, "icon": "shopping-cart"},
		{"label": _("Trucks Awaiting Receipt"), "value": _count("Vehicle Import File", {"status": ["in", ["Ready to Ship", "At Port", "Under Clearance", "Partially Received"]]}), "doctype": "Vehicle Import File", "filters": {"status": ["in", ["Ready to Ship", "At Port", "Under Clearance", "Partially Received"]]}, "icon": "package"},
		{"label": _("Trucks Awaiting VIN Completion"), "value": _count("Vehicle Import File", {"total_remaining_vehicles": [">", 0]}), "doctype": "Vehicle Import File", "filters": {"total_remaining_vehicles": [">", 0]}, "icon": "hash"},
		{"label": _("Trucks Awaiting Inspection"), "value": _count("Vehicle Master", {"vehicle_status": ["in", ["Received", "Under Inspection"]], "disabled": 0}), "doctype": "Vehicle Master", "filters": {"vehicle_status": ["in", ["Received", "Under Inspection"]], "disabled": 0}, "icon": "search"},
		{"label": _("Unpaid Supplier Invoices"), "value": _count("Purchase Invoice", {CUSTOM_FIELD: ["is", "set"], "outstanding_amount": [">", 0], "docstatus": 1}), "doctype": "Purchase Invoice", "filters": {CUSTOM_FIELD: ["is", "set"], "outstanding_amount": [">", 0], "docstatus": 1}, "icon": "alert-circle"},
	]
	return [card for card in cards if card["value"] is not None]


def _actions():
	items = [
		_new_link(_("New Vehicle Import File"), "Vehicle Import File", icon="plus"),
		_new_link(_("New Purchase Order"), "Purchase Order", icon="shopping-cart"),
		_doc_link(_("Receive Vehicle"), "Purchase Receipt", {CUSTOM_FIELD: ["is", "set"]}, icon="truck"),
		_doc_link(_("Enter VIN"), "Purchase Receipt", {CUSTOM_FIELD: ["is", "set"]}, icon="hash"),
		_new_link(_("Create Purchase Invoice"), "Purchase Invoice", icon="file-text"),
		_new_link(_("Create Landed Cost Voucher"), "Landed Cost Voucher", icon="layers"),
		_doc_link(_("Complete Vehicle Master"), "Vehicle Master", {"vehicle_status": ["in", ["Received", "Under Inspection"]], "disabled": 0}, icon="key"),
		_new_link(_("Register Vehicle"), "Vehicle", icon="clipboard-check"),
		_new_link(_("Create Sales Quotation"), "Quotation", icon="file"),
		_new_link(_("Create Sales Order"), "Sales Order", icon="check-square"),
		_new_link(_("Create Sales Invoice"), "Sales Invoice", icon="receipt"),
		_new_link(_("Record Payment"), "Payment Entry", icon="credit-card"),
	]
	visible = []
	for item in items:
		if item.get("create") and not _can_create(item["doctype"]):
			continue
		if not item.get("create") and not _can_read(item["doctype"]):
			continue
		visible.append(item)
	return visible


@frappe.whitelist()
def get_portal_data():
	user = frappe.get_doc("User", frappe.session.user)
	company = _first_company()
	return {
		"user": {
			"full_name": user.full_name or user.first_name or frappe.session.user,
			"language": frappe.local.lang or user.language or "en",
		},
		"company": company,
		"date": formatdate(today()),
		"summary": _("Daily import, receiving, costing, sales, delivery, and registration work in one place."),
		"doctype_summary": _doctype_summary(),
		"sidebar_items": _sidebar_items(),
		"menu_groups": _menu_groups(),
		"kpis": _kpis(),
		"actions": _actions(),
	}
