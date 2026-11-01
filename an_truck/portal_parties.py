"""Employee portal adapters for standard ERPNext parties, contacts and addresses.

No permission bypasses: every document is read/saved as the requesting user.
Existing portal APIs remain available to their current consumers.
"""

import frappe
from frappe import _
from frappe.utils import cint, cstr


COMMERCIAL_REGISTRATION_FIELD = "commercial_registration_number"
COMMERCIAL_REGISTRATION_TYPE = "Commercial Registration Number"
COMMERCIAL_REGISTRATION_CODE = "CRN"
CUSTOMER_ADDRESS_FIELDS = (
	"country",
	"city",
	"district",
	"street",
	"building_number",
	"additional_number",
	"pincode",
	"short_address",
)


def _access(doctype, permission="read", company=None):
	if frappe.session.user == "Guest":
		frappe.throw(_("Sign in to use AN Truck Portal."), frappe.AuthenticationError)
	if not {"AN Truck Portal User", "System Manager"}.intersection(frappe.get_roles()):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if doctype not in ("Customer", "Supplier"):
		frappe.throw(_("Unsupported resource"))
	if not frappe.has_permission(doctype, permission):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if company:
		frappe.get_doc("Company", company).check_permission("read")


def _fields(doctype):
	prefix = doctype.lower()
	fields = [f"{prefix}_name", f"{prefix}_type", f"{prefix}_group", "territory" if doctype == "Customer" else "country", "tax_id", "default_currency", "disabled", f"{prefix}_details"]
	meta = frappe.get_meta(doctype)
	if doctype == "Supplier":
		fields += [
			f
			for f in ("commercial_registration_number", "custom_commercial_registration_number")
			if meta.has_field(f)
		][:1]
	return [f for f in fields if meta.has_field(f) and not meta.get_field(f).permlevel]


def _commercial_registration(doc):
	if doc.doctype != "Customer" or not doc.meta.has_field("custom_additional_ids"):
		return ""
	row = next(
		(
			row
			for row in doc.get("custom_additional_ids") or []
			if row.type_code == COMMERCIAL_REGISTRATION_CODE
			or row.type_name == COMMERCIAL_REGISTRATION_TYPE
		),
		None,
	)
	return cstr(row.value).strip() if row else ""


def _set_commercial_registration(doc, value):
	value = cstr(value).strip()[:140]
	if not doc.meta.has_field("custom_additional_ids"):
		if value:
			frappe.throw(
				_("Commercial Registration storage is not configured."), frappe.ValidationError
			)
		return
	row = next(
		(
			row
			for row in doc.get("custom_additional_ids") or []
			if row.type_code == COMMERCIAL_REGISTRATION_CODE
			or row.type_name == COMMERCIAL_REGISTRATION_TYPE
		),
		None,
	)
	if row:
		row.type_name = COMMERCIAL_REGISTRATION_TYPE
		row.type_code = COMMERCIAL_REGISTRATION_CODE
		row.value = value
	elif value:
		doc.append(
			"custom_additional_ids",
			{
				"type_name": COMMERCIAL_REGISTRATION_TYPE,
				"type_code": COMMERCIAL_REGISTRATION_CODE,
				"value": value,
			},
		)


@frappe.whitelist()
def get_options(doctype, company=None):
	_access(doctype, company=company)
	meta = frappe.get_meta(doctype)
	fields = []
	for name in _fields(doctype):
		field = meta.get_field(name)
		fields.append({"name": name, "label": field.label, "type": field.fieldtype, "required": bool(field.reqd), "options": field.options, "read_only": bool(field.read_only or field.permlevel)})
	if doctype == "Customer" and meta.has_field("custom_additional_ids"):
		fields.append(
			{
				"name": COMMERCIAL_REGISTRATION_FIELD,
				"label": _("Commercial Registration Number"),
				"type": "Data",
				"required": False,
				"options": None,
				"read_only": False,
			}
		)
	return {"fields": fields, "create": frappe.has_permission(doctype, "create"), "linked_permissions": {kind: bool(frappe.has_permission(kind.title(), "create")) for kind in ("contact", "address")}}


@frappe.whitelist()
def link_options(doctype, field, search="", company=None):
	_access(doctype, company=company)
	if field in _fields(doctype):
		df = frappe.get_meta(doctype).get_field(field)
		if df.fieldtype != "Link":
			frappe.throw(_("Unsupported field"))
		target = df.options
	elif field == "address_country":
		target = "Country"
	else:
		frappe.throw(_("Unsupported field"))
	filters = {"name": ["like", f"%{str(search)[:100]}%"]}
	if target in ("Customer Group", "Supplier Group", "Territory"):
		filters["is_group"] = 0
	return frappe.get_list(target, filters=filters, pluck="name", order_by="name", page_length=30)


