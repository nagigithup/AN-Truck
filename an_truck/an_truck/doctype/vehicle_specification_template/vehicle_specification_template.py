import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, now


SPECIFICATION_FIELDS = (
	"model_name_ar", "model_name_en", "configuration_of", "configuration_name",
	"main_vehicle_photo", "technical_photo", "cabin_photo", "technical_highlights", "quotation_warranty_terms",
	"brand", "model", "model_year", "vehicle_type", "drive_configuration",
	"specification_attachment", "default_country_of_origin", "overall_chassis_length_mm",
	"vehicle_width_mm", "cab_height_mm", "wheelbase_mm", "curb_weight_kg",
	"gross_vehicle_weight_kg", "gross_combination_weight_kg", "payload_capacity",
	"payload_capacity_unit", "engine_model", "engine_type", "emission_standard",
	"horsepower_hp", "maximum_torque_nm", "number_of_cylinders", "engine_displacement_l",
	"fuel_type", "fuel_consumption", "fuel_consumption_unit_description", "transmission_brand",
	"transmission_model", "transmission", "forward_gears", "reverse_gears",
	"gear_ratio_details", "clutch_brand", "clutch_type", "clutch_specification",
	"brake_system_type", "abs", "brake_system_brand", "brake_system_description",
	"cabin_type", "number_of_seats", "sleeper_bed", "air_conditioning", "safety_features",
	"cabin_features_equipment", "number_of_axles", "front_axle_brand", "front_axle_type",
	"front_axle_capacity_ton", "rear_axle_brand", "rear_axle_type", "rear_axle_capacity_ton",
	"rear_axle_ratio", "front_tyre_size", "rear_tyre_size", "number_of_tyres",
	"tyre_specification_notes", "front_suspension_type", "rear_suspension_type",
	"suspension_description", "fuel_tank_material", "fuel_tank_capacity_l",
	"number_of_fuel_tanks", "fifth_wheel_size", "fifth_wheel_brand", "fifth_wheel_type",
	"specifications",
)


class VehicleSpecificationTemplate(Document):
	def autoname(self):
		base = re.sub(r"\s+", " ", (self.template_name or "").strip())
		if not base:
			frappe.throw(_("Template Name is required."))
		self.template_name = base
		self.name = f"{base}-R{cint(self.revision) or 1}"

	def before_insert(self):
		self.status = "Draft"
		self.published_on = None
		self.published_by = None
		self.revision = cint(self.revision) or 1
		if self.revised_from:
			source = frappe.get_doc("Vehicle Specification Template", self.revised_from)
			source.check_permission("read")
			if source.status != "Published":
				frappe.throw(_("Only a published template can be revised."))
			self.template_name = source.template_name
			# Lock the lineage while allocating the next immutable revision.
			frappe.get_doc("Vehicle Specification Template", source.name, for_update=True)
			self.revision = cint(frappe.db.get_value(
				"Vehicle Specification Template", {"template_name": source.template_name},
				"revision", order_by="revision desc",
			)) + 1

	def validate(self):
		self.template_name = (self.template_name or "").strip()
		self.item_code = self.item_code or ""
		previous = self.get_doc_before_save()
		if self.configuration_of and (not previous or any(self.get(key) != previous.get(key) for key in ("configuration_of", "configuration_name", "item_code"))):
			base = _template(self.configuration_of)
			if base.name == self.name or base.status != "Published" or not self.configuration_name:
				frappe.throw(_("Configurations require a published base template and a configuration name."))
			if base.item_code != self.item_code:
				frappe.throw(_("Configuration and base template must use the same Item."))
		from an_truck.vehicle_quotation import ASSET_FIELDS, _asset
		for field in ASSET_FIELDS:
			_asset(self.get(field))
		if frappe.db.exists(
			"Vehicle Specification Template",
			{"template_name": self.template_name, "revision": self.revision, "name": ["!=", self.name]},
		):
			frappe.throw(_("Template revision already exists."))
		if previous and previous.published_on:
			changed = [field for field in SPECIFICATION_FIELDS if self.get(field) != previous.get(field)]
			if any(self.get(field) != previous.get(field) for field in (
				"item_code", "template_name", "revision", "revised_from", "description", "published_on", "published_by"
			)):
				changed.append("template")
			if self._technical_rows() != _technical_rows(previous):
				changed.append("technical_specifications")
			if changed:
				frappe.throw(_("Published template revisions are immutable. Create a new revision."))
			if self.status not in {"Published", "Inactive"}:
				frappe.throw(_("Published template revisions are immutable. Create a new revision."))
		if self.status == "Published" and not self.published_on:
			self.published_on = now()
			self.published_by = frappe.session.user
		if self.status == "Inactive":
			self.active = 0

	def _technical_rows(self):
		return _technical_rows(self)

	def on_trash(self):
		if self.published_on:
			frappe.throw(_("Published template revisions cannot be deleted."))

	def before_rename(self, old, new, merge=False):
		frappe.throw(_("Specification template revisions cannot be renamed."))


