import csv

import frappe
from frappe.tests import IntegrationTestCase

from an_truck.an_truck.doctype.vehicle_master.vehicle_master import VehicleMaster


class TestVehicleMasterSpecifications(IntegrationTestCase):
	def test_structured_vehicle_specifications_preserve_existing_cost_and_links(self):
		name = frappe.db.get_value("Vehicle Master", {"disabled": 0}, "name")
		if not name:
			self.skipTest("A Vehicle Master fixture is required.")
		vehicle = frappe.get_doc("Vehicle Master", name)
		original = {
			"vin": vehicle.vin,
			"item_code": vehicle.item_code,
			"purchase_receipt": vehicle.purchase_receipt,
			"final_valuation_rate": vehicle.final_valuation_rate,
		}
		vehicle.update({
			"vehicle_type": "Truck Head / Tractor Head",
			"drive_configuration": "4x2",
			"overall_chassis_length_mm": 6310,
			"vehicle_width_mm": 2540,
			"cab_height_mm": 3880,
			"wheelbase_mm": 3800,
			"curb_weight_kg": 7720,
			"gross_combination_weight_kg": 50000,
			"engine_model": "YCK11460",
			"horsepower_hp": 460,
			"maximum_torque_nm": 2200,
			"transmission_brand": "FAST",
			"transmission_model": "F12JZ22A",
			"transmission": "Automatic",
		})
		vehicle.append("technical_specifications", {
			"specification_category": "Manufacturer",
			"specification_name": "Special Package",
			"value": "Regional",
			"notes": "Test-only transactional fixture",
		})
		vehicle.save(ignore_permissions=True)
		vehicle.reload()
		self.assertEqual(vehicle.vin, original["vin"])
		self.assertEqual(vehicle.item_code, original["item_code"])
		self.assertEqual(vehicle.purchase_receipt, original["purchase_receipt"])
		self.assertAlmostEqual(vehicle.final_valuation_rate, original["final_valuation_rate"])
		self.assertEqual(vehicle.engine_model, "YCK11460")
		self.assertIn("Special Package", {row.specification_name for row in vehicle.technical_specifications})

	def test_vehicle_master_layout_reuses_existing_fields(self):
		meta = frappe.get_meta("Vehicle Master")
		self.assertEqual(meta.get_field("vin").label, "VIN / Chassis Number")
		self.assertEqual(meta.get_field("transmission").label, "Transmission Type")
		self.assertIsNone(meta.get_field("transmission_type"))
		self.assertEqual(meta.get_field("technical_specifications").options, "Vehicle Technical Specification")
		self.assertTrue(frappe.get_meta("Vehicle Technical Specification").istable)
		sections = [field.fieldname for field in meta.fields if field.fieldtype == "Section Break"]
		expected = [
			"identification_section", "chassis_dimensions_section", "weights_capacity_section",
			"engine_specifications_section", "transmission_section", "clutch_section",
			"braking_system_section", "cabin_specifications_section", "axles_section",
			"tyres_section", "suspension_section", "fuel_tank_section", "fifth_wheel_section",
			"additional_specifications_section", "registration_section",
			"import_and_purchasing_references", "cost_information", "sales_references", "notes_section",
		]
		self.assertEqual(sections, expected)

	def test_vehicle_master_standard_filters_are_limited_to_operational_fields(self):
		meta = frappe.get_meta("Vehicle Master")
		self.assertEqual(meta.title_field, "vin")
		standard_filters = {
			field.fieldname for field in meta.fields if field.in_standard_filter
		}
		self.assertEqual(standard_filters, {
			"vin", "item_name", "vehicle_status", "plate_number",
			"vehicle_import_file", "supplier", "customer",
		})
		self.assertEqual(
			meta.search_fields,
			"vin,item_name,vehicle_status,plate_number,vehicle_import_file,supplier,customer",
		)

	def test_vehicle_master_arabic_labels_are_complete_and_unambiguous(self):
		with open(frappe.get_app_path("an_truck", "translations", "ar.csv"), encoding="utf-8", newline="") as handle:
			rows = list(csv.reader(handle))
		keys = [row[0] for row in rows if row]
		self.assertEqual(len(keys), len(set(keys)), "Arabic translations contain duplicate source labels")
		translations = {row[0]: row[1] for row in rows if len(row) >= 2}
		labels = set()
		for doctype in ("Vehicle Master", "Vehicle Technical Specification"):
			labels.update(
				field.label for field in frappe.get_meta(doctype).fields
				if field.label and not field.hidden
			)
		missing = sorted(labels - set(translations))
		self.assertFalse(missing, f"Untranslated Vehicle Master labels: {missing}")
		self.assertEqual(translations["VIN / Chassis Number"], "رقم الشاسيه")
		self.assertEqual(translations["Vehicle Identity"], "بيانات المركبة")
		self.assertEqual(translations["Sales & Warranty"], "المبيعات والضمان")
		self.assertEqual(translations["Item Name"], "اسم السيارة")

	def test_registration_expiry_cannot_precede_registration(self):
		vehicle = VehicleMaster({
			"doctype": "Vehicle Master",
			"registration_date": "2026-10-10",
			"registration_expiry_date": "2026-10-09",
		})
		with self.assertRaises(frappe.ValidationError):
			vehicle.validate_registration_dates()
