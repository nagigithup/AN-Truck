import frappe
from frappe import _
from frappe.utils import add_days, add_months, add_years, cint, getdate


def activate_warranties_from_delivery(doc):
	settings = frappe.get_single("AN Truck Settings")
	if not settings.auto_activate_vehicle_warranty:
		return []
	created = []
	for row in doc.get("items", []):
		if not row.get("custom_vehicle_master"):
			continue
		name = activate_vehicle_warranty(
			row.custom_vehicle_master,
			delivery_date=doc.posting_date,
			delivery_note=doc.name,
			activation_source="Delivery Note",
			item_code=row.item_code,
		)
		if name:
			created.append(name)
	return created


def activate_warranties_from_sales_invoice(doc):
	settings = frappe.get_single("AN Truck Settings")
	delivery_date = doc.get("custom_delivery_date")
	if not settings.auto_activate_vehicle_warranty or not delivery_date:
		return []
	created = []
	for row in doc.get("items", []):
		if not row.get("custom_vehicle_master"):
			continue
		vehicle = frappe.db.get_value("Vehicle Master", row.custom_vehicle_master, ["delivery_note", "item_code"], as_dict=True)
		if vehicle and vehicle.delivery_note:
			continue
		name = activate_vehicle_warranty(
			row.custom_vehicle_master,
			delivery_date=delivery_date,
			sales_invoice=doc.name,
			activation_source="Sales Invoice Delivery Date",
			item_code=row.item_code,
		)
		if name:
			created.append(name)
	return created


def activate_vehicle_warranty(vehicle_master, delivery_date, delivery_note=None, sales_invoice=None, activation_source="Manual", item_code=None):
	vehicle = frappe.db.get_value(
		"Vehicle Master",
		vehicle_master,
		["vin", "item_code", "customer", "sales_order", "delivery_note", "sales_invoice", "company", "disabled"],
		as_dict=True,
	)
	if not vehicle or vehicle.disabled:
		return None
	existing = frappe.db.get_value("Vehicle Warranty", {"vin": vehicle.vin, "status": "Active"}, "name")
	if existing:
		return existing
	settings = frappe.get_single("AN Truck Settings")
	item_code = item_code or vehicle.item_code
	item_config = frappe.db.get_value(
		"Item", item_code, ["custom_warranty_provider", "custom_warranty_coverage_template"], as_dict=True
	) or frappe._dict()
	provider = item_config.get("custom_warranty_provider") or settings.default_warranty_provider
	template = item_config.get("custom_warranty_coverage_template") or settings.default_warranty_coverage_template
	contract = get_valid_contract(provider, delivery_date) if provider else None
	if not (provider and template and contract):
		frappe.log_error(
			title=_("Vehicle warranty configuration incomplete"),
			message=_("VIN {0}: configure an active provider, coverage template, and provider contract valid on {1}.").format(vehicle.vin, delivery_date),
		)
		return None
	doc = frappe.get_doc({
		"doctype": "Vehicle Warranty",
		"vehicle_master": vehicle_master,
		"vin": vehicle.vin,
		"customer": vehicle.customer,
		"sales_order": vehicle.sales_order,
		"delivery_note": delivery_note or vehicle.delivery_note,
		"sales_invoice": sales_invoice or vehicle.sales_invoice,
		"delivery_date": delivery_date,
		"warranty_start_date": delivery_date,
		"coverage_template": template,
		"warranty_provider": provider,
		"provider_contract": contract,
		"company": vehicle.company,
		"status": "Active",
		"activation_source": activation_source,
	})
	doc.insert(ignore_permissions=True)
	return doc.name


def get_valid_contract(provider, date):
	if not provider or not date:
		return None
	for row in frappe.get_all(
		"Warranty Provider Contract",
		filters={"warranty_provider": provider, "status": "Active", "start_date": ["<=", getdate(date)]},
		fields=["name", "end_date"],
		order_by="start_date desc, creation desc",
	):
		if not row.end_date or getdate(row.end_date) >= getdate(date):
			return row.name
	return None


def calculate_warranty_expiry(start_date, coverage_template):
	"""Use the same inclusive, date-only calculation for preview and issuance."""
	template = frappe.db.get_value(
		"Warranty Coverage Template", coverage_template, ["duration", "duration_unit"], as_dict=True
	)
	if not template or not start_date:
		return None
	start = getdate(start_date)
	end = add_years(start, cint(template.duration)) if template.duration_unit == "Years" else add_months(start, cint(template.duration))
	return add_days(end, -1)


def cancel_warranties_for_source(source_doctype, source_name):
	fieldname = "delivery_note" if source_doctype == "Delivery Note" else "sales_invoice"
	for name in frappe.get_all("Vehicle Warranty", filters={fieldname: source_name, "status": "Active"}, pluck="name"):
		if frappe.db.exists("Warranty Claim", {"custom_vehicle_warranty": name, "status": ["!=", "Cancelled"]}):
			frappe.throw(_("Cannot cancel {0} because Vehicle Warranty {1} already has a Warranty Claim.").format(source_name, name))
		warranty = frappe.get_doc("Vehicle Warranty", name)
		warranty.status = "Cancelled"
		warranty.notes = ((warranty.notes or "") + "\n" + _("Automatically cancelled because {0} {1} was cancelled.").format(source_doctype, source_name)).strip()
		warranty.save(ignore_permissions=True)
