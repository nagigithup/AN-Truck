"""Archive populated legacy specifications before removing their form fields.

No Vehicle Master or technical-specification rows are changed or deleted. Frappe
retains the old physical columns as an additional recovery/read-compatibility path.
"""
import gzip
import hashlib

import frappe
from frappe import _


SHARED_FIELDS = (
	"brand", "model", "model_year", "vehicle_type", "drive_configuration", "country_of_origin",
	"specification_attachment", "overall_chassis_length_mm", "vehicle_width_mm", "cab_height_mm",
	"wheelbase_mm", "curb_weight_kg", "gross_vehicle_weight_kg", "gross_combination_weight_kg",
	"payload_capacity", "engine_model", "engine_type", "emission_standard", "horsepower_hp",
	"maximum_torque_nm", "number_of_cylinders", "engine_displacement_l", "fuel_type",
	"fuel_consumption", "fuel_consumption_unit_description", "transmission_brand", "transmission_model",
	"transmission", "forward_gears", "reverse_gears", "gear_ratio_details", "clutch_brand",
	"clutch_type", "clutch_specification", "brake_system_type", "abs", "brake_system_brand",
	"brake_system_description", "cabin_type", "number_of_seats", "sleeper_bed", "air_conditioning",
	"safety_features", "cabin_features_equipment", "number_of_axles", "front_axle_brand",
	"front_axle_type", "front_axle_capacity_ton", "rear_axle_brand", "rear_axle_type",
	"rear_axle_capacity_ton", "rear_axle_ratio", "front_tyre_size", "rear_tyre_size",
	"number_of_tyres", "tyre_specification_notes", "front_suspension_type", "rear_suspension_type",
	"suspension_description", "fuel_tank_material", "fuel_tank_capacity_l", "number_of_fuel_tanks",
	"fifth_wheel_size", "fifth_wheel_brand", "fifth_wheel_type", "specifications",
)


def execute():
	if not frappe.db.table_exists("Vehicle Master"):
		return
	populated = []
	for fieldname in SHARED_FIELDS:
		if not frappe.db.has_column("Vehicle Master", fieldname):
			continue
		fieldtype = frappe.db.get_value(
			"DocField", {"parent": "Vehicle Master", "fieldname": fieldname}, "fieldtype"
		)
		condition = f"coalesce(`{fieldname}`, 0) <> 0" if fieldtype in {
			"Check", "Int", "Float", "Currency", "Percent"
		} else f"coalesce(`{fieldname}`, '') <> ''"
		if frappe.db.sql(f"select name from `tabVehicle Master` where {condition} limit 1"):
			populated.append(fieldname)
	if frappe.db.table_exists("Vehicle Technical Specification") and frappe.db.exists(
		"Vehicle Technical Specification", {"parenttype": "Vehicle Master"}
	):
		populated.append("technical_specifications")
	if frappe.db.has_column("Vehicle Master", "payload_capacity_unit") and frappe.db.sql(
		"select name from `tabVehicle Master` where coalesce(payload_capacity_unit, '') not in ('', 'kg') limit 1"
	):
		populated.append("payload_capacity_unit")
	if populated:
		archive = _archive_legacy_specifications(populated)
		print(_("Legacy vehicle specifications archived before schema migration: {0}").format(archive.file_url))


def _archive_legacy_specifications(populated):
	"""Create a private, repeatable recovery snapshot; fail if it cannot be saved."""
	columns = set(frappe.db.get_table_columns("Vehicle Master"))
	fields = [field for field in ("name", "vin", "chassis_number", "modified", *SHARED_FIELDS, "payload_capacity_unit") if field in columns]
	vehicles = frappe.db.sql(
		"select " + ", ".join(f"`{field}`" for field in fields) + " from `tabVehicle Master` order by name",
		as_dict=True,
	)
	children = []
	if frappe.db.table_exists("Vehicle Technical Specification"):
		children = frappe.db.sql(
			"select * from `tabVehicle Technical Specification` where parenttype='Vehicle Master' order by parent, idx, name",
			as_dict=True,
		)
	payload = {
		"schema_version": 1,
		"source_doctype": "Vehicle Master",
		"populated_fields": populated,
		"fields": fields,
		"vehicles": vehicles,
		"technical_specifications": children,
	}
	content = frappe.as_json(payload).encode("utf-8")
	filename = f"vehicle-specifications-before-template-migration-{hashlib.sha256(content).hexdigest()[:16]}.json.gz"
	compressed = gzip.compress(content, mtime=0)
	existing = frappe.db.get_value("File", {"file_name": filename, "is_private": 1}, "name")
	if existing:
		archive = frappe.get_doc("File", existing)
		if archive.exists_on_disk() and archive.get_content(encodings=[]) == compressed:
			return archive
	archive = frappe.get_doc({
		"doctype": "File", "file_name": filename, "is_private": 1,
		"content": compressed, "folder": "Home",
	})
	archive.insert()
	stored = frappe.get_doc("File", archive.name)
	if not stored.exists_on_disk() or stored.get_content(encodings=[]) != compressed:
		frappe.throw(_("Could not verify the legacy vehicle specification archive. Migration stopped."))
	return archive