@frappe.whitelist()
def list_parties(doctype, search="", filters=None, page=1, company=None):
	_access(doctype, company=company)
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	allowed = {f"{doctype.lower()}_group", f"{doctype.lower()}_type", "territory", "country", "disabled"}
	if not isinstance(filters, dict) or set(filters) - allowed:
		frappe.throw(_("Unsupported filter"))
	meta = frappe.get_meta(doctype)
	if any(not isinstance(v, (str, int, type(None))) for v in filters.values()):
		frappe.throw(_("Unsupported filter"))
	filters = {k: v for k, v in filters.items() if meta.has_field(k) and v not in (None, "")}
	if company and meta.has_field("company"):
		filters["company"] = company
	fields = ["name", "modified"] + [f for f in _fields(doctype) if not f.endswith("_details")]
	fields += [f for f in ("mobile_no", "email_id") if meta.has_field(f)]
	or_filters = []
	if search:
		term = f"%{str(search).strip()[:100]}%"
		or_filters = [[doctype, f, "like", term] for f in ("name", f"{doctype.lower()}_name", "tax_id", "mobile_no", "email_id") if f == "name" or meta.has_field(f)]
		# Phone numbers belong to standard linked Contacts, not portal custom fields.
		contacts = frappe.get_list("Contact", or_filters=[["Contact", f, "like", term] for f in ("phone", "mobile_no", "email_id")], pluck="name", page_length=100) if frappe.has_permission("Contact", "read") else []
		if contacts:
			or_filters.append([doctype, f"{doctype.lower()}_primary_contact", "in", contacts])
	page = max(1, cint(page))
	rows = frappe.get_list(doctype, filters=filters, or_filters=or_filters or None, fields=fields, order_by="modified desc", start=(page - 1) * 20, page_length=21)
	for row in rows[:20]:
		doc = frappe.get_doc(doctype, row.name)
		row["can_write"] = bool(frappe.has_permission(doctype, "write", doc=doc))
		contact = _linked(doc, "contact")
		row["phone"] = contact.phone if contact else None
	return {"rows": rows[:20], "has_more": len(rows) > 20, "page": page}


def _linked(doc, kind, permission="read"):
	name = doc.get(f"{doc.doctype.lower()}_primary_{kind}")
	if not name and kind == "address":
		filters = [
			["Dynamic Link", "link_doctype", "=", doc.doctype],
			["Dynamic Link", "link_name", "=", doc.name],
			["Address", "disabled", "=", 0],
		]
		# A shipping-only address must not become the billing address merely
		# because it was the most recently edited linked Address.
		if doc.doctype in ("Customer", "Supplier"):
			filters.append(["Address", "address_type", "=", "Billing"])
		rows = frappe.get_list(
			"Address",
			filters=filters,
			fields=["name"],
			order_by="is_primary_address desc, modified desc",
			page_length=1,
		)
		name = rows[0].name if rows else None
	if not name:
		return None
	linked = frappe.get_doc(kind.title(), name)
	if not any(row.link_doctype == doc.doctype and row.link_name == doc.name for row in linked.links):
		frappe.throw(_("The linked document does not belong to this record."))
	if permission == "read" and not frappe.has_permission(linked.doctype, "read", doc=linked):
		return None
	linked.check_permission(permission)
	return linked


@frappe.whitelist()
def get_party(doctype, name, company=None):
	_access(doctype, company=company)
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	if company and doc.meta.has_field("company") and doc.company != company:
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	data = {f: doc.get(f) for f in _fields(doctype)}
	contact, address = _linked(doc, "contact"), _linked(doc, "address")
	if doctype == "Customer":
		if not data.get("tax_id") and doc.meta.has_field("custom_vat_registration_number"):
			data["tax_id"] = doc.get("custom_vat_registration_number") or ""
		data[COMMERCIAL_REGISTRATION_FIELD] = _commercial_registration(doc)
	data["contact"] = {f: contact.get(f) if contact else "" for f in ("first_name", "email_id", "mobile_no", "phone")}
	if doctype == "Customer":
		data["address"] = {
			"country": address.get("country") if address else "",
			"city": address.get("city") if address else "",
			"district": address.get("custom_area") if address else "",
			"street": address.get("address_line1") if address else "",
			"building_number": address.get("custom_building_number") if address else "",
			"additional_number": address.get("custom_additional_number") if address else "",
			"pincode": address.get("pincode") if address else "",
			"short_address": address.get("custom_short_address") if address else "",
		}
	else:
		data["address"] = {f: address.get(f) if address else "" for f in ("country", "city", "address_line1", "address_line2", "pincode")}
		# Add national-address aliases while preserving the legacy supplier API
		# keys consumed by the existing full-page form and integrations.
		data["address"].update({
			"district": address.get("custom_area") if address else "",
			"street": address.get("address_line1") if address else "",
			"building_number": address.get("custom_building_number") if address else "",
			"additional_number": address.get("custom_additional_number") if address else "",
			"short_address": address.get("custom_short_address") if address else "",
		})
	return {"record": data, "modified": str(doc.modified), "can_write": bool(frappe.has_permission(doctype, "write", doc=doc)), "linked_permissions": {kind: bool(frappe.has_permission(kind.title(), "write", doc=linked)) if linked else (not doc.get(f"{doctype.lower()}_primary_{kind}") and bool(frappe.has_permission(kind.title(), "create"))) for kind, linked in (("contact", contact), ("address", address))}}


