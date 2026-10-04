import frappe
from frappe import _
from frappe.model.document import Document


class WarrantyProviderUserAccess(Document):
	def validate(self):
		if self.all_branches:
			self.warranty_provider_branch = None
		elif not self.warranty_provider_branch:
			frappe.throw(_("Warranty Provider Branch is required unless All Branches is enabled."))
		if self.warranty_provider_branch:
			provider = frappe.db.get_value("Warranty Provider Branch", self.warranty_provider_branch, "warranty_provider")
			if provider != self.warranty_provider:
				frappe.throw(_("Warranty Provider Branch must belong to the selected Warranty Provider."))
		if self.user and frappe.db.get_value("User", self.user, "user_type") != "Website User":
			frappe.throw(_("Warranty Provider users must be Website Users without Desk access."))

