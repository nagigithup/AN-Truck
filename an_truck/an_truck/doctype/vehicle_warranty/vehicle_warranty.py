import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from an_truck.warranty.activation import calculate_warranty_expiry
from an_truck.warranty.timezone import get_company_local_date


class VehicleWarranty(Document):
	def before_validate(self):
		self.populate_vehicle_details()
		self.populate_warranty_configuration()
		self.set_expiry_date()
		self.set_effective_status()
		self.set_active_vin_key()

	def validate(self):
		self.validate_vehicle()
		self.validate_provider_contract()
		self.validate_template()
		self.validate_dates()
		self.validate_renewal()
		self.validate_single_active_warranty()
		self.validate_coverage_snapshot_immutable()
		self.snapshot_coverage()

	def on_update(self):
		self.sync_serial_no()

	def populate_vehicle_details(self):
		if self.vin and not self.vehicle_master:
			self.vehicle_master = frappe.db.get_value("Vehicle Master", {"vin": self.vin}, "name")
		if self.vehicle_master:
			vehicle = frappe.db.get_value(
				"Vehicle Master",
				self.vehicle_master,
				[
					"vin",
					"item_code",
					"model",
					"customer",
					"sales_order",
					"delivery_note",
					"sales_invoice",
					"company",
				],
				as_dict=True,
			)
			if vehicle:
				if self.is_new() or not self.vin:
					self.vin = vehicle.vin
				if self.is_new() or not self.item_code:
					self.item_code = vehicle.item_code
				if self.is_new() or not self.vehicle_model:
					self.vehicle_model = vehicle.model or frappe.db.get_value(
						"Item", vehicle.item_code, "item_name"
					)
				# Vehicle ownership is authoritative for Company and Customer. This also
				# prevents a user's default Company from placing a warranty in the wrong
				# company's timezone/security boundary.
				for fieldname in ("customer", "company"):
					if self.is_new() or not self.get(fieldname):
						self.set(fieldname, vehicle.get(fieldname))
				for fieldname in ("sales_order", "delivery_note", "sales_invoice"):
					if self.is_new() and vehicle.get(fieldname):
						self.set(fieldname, vehicle.get(fieldname))
				self._link_existing_standard_vehicle()
		if self.company and not self.currency:
			self.currency = frappe.db.get_value("Company", self.company, "default_currency")

	def _link_existing_standard_vehicle(self):
		"""Keep legacy ERPNext Vehicle links when present, without making them an entry dependency."""
		if self.vehicle or not frappe.db.exists("DocType", "Vehicle"):
			return
		meta = frappe.get_meta("Vehicle")
		for fieldname, value in (("custom_vehicle_master", self.vehicle_master), ("custom_vin", self.vin)):
			if value and meta.has_field(fieldname):
				self.vehicle = frappe.db.get_value("Vehicle", {fieldname: value}, "name")
				if self.vehicle:
					return

	def populate_warranty_configuration(self):
		if self.coverage_template:
			template = frappe.db.get_value(
				"Warranty Coverage Template", self.coverage_template,
				["duration", "duration_unit"], as_dict=True,
			)
			if template:
				self.duration = template.duration
				self.duration_unit = template.duration_unit
		if not (self.vehicle_master and self.coverage_template and self.warranty_start_date):
			return
		if self.warranty_provider and self.provider_contract:
			return
		from an_truck.warranty.workflow import resolve_configuration
		vehicle = frappe.db.get_value(
			"Vehicle Master", self.vehicle_master, ["name", "item_code"], as_dict=True
		)
		config = resolve_configuration(
			vehicle, self.coverage_template, self.warranty_start_date, self.warranty_provider
		)
		if not self.warranty_provider and config["provider"]:
			self.warranty_provider = config["provider"]
		if not self.provider_contract:
			contracts = [
				row.name for row in config["contracts"]
				if row.warranty_provider == self.warranty_provider
			]
			if len(contracts) == 1:
				self.provider_contract = contracts[0]

	def validate_vehicle(self):
		if not self.is_new() and self.has_value_changed("vehicle_master"):
			frappe.throw(_("Vehicle Master cannot be changed after a warranty is issued."))
		vehicle = frappe.db.get_value(
			"Vehicle Master", self.vehicle_master,
			["vin", "customer", "company", "sales_order", "delivery_note", "sales_invoice", "disabled"],
			as_dict=True,
		)
		if not vehicle or vehicle.vin != self.vin:
			frappe.throw(_("Vehicle Master must match the selected VIN."))
		if vehicle.disabled:
			frappe.throw(_("Cannot issue a warranty for a disabled Vehicle Master."))
		for fieldname in ("customer", "company", "sales_order", "delivery_note", "sales_invoice"):
			if (self.is_new() or self.has_value_changed(fieldname)) and (
				(self.get(fieldname) or None) != (vehicle.get(fieldname) or None)
			):
				if fieldname in {"customer", "company"} or not self._document_links_vehicle(
					fieldname, self.get(fieldname)
				):
					frappe.throw(_("Warranty {0} must match Vehicle Master.").format(_(fieldname)))
		if self.vehicle:
			meta = frappe.get_meta("Vehicle")
			if meta.has_field("custom_vehicle_master"):
				linked = frappe.db.get_value("Vehicle", self.vehicle, "custom_vehicle_master")
				if linked and linked != self.vehicle_master:
					frappe.throw(_("Standard Vehicle must link to the selected Vehicle Master."))

	def _document_links_vehicle(self, fieldname, document):
		if not document:
			return False
		child = {
			"sales_order": "Sales Order Item",
			"delivery_note": "Delivery Note Item",
			"sales_invoice": "Sales Invoice Item",
		}.get(fieldname)
		if not child:
			return False
		return bool(
			frappe.db.exists(
				child,
				{"parent": document, "docstatus": ["<", 2], "custom_vehicle_master": self.vehicle_master},
			)
			or frappe.db.exists(
				child, {"parent": document, "docstatus": ["<", 2], "custom_vin": self.vin}
			)
		)

	def validate_provider_contract(self):
		contract = frappe.db.get_value(
			"Warranty Provider Contract",
			self.provider_contract,
			["warranty_provider", "status", "start_date", "end_date"],
			as_dict=True,
		)
		if not contract or contract.warranty_provider != self.warranty_provider:
			frappe.throw(_("Provider Contract must belong to the selected Warranty Provider."))
		if self.status == "Active" and contract.status != "Active":
			frappe.throw(_("Provider Contract must be Active before activating a warranty."))
		if self.warranty_start_date:
			start = getdate(self.warranty_start_date)
			if start < getdate(contract.start_date) or (
				contract.end_date and start > getdate(contract.end_date)
			):
				frappe.throw(_("Warranty Start Date must fall within the Provider Contract period."))

	def validate_template(self):
		if self.status == "Active" and not frappe.db.get_value(
			"Warranty Coverage Template", self.coverage_template, "active"
		):
			frappe.throw(_("Warranty Coverage Template must be active."))

	def set_expiry_date(self):
		if not self.warranty_start_date or not self.coverage_template:
			return
		if self.expiry_override_date:
			self.warranty_expiry_date = self.expiry_override_date
			return
		self.warranty_expiry_date = calculate_warranty_expiry(
			self.warranty_start_date, self.coverage_template
		)

	def validate_dates(self):
		if self.status == "Active" and not self.warranty_start_date:
			frappe.throw(_("Warranty Start Date is required for an Active warranty."))
		if self.expiry_override_date and not self.expiry_override_reason:
			frappe.throw(_("Expiry Override Reason is required."))
		if self.expiry_override_date and not _can_override_expiry():
			previous = (
				None
				if self.is_new()
				else frappe.db.get_value("Vehicle Warranty", self.name, "expiry_override_date")
			)
			if str(previous or "") != str(self.expiry_override_date or ""):
				frappe.throw(
					_("Only a Warranty Manager can override the expiry date."), frappe.PermissionError
				)
		if (
			self.warranty_start_date
			and self.warranty_expiry_date
			and getdate(self.warranty_expiry_date) < getdate(self.warranty_start_date)
		):
			frappe.throw(_("Warranty Expiry Date cannot be before Warranty Start Date."))

	def set_effective_status(self):
		if (
			self.status == "Active"
			and self.warranty_expiry_date
			and self.company
			and getdate(self.warranty_expiry_date) < get_company_local_date(self.company)
		):
			self.status = "Expired"

	def set_active_vin_key(self):
		self.active_vin_key = self.vin if self.status == "Active" else None

	def validate_single_active_warranty(self):
		if self.status != "Active":
			return
		existing = frappe.db.get_value(
			"Vehicle Warranty", {"vin": self.vin, "status": "Active", "name": ["!=", self.name]}, "name"
		)
		if existing:
			frappe.throw(
				_(
					"VIN {0} already has active warranty {1}. Create a renewal or extension after expiring/cancelling it."
				).format(self.vin, existing)
			)

	def validate_renewal(self):
		if not self.renewal_of:
			return
		previous = frappe.db.get_value("Vehicle Warranty", self.renewal_of, ["vin", "status"], as_dict=True)
		if not previous or previous.vin != self.vin:
			frappe.throw(_("Renewal / Extension must reference a warranty for the same VIN."))
		if self.status == "Active" and previous.status == "Active":
			frappe.throw(_("The previous warranty must no longer be Active before activating its renewal."))

	def snapshot_coverage(self):
		if self.coverage_snapshot:
			if not self.is_new() and self.has_value_changed("coverage_template"):
				frappe.throw(_("Coverage Template cannot be changed after the coverage snapshot is created."))
			return
		template = frappe.get_doc("Warranty Coverage Template", self.coverage_template)
		for row in template.coverage_items:
			self.append(
				"coverage_snapshot",
				{
					"coverage_category": row.coverage_category,
					"description": row.description,
					"covered": row.covered,
					"coverage_limit": row.coverage_limit,
					"mileage_limit": row.mileage_limit,
					"conditions": row.conditions,
					"exclusions": row.exclusions,
				},
			)

	def validate_coverage_snapshot_immutable(self):
		"""Never allow an issued coverage snapshot to be rewritten.

		The read-only grid protects Desk users, while this comparison also protects
		API/import writes and other server-side callers.
		"""
		if self.is_new():
			return
		previous = self.get_doc_before_save()
		if not previous or not previous.coverage_snapshot:
			return
		fields = (
			"coverage_category",
			"description",
			"covered",
			"coverage_limit",
			"mileage_limit",
			"conditions",
			"exclusions",
		)
		before = [tuple(row.get(field) for field in fields) for row in previous.coverage_snapshot]
		after = [tuple(row.get(field) for field in fields) for row in self.coverage_snapshot]
		if before != after:
			frappe.throw(_("Issued warranty coverage is an immutable snapshot."), frappe.PermissionError)

	def sync_serial_no(self):
		if not frappe.db.exists("Serial No", self.vin):
			return
		if self.status == "Active":
			frappe.db.set_value(
				"Serial No",
				self.vin,
				"warranty_expiry_date",
				self.warranty_expiry_date,
				update_modified=False,
			)
		elif self.status in {"Cancelled", "Expired"}:
			other = frappe.db.get_value(
				"Vehicle Warranty",
				{"vin": self.vin, "status": "Active", "name": ["!=", self.name]},
				"warranty_expiry_date",
			)
			frappe.db.set_value("Serial No", self.vin, "warranty_expiry_date", other, update_modified=False)


def _can_override_expiry():
	return bool({"System Manager", "AN Truck Warranty Manager"}.intersection(frappe.get_roles()))