def _technical_rows(doc):
	return [
		(row.specification_category, row.specification_name, row.value, row.uom, row.notes)
		for row in doc.get("technical_specifications") or []
	]


def _template(name, permission="read"):
	doc = frappe.get_doc("Vehicle Specification Template", name)
	doc.check_permission(permission)
	return doc


@frappe.whitelist(methods=["POST"])
def publish_template(name):
	doc = _template(name, "write")
	if doc.status != "Draft":
		frappe.throw(_("Only draft templates can be published."))
	doc.status = "Published"
	doc.active = 1
	doc.save()
	return {"name": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def create_revision(name):
	source = _template(name)
	if not frappe.has_permission("Vehicle Specification Template", "create"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if source.status != "Published":
		frappe.throw(_("Only a published template can be revised."))
	doc = frappe.new_doc("Vehicle Specification Template")
	doc.template_name = source.template_name
	doc.revised_from = source.name
	doc.item_code = source.item_code
	doc.description = source.description
	for field in SPECIFICATION_FIELDS:
		doc.set(field, source.get(field))
	for row in source.technical_specifications:
		doc.append("technical_specifications", {
			"specification_category": row.specification_category,
			"specification_name": row.specification_name,
			"value": row.value,
			"uom": row.uom,
			"notes": row.notes,
		})
	doc.insert()
	# Reuse the managed files without copying their bytes or changing the source.
	for row in frappe.get_all("File", filters={"attached_to_doctype": source.doctype,
		"attached_to_name": source.name, "is_folder": 0,
		"file_type": ["in", ["JPG", "JPEG", "PNG", "WEBP", "GIF"]]}, pluck="name"):
		file = frappe.get_doc("File", row)
		file.check_permission("read")
		frappe.get_doc({"doctype": "File", "file_name": file.file_name, "file_url": file.file_url,
			"is_private": file.is_private, "attached_to_doctype": doc.doctype,
			"attached_to_name": doc.name}).insert()
	return {"name": doc.name, "revision": doc.revision}


def _company_filter(company):
	if not company:
		return {}
	frappe.get_doc("Company", company).check_permission("read")
	return {"company": company}


@frappe.whitelist()
def get_linked_vehicles(template, search="", status="", company=None, page=1, page_length=20):
	_template(template)
	if not frappe.has_permission("Vehicle Master", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	filters = {"specification_template": template, **_company_filter(company)}
	if status:
		valid = {
			value.strip()
			for value in (frappe.get_meta("Vehicle Master").get_field("vehicle_status").options or "").splitlines()
			if value.strip()
		}
		if status not in valid:
			frappe.throw(_("Select a valid vehicle status."))
		filters["vehicle_status"] = status
	or_filters = None
	if search := str(search or "").strip()[:100]:
		term = f"%{search}%"
		or_filters = [["Vehicle Master", field, "like", term] for field in ("vin", "chassis_number", "color", "engine_number")]
	page = max(cint(page), 1)
	page_length = min(max(cint(page_length), 1), 100)
	rows = frappe.get_list(
		"Vehicle Master",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "vin", "chassis_number", "color", "vehicle_status", "engine_number", "receipt_date", "company"],
		order_by="receipt_date desc, modified desc",
		start=(page - 1) * page_length,
		page_length=page_length,
	)
	count_rows = frappe.get_list(
		"Vehicle Master",
		filters=filters,
		or_filters=or_filters,
		fields=[{"COUNT": "name", "as": "total"}],
		page_length=1,
	)
	total = cint(count_rows[0].total) if count_rows else 0
	return {
		"rows": rows,
		"total": total,
		"page": page,
		"page_length": page_length,
		"has_more": page * page_length < total,
		"statuses": [value.strip() for value in (frappe.get_meta("Vehicle Master").get_field("vehicle_status").options or "").splitlines() if value.strip()],
	}


@frappe.whitelist()
def get_linked_vehicle_count(template, company=None):
	return get_linked_vehicles(template, company=company, page=1, page_length=1)["total"]


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def template_query(doctype, txt, searchfield, start, page_len, filters=None):
	if not frappe.has_permission("Vehicle Specification Template", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	conditions = {"active": 1, "status": "Published"}
	if filters.get("item_code"):
		conditions["item_code"] = ["in", ["", filters["item_code"]]]
	rows = frappe.get_list(
		"Vehicle Specification Template", filters=conditions,
		or_filters=[["Vehicle Specification Template", field, "like", f"%{str(txt or '')[:100]}%"] for field in ("name", "template_name", "brand", "model")],
		fields=["name", "template_name", "revision"], order_by="modified desc",
		start=max(cint(start), 0), page_length=min(max(cint(page_len), 1), 100),
	)
	return [[row.name, row.template_name, row.revision] for row in rows]


def protect_published_template_file(doc, method=None):
	"""File deletion must not silently clear a published revision's attachment."""
	if not frappe.db.exists("DocType", "Vehicle Specification Template"):
		return
	previous = doc.get_doc_before_save() if not doc.is_new() else None
	changing = method == "on_trash" or doc.is_new() or any(
		doc.has_value_changed(field) for field in ("file_url", "attached_to_doctype", "attached_to_name")
	)
	if not changing:
		return
	for record in (doc, previous):
		if not record:
			continue
		attached_published = (
			record.attached_to_doctype == "Vehicle Specification Template"
			and record.attached_to_name
			and frappe.db.get_value("Vehicle Specification Template", record.attached_to_name, "published_on")
		)
		referenced_published = not doc.is_new() and record.file_url and any(frappe.db.exists(
			"Vehicle Specification Template", {field: record.file_url, "published_on": ["is", "set"]}
		) for field in ("specification_attachment", "main_vehicle_photo", "technical_photo", "cabin_photo"))
		if referenced_published and not attached_published and record.attached_to_doctype == "Vehicle Specification Template":
			# Removing a draft revision's File link is safe when a protected,
			# published revision still owns the same physical file (same hash).
			owners = frappe.get_all("File", filters={"file_url": record.file_url,
				"content_hash": record.content_hash, "name": ["!=", doc.name],
				"attached_to_doctype": "Vehicle Specification Template"}, pluck="attached_to_name") if record.content_hash else []
			if owners and frappe.db.exists("Vehicle Specification Template", {"name": ["in", owners], "published_on": ["is", "set"]}):
				referenced_published = False
		if attached_published or referenced_published:
			frappe.throw(_("Published template revisions are immutable. Create a new revision."))


class PublishedTemplateFileGuard:
	"""Run before standard File methods perform filesystem changes."""
	def before_insert(self):
		protect_published_template_file(self, "before_insert")
		return super().before_insert()

	def validate(self):
		protect_published_template_file(self, "validate")
		return super().validate()

	def on_trash(self):
		protect_published_template_file(self, "on_trash")
		return super().on_trash()
