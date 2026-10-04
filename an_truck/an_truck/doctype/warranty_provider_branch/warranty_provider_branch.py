import frappe
from frappe import _
from frappe.model.document import Document


class WarrantyProviderBranch(Document):
	def validate(self):
		self.branch_name = (self.branch_name or "").strip()
		self.branch_code = (self.branch_code or "").strip().upper()
		if frappe.db.exists(
			"Warranty Provider Branch",
			{"warranty_provider": self.warranty_provider, "branch_code": self.branch_code, "name": ["!=", self.name]},
		):
			frappe.throw(_("Branch Code must be unique within the Warranty Provider."))
		if not frappe.db.get_value("Warranty Provider", self.warranty_provider, "active"):
			frappe.throw(_("Warranty Provider must be active."))

