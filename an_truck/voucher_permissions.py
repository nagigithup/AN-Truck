"""Scope new optional voucher roles without reducing existing accounting grants."""
import frappe

VIEWER = "AN Truck Voucher Viewer"
CREATOR = "AN Truck Voucher Creator"
ROLES = {VIEWER, CREATOR}


def _legacy(doctype, user, permission):
	roles = set(frappe.get_roles(user))
	if user == "Administrator" or not roles.intersection(ROLES):
		return None
	return [row for row in frappe.get_meta(doctype).permissions if row.role in roles - ROLES
		and not row.permlevel and (row.get(permission) or (permission == "select" and row.read))]


def _condition(doctype, company):
	table = f"`tab{doctype}`"
	if doctype in {"Address", "Contact"}:
		return f"exists (select 1 from `tabDynamic Link` vdl where vdl.parent={table}.name and vdl.parenttype={frappe.db.escape(doctype)} and vdl.link_doctype='Company' and vdl.link_name={frappe.db.escape(company)})"
	field = "name" if doctype == "Company" else "company"
	return f"{table}.`{field}`={frappe.db.escape(company)}"


def query(doctype, user=None):
	user = user or frappe.session.user
	legacy = _legacy(doctype, user, "read")
	if legacy is None or any(not row.if_owner for row in legacy):
		return ""
	company = frappe.db.get_single_value("AN Truck Settings", "voucher_company")
	condition = _condition(doctype, company) if company else "1=0"
	if any(row.if_owner for row in legacy):
		condition = f"({condition} or `tab{doctype}`.owner={frappe.db.escape(user)})"
	return condition


def has_permission(doc, user=None, permission_type=None, ptype=None):
	user = user or frappe.session.user
	legacy = _legacy(doc.doctype, user, ptype or permission_type or "read")
	if legacy is None or any(not row.if_owner or doc.owner == user for row in legacy):
		return True
	company = frappe.db.get_single_value("AN Truck Settings", "voucher_company")
	if doc.doctype in {"Address", "Contact"}:
		allowed = company and frappe.db.exists("Dynamic Link", {"parent": doc.name, "parenttype": doc.doctype,
			"link_doctype": "Company", "link_name": company})
	else:
		allowed = company and (doc.name if doc.doctype == "Company" else doc.get("company")) == company
	return bool(allowed)


def payment_query(user=None): return query("Payment Entry", user)
def company_query(user=None): return query("Company", user)
def account_query(user=None): return query("Account", user)
def sales_query(user=None): return query("Sales Invoice", user)
def purchase_query(user=None): return query("Purchase Invoice", user)
def address_query(user=None): return query("Address", user)
def contact_query(user=None): return query("Contact", user)
