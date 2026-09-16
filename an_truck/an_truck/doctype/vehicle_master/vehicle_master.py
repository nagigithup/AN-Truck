import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class VehicleMaster(Document):
	def validate(self):
		self.vin = (self.vin or "").strip()
		if not self.vin:
			frappe.throw(_("VIN is required."))
		if self.is_new() and frappe.db.exists("Vehicle Master", {"vin": self.vin}):
			frappe.throw(_("Vehicle Master already exists for VIN {0}.").format(self.vin))
		if frappe.db.exists("Vehicle Master", {"vin": self.vin, "name": ["!=", self.name]}):
			frappe.throw(_("Vehicle Master already exists for VIN {0}.").format(self.vin))

		self.chassis_number = self.vin
		serial = frappe.db.get_value("Serial No", self.vin, ["item_code", "warehouse"], as_dict=True)
		if not serial:
			frappe.throw(_("VIN {0} must exist as an ERPNext Serial Number.").format(self.vin))
		if self.item_code and serial.item_code and self.item_code != serial.item_code:
			frappe.throw(_("VIN {0} belongs to Item {1}, not {2}.").format(self.vin, serial.item_code, self.item_code))
		self.item_code = self.item_code or serial.item_code
		self.item_name = frappe.db.get_value("Item", self.item_code, "item_name") if self.item_code else self.item_name
		self.warehouse = self.warehouse or serial.warehouse

	def before_save(self):
		self.refresh_costs()

	def refresh_costs(self):
		if self.company and not self.cost_currency:
			self.cost_currency = frappe.db.get_value("Company", self.company, "default_currency")
		if self.purchase_receipt_item:
			self.purchase_valuation_rate = frappe.db.get_value("Purchase Receipt Item", self.purchase_receipt_item, "valuation_rate") or self.purchase_valuation_rate
		self.landed_cost_added = get_landed_cost_added(self.purchase_receipt, self.purchase_receipt_item)
		self.final_valuation_rate = self.purchase_valuation_rate or 0


def get_landed_cost_added(purchase_receipt, purchase_receipt_item=None):
	if not purchase_receipt:
		return 0
	rows = frappe.get_all(
		"Landed Cost Purchase Receipt",
		filters={"receipt_document_type": "Purchase Receipt", "receipt_document": purchase_receipt, "docstatus": 1},
		pluck="parent",
	)
	if not rows:
		return 0
	# ERPNext stores final valuation on stock ledgers reliably; per-serial landed split can vary by setup.
	# Purchase Receipt Item stores the total landed amount for the row, so split it per stock unit.
	if purchase_receipt_item and frappe.db.has_column("Purchase Receipt Item", "landed_cost_voucher_amount"):
		row = frappe.db.get_value(
			"Purchase Receipt Item",
			purchase_receipt_item,
			["landed_cost_voucher_amount", "stock_qty", "qty"],
			as_dict=True,
		)
		if not row:
			return 0
		qty = flt(row.stock_qty) or flt(row.qty) or 1
		return flt(row.landed_cost_voucher_amount) / qty
	return 0
