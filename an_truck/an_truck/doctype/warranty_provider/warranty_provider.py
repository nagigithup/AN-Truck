import frappe
from frappe import _
from frappe.model.document import Document


class WarrantyProvider(Document):
	def validate(self):
		self.provider_name = (self.provider_name or "").strip()
		self.provider_name_arabic = (self.provider_name_arabic or "").strip()
		if not self.provider_name:
			frappe.throw(_("Provider Name is required."))
		for fieldname, label in (("commercial_registration", _("Commercial Registration")), ("tax_number", _("Tax Number"))):
			value = (self.get(fieldname) or "").strip()
			self.set(fieldname, value)
			if value and frappe.db.exists("Warranty Provider", {fieldname: value, "name": ["!=", self.name]}):
				frappe.throw(_("{0} must be unique.").format(label))
		self.active = 0 if self.status in {"Inactive", "Suspended", "Terminated"} else self.active