def _customer_address_values(values):
	if not isinstance(values, dict) or set(values) - set(CUSTOMER_ADDRESS_FIELDS):
		frappe.throw(_("Unsupported field"), frappe.ValidationError)
	clean = {}
	for key in CUSTOMER_ADDRESS_FIELDS:
		value = values.get(key)
		if not isinstance(value, (str, type(None))):
			frappe.throw(_("Unsupported field"), frappe.ValidationError)
		clean[key] = cstr(value).strip()
	return {
		"country": clean["country"],
		"city": clean["city"],
		"custom_area": clean["district"],
		"address_line1": clean["street"],
		"custom_building_number": clean["building_number"],
		"custom_additional_number": clean["additional_number"],
		"pincode": clean["pincode"],
		"custom_short_address": clean["short_address"].upper(),
	}


def _save_linked(doc, kind, values):
	if not isinstance(values, dict):
		frappe.throw(_("Unsupported field"), frappe.ValidationError)
	if kind != "address" or doc.doctype != "Customer":
		if any(not isinstance(value, (str, type(None))) for value in values.values()):
			frappe.throw(_("Unsupported field"), frappe.ValidationError)
	if kind == "contact":
		allowed = {"first_name", "email_id", "mobile_no", "phone"}
	elif doc.doctype == "Customer":
		values = _customer_address_values(values)
		allowed = set(values)
	else:
		allowed = set(CUSTOMER_ADDRESS_FIELDS) | {"address_line1", "address_line2"}
		if set(values) - allowed:
			frappe.throw(_("Unsupported field"))
		mapping = {"district": "custom_area", "street": "address_line1", "building_number": "custom_building_number", "additional_number": "custom_additional_number", "short_address": "custom_short_address"}
		mapped = {mapping.get(key, key): cstr(value).strip() for key, value in values.items()}
		if "address_line1" in values:
			# The full-page supplier form still edits the legacy street key.
			mapped["address_line1"] = cstr(values["address_line1"]).strip()
		values = mapped
		allowed = set(values)
	if set(values) - allowed:
		frappe.throw(_("Unsupported field"))
	if not any(values.values()) and not doc.get(f"{doc.doctype.lower()}_primary_{kind}"):
		return
	linked = _linked(doc, kind, "write")
	if linked:
		linked.check_permission("read")
	if linked and all((linked.get(k) or "") == (v or "") for k, v in values.items()):
		if kind == "address":
			doc.set(f"{doc.doctype.lower()}_primary_address", linked.name)
		return
	if linked and len(linked.links) > 1:
		frappe.throw(_("This contact or address is shared. Update it in Desk."))
	if not linked:
		linked = frappe.new_doc(kind.title())
		linked.check_permission("create")
		linked.append("links", {"link_doctype": doc.doctype, "link_name": doc.name})
	if kind == "address":
		missing_fields = [
			label
			for fieldname, label in (
				("country", _("Country")),
				("city", _("City")),
				("address_line1", _("Street")),
			)
			if any(values.values()) and not values.get(fieldname)
		]
		if missing_fields:
			frappe.throw(
				_("Please complete required address fields: {0}").format(", ".join(missing_fields)),
				frappe.MandatoryError,
			)
		for fieldname, value in values.items():
			if not linked.meta.has_field(fieldname) and value:
				frappe.throw(
					_("National Address fields are not installed. Run the site migration."),
					frappe.ValidationError,
				)
		linked.update(values)
		linked.address_title = doc.get(f"{doc.doctype.lower()}_name")
		linked.address_type = linked.address_type or "Billing"
		linked.is_primary_address = 1
	else:
		if "first_name" in values or linked.is_new():
			linked.first_name = values.get("first_name") or doc.get(f"{doc.doctype.lower()}_name")
		# Replace primary values only; preserve secondary contact channels.
		if "email_id" in values:
			linked.set("email_ids", [r for r in linked.email_ids if not r.is_primary and r.email_id != values["email_id"]])
			if values["email_id"]:
				linked.append("email_ids", {"email_id": values["email_id"], "is_primary": 1})
		for field, flag in (("mobile_no", "is_primary_mobile_no"), ("phone", "is_primary_phone")):
			if field in values:
				for row in linked.phone_nos:
					if row.get(flag):
						row.set(flag, 0)
				if values[field]:
					row = next((r for r in linked.phone_nos if r.phone == values[field]), None)
					if row:
						row.set(flag, 1)
					else:
						linked.append("phone_nos", {"phone": values[field], flag: 1})
	linked.save()
	doc.set(f"{doc.doctype.lower()}_primary_{kind}", linked.name)


