"""Shared, Vehicle-Master-first warranty entry workflow for Desk and portal."""

import frappe
from frappe import _
from frappe.utils import getdate

from an_truck.warranty.activation import calculate_warranty_expiry

VEHICLE_FIELDS = [
	"name", "vin", "item_code", "item_name", "brand", "model", "model_year", "color",
	"customer", "company", "sales_order", "delivery_note", "sales_invoice", "disabled",
]


def _vehicle(value, *, check_permission=True):
	value = (value or "").strip()
	if not value:
		frappe.throw(_("VIN / Chassis Number is required."))
	name = frappe.db.get_value("Vehicle Master", {"vin": value}, "name") or frappe.db.exists(
		"Vehicle Master", value
	)
	if not name:
		frappe.throw(_("Vehicle Master was not found for VIN {0}.").format(value))
	if check_permission and not frappe.has_permission("Vehicle Master", "read", name):
		frappe.throw(_("Not permitted to read Vehicle Master."), frappe.PermissionError)
	vehicle = frappe.db.get_value("Vehicle Master", name, VEHICLE_FIELDS, as_dict=True)
	if vehicle.disabled:
		frappe.throw(_("Cannot issue a warranty for a disabled Vehicle Master."))
	return vehicle


def _invoice_has_vehicle(invoice, vehicle):
	return bool(
		frappe.db.exists(
			"Sales Invoice Item",
			{"parent": invoice, "parenttype": "Sales Invoice", "custom_vehicle_master": vehicle.name},
		)
		or frappe.db.exists(
			"Sales Invoice Item",
			{"parent": invoice, "parenttype": "Sales Invoice", "custom_vin": vehicle.vin},
		)
	)


def _start_date(vehicle, invoice=None):
	if vehicle.delivery_note:
		row = frappe.db.get_value(
			"Delivery Note", vehicle.delivery_note, ["posting_date", "docstatus"], as_dict=True
		)
		if row and row.docstatus == 1:
			return row.posting_date, "Delivery Note"
	invoice = invoice or vehicle.sales_invoice
	if invoice and frappe.get_meta("Sales Invoice").has_field("custom_delivery_date"):
		row = frappe.db.get_value(
			"Sales Invoice", invoice, ["custom_delivery_date", "docstatus"], as_dict=True
		)
		if row and row.docstatus == 1 and row.custom_delivery_date:
			return row.custom_delivery_date, "Sales Invoice Delivery Date"
	return None, "Manual"


def _summary(vehicle, invoice=None):
	customer_name = frappe.db.get_value("Customer", vehicle.customer, "customer_name") if vehicle.customer else None
	start_date, activation_source = _start_date(vehicle, invoice)
	existing = frappe.db.get_value(
		"Vehicle Warranty", {"vin": vehicle.vin, "status": "Active"}, "name"
	)
	return {
		"vehicle_master": vehicle.name,
		"vin": vehicle.vin,
		"vehicle": {
			"label": " ".join(
				str(value) for value in (vehicle.brand, vehicle.model, vehicle.model_year, vehicle.color) if value
			) or vehicle.item_name or vehicle.item_code,
			"item_code": vehicle.item_code,
			"brand": vehicle.brand,
			"model": vehicle.model,
			"model_year": vehicle.model_year,
			"color": vehicle.color,
		},
		"customer": {"name": vehicle.customer, "label": customer_name or vehicle.customer},
		"company": vehicle.company,
		"sales_order": vehicle.sales_order,
		"delivery_note": vehicle.delivery_note,
		"sales_invoice": invoice or vehicle.sales_invoice,
		"start_date": start_date,
		"activation_source": activation_source,
		"existing_warranty": existing,
	}


def _templates():
	return frappe.get_all(
		"Warranty Coverage Template",
		filters={"active": 1},
		fields=["name", "template_name", "duration", "duration_unit"],
		order_by="template_name asc",
	)


