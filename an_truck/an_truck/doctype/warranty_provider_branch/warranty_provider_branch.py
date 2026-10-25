import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname


class WarrantyProviderBranch(Document):
	def validate(self):
		self.branch_name = (self.branch_name or "").strip()
		self._set_immutable_branch_code()
		if frappe.db.exists(
			"Warranty Provider Branch",
			{"branch_code": self.branch_code, "name": ["!=", self.name]},
		):
			frappe.throw(_("Branch Code must be unique."))
		if not frappe.db.get_value("Warranty Provider", self.warranty_provider, "active"):
			frappe.throw(_("Warranty Provider must be active."))

	def _set_immutable_branch_code(self):
		"""Assign a concurrency-safe code once and never change it on update."""
		if self.is_new():
			# Naming Series uses a database-backed counter. The unique DocField index
			# remains the final guard when branches are inserted concurrently.
			self.branch_code = make_autoname("WBR-.#####")
			return

		old_code = frappe.db.get_value("Warranty Provider Branch", self.name, "branch_code")
		if old_code:
			self.branch_code = old_code

