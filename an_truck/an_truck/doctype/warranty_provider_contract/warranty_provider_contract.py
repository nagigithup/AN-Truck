import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate


class WarrantyProviderContract(Document):
	def validate(self):
		if self.contract_type != "Open Ended" and not self.end_date:
			frappe.throw(_("End Date is required unless Contract Type is Open Ended."))
		if self.end_date and getdate(self.end_date) < getdate(self.start_date):
			frappe.throw(_("End Date cannot be before Start Date."))
		if self.renewal_date and getdate(self.renewal_date) < getdate(self.start_date):
			frappe.throw(_("Renewal Date cannot be before Start Date."))
		if self.status not in {"Draft", "Terminated"}:
			today = getdate(nowdate())
			if getdate(self.start_date) > today:
				self.status = "Draft"
			elif self.end_date and getdate(self.end_date) < today:
				self.status = "Expired"

