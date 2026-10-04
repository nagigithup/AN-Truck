import frappe

from an_truck.warranty.setup import PROVIDER_USER


def is_provider_user(user=None):
	user = user or frappe.session.user
	if not user or user in {"Guest", "Administrator"}:
		return False
	return PROVIDER_USER in frappe.get_roles(user) and frappe.db.get_value("User", user, "user_type") == "Website User"


def get_provider_access(user=None):
	user = user or frappe.session.user
	if not user or user == "Guest":
		return None
	return frappe.db.get_value(
		"Warranty Provider User Access",
		{"user": user, "active": 1},
		["warranty_provider", "warranty_provider_branch", "all_branches"],
		as_dict=True,
	)


def claim_permission_query(user=None):
	user = user or frappe.session.user
	if not is_provider_user(user):
		return None
	access = get_provider_access(user)
	if not access:
		return "1=0"
	provider = frappe.db.escape(access.warranty_provider)
	condition = f"`tabWarranty Claim`.`custom_warranty_provider`={provider}"
	if not access.all_branches:
		branch = frappe.db.escape(access.warranty_provider_branch)
		condition += f" and `tabWarranty Claim`.`custom_warranty_provider_branch`={branch}"
	return condition


def claim_has_permission(doc, user=None, permission_type=None):
	user = user or frappe.session.user
	if not is_provider_user(user):
		# Frappe controller permission hooks can only deny; a falsey return denies.
		# Return True so normal DocPerm/User Permission evaluation remains authoritative.
		return True
	access = get_provider_access(user)
	if not access or doc.custom_warranty_provider != access.warranty_provider:
		return False
	if not access.all_branches and doc.custom_warranty_provider_branch != access.warranty_provider_branch:
		return False
	return permission_type not in {"delete", "cancel", "submit", "amend"}