@frappe.whitelist(methods=["POST"])
def save_party(doctype, data, name=None, modified=None, company=None):
	# Keep the same atomic behavior for HTTP callers and internal callers that
	# catch validation errors and continue their surrounding transaction.
	savepoint = "portal_party_" + frappe.generate_hash(length=10)
	frappe.db.savepoint(savepoint)
	try:
		result = _save_party(doctype, data, name, modified, company)
	except Exception:
		frappe.db.rollback(save_point=savepoint)
		frappe.db.release_savepoint(savepoint)
		raise
	frappe.db.release_savepoint(savepoint)
	return result


def _save_party(doctype, data, name=None, modified=None, company=None):
	_access(doctype, "write" if name else "create", company)
	data = frappe.parse_json(data) if isinstance(data, str) else data
	extra_fields = {COMMERCIAL_REGISTRATION_FIELD} if doctype == "Customer" else set()
	if not isinstance(data, dict) or set(data) - set(_fields(doctype)) - extra_fields - {"contact", "address"}:
		frappe.throw(_("Unsupported field"))
	doc = frappe.get_doc(doctype, name) if name else frappe.new_doc(doctype)
	doc.check_permission("write" if name else "create")
	if name:
		doc.check_permission("read")
		if str(doc.modified) != str(modified):
			frappe.throw(_("This record changed. Reload it before saving."), frappe.TimestampMismatchError)
	if company and doc.meta.has_field("company"):
		if name and doc.company != company:
			frappe.throw(_("Not permitted"), frappe.PermissionError)
		doc.company = company
	for key in _fields(doctype):
		if key in data:
			field = doc.meta.get_field(key)
			if field.read_only or field.permlevel:
				if data[key] != doc.get(key):
					frappe.throw(_("Not permitted"), frappe.PermissionError)
				continue
			if not isinstance(data[key], (str, int, float, type(None))):
				frappe.throw(_("Unsupported field"))
			doc.set(key, data[key])
	if doctype == "Customer":
		if COMMERCIAL_REGISTRATION_FIELD in data:
			if not isinstance(data[COMMERCIAL_REGISTRATION_FIELD], (str, type(None))):
				frappe.throw(_("Unsupported field"), frappe.ValidationError)
			_set_commercial_registration(doc, data[COMMERCIAL_REGISTRATION_FIELD])
		# KSA Compliance print formats and e-invoice helpers use this custom VAT
		# field in some installations. Keep it aligned with ERPNext's standard
		# tax_id without creating a second editable value in the portal.
		if "tax_id" in data and doc.meta.has_field("custom_vat_registration_number"):
			doc.custom_vat_registration_number = cstr(data.get("tax_id")).strip()
	missing = [_(doc.meta.get_field(key).label) for key in _fields(doctype) if doc.meta.get_field(key).reqd and doc.get(key) in (None, "")]
	if missing:
		frappe.throw(_("Please complete required fields: {0}").format(", ".join(missing)), frappe.MandatoryError)
	# Exact name + tax identity is a duplicate; shared phones/emails alone are not.
	party_name = f"{doctype.lower()}_name"
	if doc.get("tax_id") and frappe.db.exists(doctype, {party_name: doc.get(party_name), "tax_id": doc.tax_id, "name": ["!=", name or ""]}):
		frappe.throw(_("A record with this name and Tax ID already exists."))
	doc.save()
	doc.reload()
	for kind in ("contact", "address"):
		if kind in data:
			_save_linked(doc, kind, data[kind])
	# Contact hooks may update the party's cached contact values and modified time.
	# Reload those values, retaining newly selected primary links, before saving.
	links = {f"{doctype.lower()}_primary_{kind}": doc.get(f"{doctype.lower()}_primary_{kind}") for kind in ("contact", "address")}
	doc.reload()
	doc.update(links)
	doc.save()
	doc.reload()
	return {"name": doc.name, "modified": str(doc.modified)}
