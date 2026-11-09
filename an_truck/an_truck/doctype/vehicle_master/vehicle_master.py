import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from an_truck.an_truck.doctype.vehicle_specification_template.vehicle_specification_template import (
	SPECIFICATION_FIELDS,
)


class VehicleMaster(Document):
	def get(self, key, filters=None, limit=None, default=None):
		if isinstance(key, str) and key in SPECIFICATION_FIELDS and filters is None:
			return self._resolved_specification(key, default)
		if key == "country_of_origin" and filters is None:
			return self._resolved_specification("default_country_of_origin", default)
		if key == "technical_specifications" and filters is None:
			return self.technical_specifications
		return super().get(key, filters=filters, limit=limit, default=default)

	@property
	def technical_specifications(self):
		if not self.specification_template:
			return []
		template = frappe.get_doc("Vehicle Specification Template", self.specification_template)
		template.check_permission("read")
		return [frappe._dict({key: row.get(key) for key in (
			"specification_category", "specification_name", "value", "uom", "notes"
		)}) for row in template.technical_specifications]

	def _resolved_specification(self, field, default=None):
		cache = self.__dict__.get("_resolved_specification_cache")
		link = self.__dict__.get("specification_template")
		if cache is None or cache[0] != link:
			values = get_specification_values(self) if self.name and not self.is_new() or link else {}
			cache = (link, values)
			self.__dict__["_resolved_specification_cache"] = cache
		return cache[1].get(field, default)

	def validate(self):
		# Existing VINs are immutable identifiers, including their original spelling.
		if self.is_new():
			self.vin = (self.vin or "").strip()
		if not self.vin:
			frappe.throw(_("VIN is required."))
		if self.is_new() and frappe.db.exists("Vehicle Master", {"vin": self.vin}):
			frappe.throw(_("Vehicle Master already exists for VIN {0}.").format(self.vin))
		if frappe.db.exists("Vehicle Master", {"vin": self.vin, "name": ["!=", self.name]}):
			frappe.throw(_("Vehicle Master already exists for VIN {0}.").format(self.vin))
		previous = self.get_doc_before_save()
		if previous and self.vin != previous.vin:
			frappe.throw(_("VIN / Chassis Number cannot be changed after the Vehicle Master is created."))
		template_changed = self.is_new() or not previous or previous.specification_template != self.specification_template
		if previous and template_changed:
			frappe.db.get_value("Vehicle Master", self.name, "name", for_update=True)
		if previous and template_changed and (
			previous.sales_invoice or previous.delivery_note
			or frappe.db.exists("Sales Invoice Item", {"custom_vehicle_master": self.name, "docstatus": 1})
			or frappe.db.exists("Delivery Note Item", {"custom_vehicle_master": self.name, "docstatus": 1})
			or frappe.db.exists("Vehicle Warranty", {"vehicle_master": self.name})
		):
			frappe.throw(_("The Specification Template cannot change after invoicing, delivery or warranty issuance."))
		if self.specification_template:
			template = frappe.get_doc("Vehicle Specification Template", self.specification_template)
			if template_changed and (template.status != "Published" or not template.active):
				frappe.throw(_("Select an active published Specification Template."))
			if template_changed:
				template.check_permission("read")
			serial_item = self.item_code or frappe.db.get_value("Serial No", self.vin, "item_code")
			if template.item_code and serial_item and template.item_code != serial_item:
				frappe.throw(
					_("Specification Template {0} is associated with Item {1}.").format(
						template.name, template.item_code
					)
				)

		self.chassis_number = self.vin
		serial = frappe.db.get_value("Serial No", self.vin, ["item_code", "warehouse"], as_dict=True)
		if not serial:
			frappe.throw(_("VIN {0} must exist as an ERPNext Serial Number.").format(self.vin))
		if self.item_code and serial.item_code and self.item_code != serial.item_code:
			frappe.throw(_("VIN {0} belongs to Item {1}, not {2}.").format(self.vin, serial.item_code, self.item_code))
		self.item_code = self.item_code or serial.item_code
		self.item_name = frappe.db.get_value("Item", self.item_code, "item_name") if self.item_code else self.item_name
		self.warehouse = self.warehouse or serial.warehouse
		self.validate_registration_dates()

	def before_save(self):
		self.refresh_costs()

	def before_rename(self, old, new, merge=False):
		frappe.throw(_("VIN / Chassis Number cannot be changed after the Vehicle Master is created."))

	def refresh_costs(self):
		if self.company and not self.cost_currency:
			self.cost_currency = frappe.db.get_value("Company", self.company, "default_currency")
		if self.purchase_receipt_item:
			self.purchase_valuation_rate = get_purchase_rate(self.purchase_receipt_item)
		self.landed_cost_added = get_landed_cost_added(self.purchase_receipt, self.purchase_receipt_item)
		self.final_valuation_rate = flt(self.purchase_valuation_rate) + flt(self.landed_cost_added)
		if self.meta.has_field("custom_portal_serial_cost_adjustment"):
			from an_truck.serial_vehicle_cost import FIELD, valuation_basis
			basis = valuation_basis(self)
			self.set(FIELD,0 if basis is None else basis-self.final_valuation_rate)
			if basis is not None: self.final_valuation_rate = basis

	def validate_registration_dates(self):
		if (
			self.registration_date
			and self.registration_expiry_date
			and getdate(self.registration_expiry_date) < getdate(self.registration_date)
		):
			frappe.throw(_("Registration Expiry Date cannot be before Registration Date."))


