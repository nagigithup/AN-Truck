"""Quotation specifications are references in drafts and sealed data on submission.

ERPNext remains responsible for prices, taxes, totals and document lifecycle.
Configuration variants are complete, independently published template revisions.
"""
import json

import frappe
from frappe import _
from frappe.utils import cstr, now

TEMPLATE = "Vehicle Specification Template"
LINK = "custom_vehicle_specification_template"
SNAPSHOT = "custom_vehicle_quotation_snapshot"
PRINT_FORMAT = "AN Truck - Unified Vehicle Quotation"
ASSET_FIELDS = ("main_vehicle_photo", "technical_photo", "cabin_photo")
COMMERCIAL_FIELDS = ("custom_vehicle_warranty_terms", "custom_vehicle_delivery_terms")


def _asset(url):
	if not url:
		return ""
	# Only managed local files can be protected against later removal.
	if not cstr(url).startswith(("/files/", "/private/files/")):
		frappe.throw(_("Quotation images must be uploaded files."))
	file = frappe.get_doc("File", {"file_url": url})
	file.check_permission("read")
	if cstr(file.file_type).lower() not in {"jpg", "jpeg", "png", "webp", "gif"}:
		frappe.throw(_("Upload a JPG, PNG, WebP or GIF quotation image."))
	return url


def template_photos(template):
	return [row for row in frappe.get_all("File", filters={"attached_to_doctype": TEMPLATE,
		"attached_to_name": template, "is_folder": 0, "file_type": ["in", ["JPG", "JPEG", "PNG", "WEBP", "GIF"]]},
		fields=["name", "file_name", "file_url"], order_by="creation asc") if frappe.has_permission("File", "read", row.name)]


def resolve_line(row, company):
	name = row.get(LINK)
	vehicle_name = row.get("custom_vehicle_master")
	if vehicle_name:
		vehicle = frappe.get_doc("Vehicle Master", vehicle_name)
		vehicle.check_permission("read")
		if vehicle.company != company or vehicle.disabled:
			frappe.throw(_("Selected vehicle does not belong to this company or is disabled."))
		if vehicle.item_code and vehicle.item_code != row.item_code:
			frappe.throw(_("Selected VIN does not match the source item."))
		# Respect an explicitly selected revision. Never write identity fields.
		name = name or vehicle.specification_template
		row.set(LINK, name)
	if not name:
		return {}
	template = frappe.get_doc(TEMPLATE, name)
	template.check_permission("read")
	if template.status != "Published" or not template.active:
		frappe.throw(_("Select an active published Vehicle Specification Template."))
	if template.item_code and template.item_code != row.item_code:
		frappe.throw(_("The specification template does not match the quotation item."))
	item = frappe.get_doc("Item", row.item_code)
	item.check_permission("read")
	if not template.item_code and cstr(template.model).strip().casefold() not in {
		cstr(value).strip().casefold() for value in (item.name, item.item_name)
	}:
		frappe.throw(_("The specification template does not match the quotation item."))
	from an_truck.an_truck.doctype.vehicle_master.vehicle_master import get_template_specifications
	data = get_template_specifications(template.name)
	data.update({
		"schema_version": 1, "configuration": template.get("configuration_name") or "",
		"model_name_ar": template.get("model_name_ar") or template.model or template.template_name,
		"model_name_en": template.get("model_name_en") or template.model or template.template_name,
		"highlights": template.get("technical_highlights") or "",
		"images": {field: _asset(template.get(field)) for field in ASSET_FIELDS},
		"additional_images": [_asset(file.file_url) for file in template_photos(template.name)
			if file.file_url not in {template.get(field) for field in ASSET_FIELDS}],
		"warranty_terms": row.get(COMMERCIAL_FIELDS[0]) or template.get("quotation_warranty_terms") or "",
		"delivery_terms": row.get(COMMERCIAL_FIELDS[1]) or "",
	})
	# Assets/commercial metadata have dedicated places in the print layout.
	excluded = {*ASSET_FIELDS, "configuration_name", "configuration_of", "model_name_ar",
		"model_name_en", "technical_highlights", "quotation_warranty_terms"}
	section_names, heading = {}, ""
	for field in template.meta.fields:
		if field.fieldtype == "Section Break":
			heading = field.label
		section_names[field.fieldname] = heading
	for section in data["sections"]:
		base_label = section_names.get(section["fields"][0]["fieldname"], section["label"])
		section.update(label_ar=_(base_label, lang="ar"), label_en=base_label)
		section["fields"] = [dict(field, label_en=frappe.get_meta(TEMPLATE).get_field(field["fieldname"]).label,
			label_ar=_(frappe.get_meta(TEMPLATE).get_field(field["fieldname"]).label, lang="ar"))
			for field in section["fields"] if field["fieldname"] not in excluded]
		for field in section["fields"]:
			if field["fieldtype"] == "Table":
				field["value"] = [entry for entry in field["value"] if entry.get("value") not in (None, "")]
		section["fields"] = [field for field in section["fields"] if field["value"] not in (None, "", [])]
		# Unit defaults alone are not technical specifications.
		if section_names.get("payload_capacity") == base_label and not template.payload_capacity:
			section["fields"] = [field for field in section["fields"] if field["fieldname"] != "payload_capacity_unit"]
	data["sections"] = [section for section in data["sections"] if section["fields"]]
	return data


