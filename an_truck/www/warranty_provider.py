import frappe

from an_truck.warranty.portal_api import get_portal_context


no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/warranty-provider"
		raise frappe.Redirect
	context.no_cache = 1
	context.show_sidebar = False
	context.portal_context = get_portal_context()
	context.title = "Warranty Provider Portal"