def _preferred_providers(vehicle, coverage_template):
	settings = frappe.get_single("AN Truck Settings")
	item = frappe.db.get_value(
		"Item", vehicle.item_code,
		["custom_warranty_provider", "custom_warranty_coverage_template"], as_dict=True,
	) or frappe._dict()
	providers = []
	if item.custom_warranty_provider and (
		not item.custom_warranty_coverage_template or item.custom_warranty_coverage_template == coverage_template
	):
		providers.append(item.custom_warranty_provider)
	if settings.default_warranty_provider and (
		not settings.default_warranty_coverage_template
		or settings.default_warranty_coverage_template == coverage_template
	):
		providers.append(settings.default_warranty_provider)
	return list(dict.fromkeys(providers))


def resolve_configuration(vehicle, coverage_template, start_date, provider=None):
	if not coverage_template or not frappe.db.get_value(
		"Warranty Coverage Template", coverage_template, "active"
	):
		frappe.throw(_("Select an active Warranty Coverage Template."))
	if not start_date:
		frappe.throw(_("Warranty Start Date is required for an Active warranty."))
	providers = _preferred_providers(vehicle, coverage_template)
	if provider:
		providers = [provider]
	providers = [
		name
		for name in providers
		if frappe.db.exists("Warranty Provider", {"name": name, "active": 1, "status": "Active"})
	]
	if provider and not providers:
		frappe.throw(_("Select an active Warranty Provider."))
	if not providers:
		providers = frappe.get_all(
			"Warranty Provider", filters={"active": 1, "status": "Active"}, pluck="name"
		)
	contracts = frappe.get_all(
		"Warranty Provider Contract",
		filters={
			"warranty_provider": ["in", providers],
			"status": "Active",
			"start_date": ["<=", getdate(start_date)],
		},
		fields=["name", "contract_number", "warranty_provider", "start_date", "end_date"],
		order_by="warranty_provider asc, start_date desc, creation desc",
	)
	contracts = [
		row for row in contracts if not row.end_date or getdate(row.end_date) >= getdate(start_date)
	]
	if not contracts:
		frappe.throw(_("No active Provider Contract is valid for the selected start date."))
	provider_names = list(dict.fromkeys(row.warranty_provider for row in contracts))
	return {
		"providers": provider_names,
		"contracts": contracts,
		"provider": provider_names[0] if len(provider_names) == 1 else None,
		"contract": contracts[0].name if len(contracts) == 1 else None,
		"expiry_date": calculate_warranty_expiry(start_date, coverage_template),
	}


@frappe.whitelist(methods=["GET"])
def get_vehicle_warranty_context(vin=None, vehicle_master=None, sales_invoice=None):
	if not frappe.has_permission("Vehicle Warranty", "read"):
		frappe.throw(_("Not permitted to read Vehicle Warranty."), frappe.PermissionError)
	vehicle = _vehicle(vehicle_master or vin)
	if sales_invoice:
		invoice = frappe.get_doc("Sales Invoice", sales_invoice)
		invoice.check_permission("read")
		if not _invoice_has_vehicle(invoice.name, vehicle):
			frappe.throw(_("The selected VIN is not linked to this Sales Invoice."))
		if vehicle.customer and invoice.customer != vehicle.customer:
			frappe.throw(_("Vehicle customer does not match the Sales Invoice customer."))
		if vehicle.company and invoice.company != vehicle.company:
			frappe.throw(_("Vehicle company does not match the Sales Invoice company."))
	return {**_summary(vehicle, sales_invoice), "templates": _templates()}