@frappe.whitelist()
def template_options(item_code=None, search="", start=0, page_length=30):
	"""Two bounded, permission-aware queries: explicit Item or exact model match."""
	if not item_code:
		return []
	item = frappe.get_doc("Item", item_code)
	item.check_permission("read")
	from frappe.utils import cint
	start, length = min(max(cint(start), 0), 10000), min(max(cint(page_length), 1), 100)
	rows = {}
	for match in ({"item_code": item_code}, {"item_code": ["in", ["", None]], "model": ["in", [item.name, item.item_name]]}):
		for row in frappe.get_list(TEMPLATE, filters={"status": "Published", "active": 1, **match},
			or_filters=[[TEMPLATE, key, "like", f"%{cstr(search).strip()[:100]}%"] for key in ("name", "template_name", "brand", "model")],
			fields=["name", "template_name", "revision", "modified"], order_by="modified desc", page_length=start + length):
			rows[row.name] = row
	return sorted(rows.values(), key=lambda row: row.modified, reverse=True)[start:start + length]


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def template_query(doctype, txt, searchfield, start, page_len, filters=None):
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	return [[row.name, row.template_name, row.revision] for row in template_options(filters.get("item_code"), txt, start, page_len)]


def _bank(doc):
	name = doc.get("custom_company_bank_account")
	if not name:
		return {}
	bank = frappe.get_doc("Bank Account", name)
	bank.check_permission("read")
	if not bank.is_company_account or bank.company != doc.company or bank.disabled:
		frappe.throw(_("Select an enabled bank account belonging to the quotation company."))
	return {key: bank.get(key) for key in ("account_name", "bank", "bank_account_no", "iban")}


def _commercial_context(doc):
	company = frappe.get_doc("Company", doc.company)
	customer = {}
	if doc.quotation_to == "Customer" and doc.party_name:
		party = frappe.get_doc("Customer", doc.party_name)
		from an_truck.portal_parties import _commercial_registration
		if party.has_permission("read"):
			customer = {"commercial_registration": _commercial_registration(party),
				"tax_id": party.tax_id, "mobile_no": doc.get("contact_mobile") or party.get("mobile_no") or ""}
	return {"bank": _bank(doc), "captured_at": now(), "customer": customer,
		"company": _company_print_details(company, doc) if company.has_permission("read") else {}}


def _company_print_details(company, doc):
	"""Approved Company/ZATCA facts only; never copy reference artwork's IDs."""
	data = {key: company.get(key) for key in ("company_name", "tax_id", "phone_no", "email", "website")}
	data["commercial_registration"] = ""
	# ZATCA's existing seller IDs are authoritative when one readable active
	# configuration exists. Multiple business units must not be chosen arbitrarily.
	if frappe.db.exists("DocType", "ZATCA Business Settings") and frappe.has_permission("ZATCA Business Settings", "read"):
		settings = frappe.get_list("ZATCA Business Settings", filters={"company": company.name, "status": "Active"}, pluck="name", page_length=2)
		if len(settings) == 1:
			seller = frappe.get_doc("ZATCA Business Settings", settings[0])
			data["company_name"] = seller.seller_name or data["company_name"]
			data["tax_id"] = seller.vat_registration_number or data["tax_id"]
			ids = [row.value for row in seller.other_ids if row.type_code == "CRN" and row.value]
			if len(set(ids)) == 1:
				data["commercial_registration"] = ids[0]
	if not data["tax_id"] and frappe.db.exists("DocType", "ZATCA Phase 1 Business Settings") and frappe.has_permission("ZATCA Phase 1 Business Settings", "read"):
		settings = frappe.get_list("ZATCA Phase 1 Business Settings", filters={"company": company.name, "status": "Active"},
			fields=["vat_registration_number"], page_length=2)
		if len(settings) == 1:
			data["tax_id"] = settings[0].vat_registration_number
	data["address"] = doc.get("company_address_display") or ""
	if not data["address"]:
		from erpnext.setup.doctype.company.company import get_default_company_address
		from frappe.contacts.doctype.address.address import get_address_display
		address = get_default_company_address(company.name)
		if address and frappe.has_permission("Address", "read", address):
			data["address"] = get_address_display(address)
	if not data["phone_no"] or not data["email"]:
		from frappe.contacts.doctype.contact.contact import get_default_contact
		contact = get_default_contact("Company", company.name)
		if contact and frappe.has_permission("Contact", "read", contact):
			person = frappe.get_doc("Contact", contact)
			data["phone_no"] = data["phone_no"] or person.phone or person.mobile_no
			data["email"] = data["email"] or person.email_id
	return data


