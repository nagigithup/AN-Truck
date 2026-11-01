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
		frappe.throw(
			_("Vehicle specification migration stopped because these Vehicle Master fields contain data: {0}. Review and approve a migration plan before continuing.").format(
				", ".join(populated)
			)
		)