def get_specification_values(vehicle, fields=None):
	"""Resolve shared values from the immutable template, with legacy fallback.

	The fallback reads the retained database columns for pre-template vehicles.
	It never writes resolved values back to Vehicle Master.
	"""
	if isinstance(vehicle, str):
		vehicle = frappe.get_doc("Vehicle Master", vehicle)
	fields = tuple(fields or SPECIFICATION_FIELDS)
	if vehicle.get("specification_template"):
		template = frappe.get_doc("Vehicle Specification Template", vehicle.specification_template)
		template.check_permission("read")
		return {field: template.get(field) for field in fields if template.meta.has_field(field)}
	columns = set(frappe.db.get_table_columns("Vehicle Master"))
	sources = {field: "country_of_origin" if field == "default_country_of_origin" else field for field in fields}
	sources = {field: source for field, source in sources.items() if source in columns}
	if not sources or vehicle.is_new():
		return {}
	row = frappe.db.get_value("Vehicle Master", vehicle.name, list(sources.values()), as_dict=True) or {}
	return {field: row.get(source) for field, source in sources.items()}


def resolve_vehicle_rows(rows):
	"""Fill response dictionaries from templates without saving vehicle records."""
	if not rows:
		return rows
	links = dict(frappe.get_all(
		"Vehicle Master", filters={"name": ["in", [row.name for row in rows]]},
		fields=["name", "specification_template"], as_list=True,
	))
	names = list({name for name in links.values() if name})
	templates = {}
	if names and frappe.has_permission("Vehicle Specification Template", "read"):
		templates = {row.name: row for row in frappe.get_list(
			"Vehicle Specification Template", filters={"name": ["in", names]},
			fields=["name", *SPECIFICATION_FIELDS], page_length=0,
		)}
	for row in rows:
		for field in ("brand", "model", "model_year"):
			row.setdefault(field, None)
		if name := links.get(row.name):
			template = templates.get(name)
			for field in SPECIFICATION_FIELDS:
				if field in row:
					row[field] = template.get(field) if template else None
			if "country_of_origin" in row:
				row.country_of_origin = template.default_country_of_origin if template else None
	return rows


@frappe.whitelist()
def get_vehicle_specifications(vehicle_master):
	vehicle = frappe.get_doc("Vehicle Master", vehicle_master)
	vehicle.check_permission("read")
	if not vehicle.specification_template:
		return {"template": None, "sections": [], "legacy": True}
	return get_template_specifications(vehicle.specification_template)


@frappe.whitelist()
def get_template_specifications(template_name):
	template = frappe.get_doc("Vehicle Specification Template", template_name)
	template.check_permission("read")
	sections = []
	current = None
	for field in template.meta.fields:
		if field.fieldtype == "Section Break":
			current = {"label": _(field.label), "fields": []}
			sections.append(current)
			continue
		if (
			not current
			or field.hidden
			or field.fieldtype in {"Column Break", "HTML", "Button", "Heading"}
			or field.fieldname in {"template_name", "item_code", "status", "active", "revision", "revised_from", "description", "published_on", "published_by"}
		):
			continue
		value = template.get(field.fieldname)
		if field.fieldtype == "Table":
			value = [
				{
					"specification_category": row.specification_category,
					"specification_name": row.specification_name,
					"value": row.value,
					"uom": row.uom,
					"notes": row.notes,
				}
				for row in value or []
			]
		if value not in (None, "", 0, [], False):
			current["fields"].append({"fieldname": field.fieldname, "label": _(field.label), "fieldtype": field.fieldtype, "value": value})
	sections = [section for section in sections if section["fields"]]
	return {
		"template": template.name,
		"template_name": template.template_name,
		"revision": template.revision,
		"sections": sections,
		"legacy": False,
	}


# Compatibility for existing print formats and integrations using vehicle.model.
# These are Python properties, never stored as Vehicle Master specification data.
for _fieldname in SPECIFICATION_FIELDS:
	setattr(VehicleMaster, _fieldname, property(lambda self, key=_fieldname: self._resolved_specification(key)))
VehicleMaster.country_of_origin = property(lambda self: self._resolved_specification("default_country_of_origin"))


def get_purchase_rate(purchase_receipt_item):
	"""Return the item price in company currency, before landed costs."""
	if not purchase_receipt_item:
		return 0
	row = frappe.db.get_value(
		"Purchase Receipt Item",
		purchase_receipt_item,
		["base_net_rate", "base_rate", "valuation_rate"],
		as_dict=True,
	)
	if not row:
		return 0
	return flt(row.base_net_rate) or flt(row.base_rate) or flt(row.valuation_rate)


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