def validate_quotation(doc, method=None):
	previous = doc.get_doc_before_save()
	if previous and previous.docstatus in (1, 2):
		if doc.company != previous.company or doc.get("custom_vehicle_quotation_context") != previous.get("custom_vehicle_quotation_context"):
			frappe.throw(_("Submitted quotation specifications cannot be changed."))
		old = {row.name: row for row in previous.items}
		new = {row.name: row for row in doc.items}
		if any(row.get(LINK) and name not in new for name, row in old.items()):
			frappe.throw(_("Submitted quotation specifications cannot be changed."))
		for row in doc.items:
			prior = old.get(row.name)
			if not prior and (row.get(LINK) or row.get(SNAPSHOT)):
				frappe.throw(_("Submitted quotation specifications cannot be changed."))
			if prior and prior.get(LINK) and row.item_code != prior.item_code:
				frappe.throw(_("Submitted quotation specifications cannot be changed."))
			if prior and any(row.get(key) != prior.get(key) for key in (LINK, SNAPSHOT, *COMMERCIAL_FIELDS)):
				frappe.throw(_("Submitted quotation specifications cannot be changed."))
		return
	if doc.docstatus == 2:
		return
	for row in doc.items:
		# Never accept client supplied snapshots, including during imports/amendments.
		row.set(SNAPSHOT, frappe.as_json(resolve_line(row, doc.company)))
	doc.custom_vehicle_quotation_context = frappe.as_json(_commercial_context(doc))


@frappe.whitelist(methods=["POST"])
def refresh_specifications(name):
	doc = frappe.get_doc("Quotation", name)
	doc.check_permission("write")
	if doc.docstatus != 0:
		frappe.throw(_("Only draft quotations can refresh specifications."))
	doc.save()
	return {"name": doc.name}


def quotation_print_data(doc):
	"""Called by Jinja. Never look up current specs for a submitted quotation."""
	doc.check_permission("read")
	frappe.get_doc("Company", doc.company).check_permission("read")
	context = json.loads(doc.get("custom_vehicle_quotation_context") or "{}")
	models, seen, lines = [], set(), []
	for row in doc.items:
		data = json.loads(row.get(SNAPSHOT) or "{}") if doc.docstatus else resolve_line(row, doc.company)
		lines.append(data)
		key = (data.get("template"), data.get("configuration"))
		if data and key not in seen:
			seen.add(key)
			models.append(data)
	if not doc.docstatus:
		context = _commercial_context(doc)
	data = {"lines": lines, "models": models, **{key: context.get(key, {}) for key in ("bank", "company", "customer")}}
	if not data["company"].get("address") and doc.get("company_address_display"):
		# This is the document's own saved address, not today's Company address.
		data["company"] = {**data["company"], "address": doc.company_address_display}
	# Tax descriptions/amounts always come from this Quotation. An Expense or
	# Chargeable account must never be presented as VAT because its rate is 15%.
	data["tax_rows"] = []
	for row in doc.taxes:
		kind = "Tax / Charge — ضريبة / رسوم"
		if frappe.has_permission("Account", "read", row.account_head):
			account_type = frappe.get_cached_value("Account", row.account_head, "account_type")
			kind = "Tax / ضريبة" if account_type == "Tax" else "Charge / رسوم"
		data["tax_rows"].append({"description": row.description or row.account_head,
			"rate": row.rate if row.charge_type == "On Net Total" else None,
			"amount": row.tax_amount_after_discount_amount, "kind": kind})
	from an_truck.quotation_presentation import layout
	return {**data, **layout(doc, data)}
