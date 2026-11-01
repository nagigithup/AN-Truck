import csv

import frappe
from frappe.tests import IntegrationTestCase

from an_truck.an_truck.doctype.vehicle_master.vehicle_master import VehicleMaster
from an_truck.patches.v1_0.verify_vehicle_specification_fields_empty import SHARED_FIELDS


class TestVehicleMasterSpecifications(IntegrationTestCase):
	def test_vehicle_master_contains_operational_fields_and_template_reference(self):
		meta = frappe.get_meta("Vehicle Master")
		self.assertEqual(meta.get_field("vin").label, "VIN / Chassis Number")
		self.assertTrue(meta.get_field("vin").unique)
		self.assertEqual(meta.get_field("specification_template").options, "Vehicle Specification Template")
		self.assertFalse(meta.get_field("specification_template").reqd, "Existing records remain valid")
		for field in SHARED_FIELDS:
			self.assertFalse(meta.has_field(field), field)
		for field in ("engine_number", "color", "manufacturing_date", "vehicle_photo", "specification_exceptions", "purchase_receipt", "purchase_receipt_item", "sales_invoice", "delivery_note", "company", "warehouse", "receipt_date", "plate_number"):
			self.assertTrue(meta.has_field(field), field)
		self.assertFalse(meta.has_field("technical_specifications"))
		self.assertEqual(frappe.get_meta("Vehicle Specification Template").get_field("technical_specifications").options, "Vehicle Technical Specification")

	def test_vehicle_master_filters_include_template(self):
		meta = frappe.get_meta("Vehicle Master")
		self.assertEqual(meta.title_field, "vin")
		self.assertEqual({field.fieldname for field in meta.fields if field.in_standard_filter}, {
			"vin", "item_name", "specification_template", "vehicle_status", "plate_number", "vehicle_import_file", "supplier", "customer",
		})

	def test_arabic_labels_complete_without_duplicate_keys(self):
		with open(frappe.get_app_path("an_truck", "translations", "ar.csv"), encoding="utf-8", newline="") as handle:
			rows = list(csv.reader(handle))
		keys = [row[0] for row in rows if row]
		self.assertEqual(len(keys), len(set(keys)))
		translations = {row[0]: row[1] for row in rows if len(row) >= 2}
		labels = {field.label for doctype in ("Vehicle Master", "Vehicle Specification Template", "Vehicle Technical Specification") for field in frappe.get_meta(doctype).fields if field.label and not field.hidden}
		self.assertFalse(sorted(labels - set(translations)))

	def test_registration_expiry_cannot_precede_registration(self):
		vehicle = VehicleMaster({"doctype": "Vehicle Master", "registration_date": "2026-10-10", "registration_expiry_date": "2026-10-09"})
		with self.assertRaises(frappe.ValidationError):
			vehicle.validate_registration_dates()
