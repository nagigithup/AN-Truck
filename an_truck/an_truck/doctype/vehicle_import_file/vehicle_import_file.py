import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class VehicleImportFile(Document):
	def validate(self):
		self.set_company_currency()
		self.validate_currency()
		self.calculate_contract_amount()
		self.refresh_totals(update_status=False)

	def set_company_currency(self):
		if self.company:
			self.company_currency = frappe.db.get_value("Company", self.company, "default_currency")

	def validate_currency(self):
		if not self.company:
			frappe.throw(_("Company is required."))
		if not self.supplier:
			frappe.throw(_("Supplier is required."))
		if not self.supplier_currency:
			frappe.throw(_("Supplier Currency is required."))
		if flt(self.total_expected_vehicles) < 0:
			frappe.throw(_("Expected vehicle quantity cannot be negative."))
		if self.company_currency and self.supplier_currency != self.company_currency and flt(self.transaction_exchange_rate) <= 0:
			frappe.throw(_("Exchange rate must be greater than zero when contract currency differs from company currency."))

	def calculate_contract_amount(self):
		rate = flt(self.transaction_exchange_rate) or 1
		if self.company_currency and self.supplier_currency == self.company_currency:
			rate = 1
			self.transaction_exchange_rate = self.transaction_exchange_rate or 1
		self.total_contract_amount_company_currency = flt(self.total_contract_amount) * rate

	def refresh_totals(self, update_status=True):
		if self.is_new():
			self.total_received_vehicles = 0
			self.total_created_vehicles = 0
			self.total_remaining_vehicles = flt(self.total_expected_vehicles)
			return
		totals = get_import_file_totals(self.name)
		for field, value in totals.items():
			self.set(field, value)
		if update_status:
			self.set_receipt_status()

	def set_receipt_status(self):
		expected = flt(self.total_expected_vehicles)
		received = flt(self.total_received_vehicles)
		if self.status in ("Completed", "Cancelled"):
			return
		if expected and received == expected:
			self.status = "Fully Received"
		elif received > 0:
			self.status = "Partially Received"


def get_import_file_totals(import_file):
	received = frappe.db.sql(
		"""
		select count(distinct vm.vin)
		from `tabVehicle Master` vm
		inner join `tabPurchase Receipt` pr on pr.name = vm.purchase_receipt
		where vm.vehicle_import_file = %s
			and vm.disabled = 0
			and vm.docstatus < 2
			and pr.docstatus = 1
		""",
		import_file,
	)[0][0] or 0
	created = frappe.db.count("Vehicle Master", {"vehicle_import_file": import_file, "docstatus": ["<", 2], "disabled": 0})
	expected = frappe.db.get_value("Vehicle Import File", import_file, "total_expected_vehicles") or 0
	return {
		"total_received_vehicles": received,
		"total_created_vehicles": created,
		"total_remaining_vehicles": max(flt(expected) - flt(received), 0),
	}


@frappe.whitelist()
def refresh_import_file_totals(name):
	doc = frappe.get_doc("Vehicle Import File", name)
	doc.check_permission("write")
	doc.refresh_totals(update_status=True)
	doc.save()
	return doc.as_dict()