@frappe.whitelist(methods=["GET"])
def get_invoice_warranty_context(sales_invoice):
	if not frappe.has_permission("Vehicle Warranty", "read"):
		frappe.throw(_("Not permitted to read Vehicle Warranty."), frappe.PermissionError)
	invoice = frappe.get_doc("Sales Invoice", sales_invoice)
	invoice.check_permission("read")
	vehicles = []
	seen = set()
	for row in invoice.items:
		value = row.get("custom_vehicle_master") or row.get("custom_vin")
		if not value:
			continue
		vehicle = _vehicle(value)
		if vehicle.name in seen:
			continue
		seen.add(vehicle.name)
		if vehicle.customer and vehicle.customer != invoice.customer:
			frappe.throw(_("Vehicle customer does not match the Sales Invoice customer."))
		if vehicle.company and vehicle.company != invoice.company:
			frappe.throw(_("Vehicle company does not match the Sales Invoice company."))
		vehicles.append(_summary(vehicle, invoice.name))
	return {
		"invoice": {"name": invoice.name, "customer": invoice.customer,
			"customer_name": invoice.customer_name, "company": invoice.company,
			"posting_date": invoice.posting_date, "docstatus": invoice.docstatus},
		"vehicles": vehicles,
		"templates": _templates(),
		"can_create": bool(invoice.docstatus == 1 and frappe.has_permission("Vehicle Warranty", "create")),
	}


@frappe.whitelist(methods=["GET"])
def get_warranty_configuration(vehicle_master, coverage_template, start_date, provider=None):
	if not frappe.has_permission("Vehicle Warranty", "read"):
		frappe.throw(_("Not permitted to read Vehicle Warranty."), frappe.PermissionError)
	vehicle = _vehicle(vehicle_master)
	return resolve_configuration(vehicle, coverage_template, start_date, provider)


@frappe.whitelist(methods=["POST"])
def create_warranty_from_invoice(
	sales_invoice, vehicle_master, coverage_template, warranty_start_date,
	warranty_provider=None, provider_contract=None, notes=None,
):
	if not frappe.has_permission("Vehicle Warranty", "create"):
		frappe.throw(_("Not permitted to create Vehicle Warranty."), frappe.PermissionError)
	invoice = frappe.get_doc("Sales Invoice", sales_invoice)
	invoice.check_permission("read")
	if invoice.docstatus != 1:
		frappe.throw(_("Sales Invoice must be submitted before adding a warranty."))
	vehicle = _vehicle(vehicle_master)
	if not _invoice_has_vehicle(invoice.name, vehicle):
		frappe.throw(_("The selected VIN is not linked to this Sales Invoice."))
	if vehicle.customer != invoice.customer or vehicle.company != invoice.company:
		frappe.throw(_("Vehicle, customer, company, and Sales Invoice relationships do not match."))
	existing = frappe.db.get_value(
		"Vehicle Warranty", {"vin": vehicle.vin, "status": "Active"}, "name"
	)
	if existing:
		frappe.throw(_("VIN {0} already has active warranty {1}.").format(vehicle.vin, existing))
	config = resolve_configuration(vehicle, coverage_template, warranty_start_date, warranty_provider)
	provider = warranty_provider or config["provider"]
	if not provider:
		frappe.throw(_("Select a Warranty Provider because multiple valid options exist."))
	valid_contracts = [row.name for row in config["contracts"] if row.warranty_provider == provider]
	contract = provider_contract or (valid_contracts[0] if len(valid_contracts) == 1 else None)
	if not contract:
		frappe.throw(_("Select a Provider Contract because multiple valid options exist."))
	if contract not in valid_contracts:
		frappe.throw(_("Provider Contract is not valid for the selected provider and start date."))
	default_start, activation_source = _start_date(vehicle, invoice.name)
	if not default_start or getdate(default_start) != getdate(warranty_start_date):
		activation_source = "Manual"
	doc = frappe.get_doc({
		"doctype": "Vehicle Warranty", "vehicle_master": vehicle.name,
		"coverage_template": coverage_template, "warranty_provider": provider,
		"provider_contract": contract, "warranty_start_date": warranty_start_date,
		"delivery_date": warranty_start_date if activation_source != "Manual" else None,
		"sales_invoice": invoice.name, "status": "Active",
		"activation_source": activation_source, "notes": notes,
	}).insert()
	return {"name": doc.name, "vin": doc.vin, "expiry_date": doc.warranty_expiry_date}
