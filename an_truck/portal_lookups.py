"""Fixed, permission-aware reference data for employee portal forms."""

import frappe

from an_truck.portal_parties import _access


def _options(doctype, filters=None):
	"""Internal helper only; callers cannot choose a DocType over HTTP."""
	filters = dict(filters or {})
	meta = frappe.get_meta(doctype)
	for field, value in (("disabled", 0), ("enabled", 1), ("is_active", 1)):
		if meta.has_field(field) and meta.get_field(field).fieldtype == "Check":
			filters[field] = value
	# get_list enforces DocType and User Permissions; zero means all matching
	# master names, not the default first twenty records. No full documents.
	names = frappe.get_list(
		doctype, filters=filters, pluck="name", order_by="name asc", limit=0
	)
	return [{"value": name, "label": name} for name in names]


@frappe.whitelist(methods=["GET"])
def get_supplier_form_options(company=None):
	_access("Supplier", company=company)
	return {
		"supplier_groups": _options("Supplier Group", {"is_group": 0}),
		"countries": _options("Country"),
		"currencies": _options("Currency"),
	}
