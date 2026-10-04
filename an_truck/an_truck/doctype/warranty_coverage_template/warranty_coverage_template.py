import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class WarrantyCoverageTemplate(Document):
	def validate(self):
		if cint(self.duration) <= 0:
			frappe.throw(_("Duration must be greater than zero."))
		seen = set()
		for row in self.coverage_items:
			if row.coverage_category in seen:
				frappe.throw(_("Coverage Category {0} is duplicated.").format(row.coverage_category))
			seen.add(row.coverage_category)

