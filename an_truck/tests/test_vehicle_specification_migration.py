"""Regression coverage for the populated-field migration failure on Cloud."""
import gzip
import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from an_truck.patches.v1_0 import verify_vehicle_specification_fields_empty as migration


class TestVehicleSpecificationMigration(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.user = frappe.session.user
		frappe.set_user("Administrator")

	def tearDown(self):
		# Full rollback also executes File's rollback cleanup for private files.
		frappe.db.rollback()
		frappe.set_user(self.user)
		super().tearDown()

	def test_cloud_populated_fields_are_archived_instead_of_blocking(self):
		fields = {"brand", "model", "model_year", "country_of_origin", "engine_type", "fuel_type", "transmission"}
		with (
			patch.object(frappe.db, "table_exists", side_effect=lambda name: name == "Vehicle Master"),
			patch.object(frappe.db, "has_column", side_effect=lambda doctype, field: field in fields),
			patch.object(frappe.db, "get_value", return_value="Data"),
			patch.object(frappe.db, "sql", return_value=[("VIN-UNCHANGED",)]),
			patch.object(migration, "_archive_legacy_specifications") as archive,
		):
			archive.return_value.file_url = "/private/files/legacy-specifications.json.gz"
			migration.execute()
			archive.assert_called_once_with([field for field in migration.SHARED_FIELDS if field in fields])

	def test_numeric_zeros_do_not_block_or_require_an_archive(self):
		with (
			patch.object(frappe.db, "table_exists", side_effect=lambda name: name == "Vehicle Master"),
			patch.object(frappe.db, "has_column", side_effect=lambda doctype, field: field in {"model_year", "horsepower_hp"}),
			patch.object(frappe.db, "get_value", return_value="Float"),
			patch.object(frappe.db, "sql", return_value=[]),
			patch.object(migration, "_archive_legacy_specifications") as archive,
		):
			migration.execute()
			archive.assert_not_called()

	def test_archive_failure_still_stops_migration(self):
		with (
			patch.object(frappe.db, "table_exists", side_effect=lambda name: name == "Vehicle Master"),
			patch.object(frappe.db, "has_column", side_effect=lambda doctype, field: field == "brand"),
			patch.object(frappe.db, "get_value", return_value="Data"),
			patch.object(frappe.db, "sql", return_value=[("VIN-UNCHANGED",)]),
			patch.object(migration, "_archive_legacy_specifications", side_effect=OSError("archive storage failure")),
		):
			with self.assertRaisesRegex(OSError, "archive storage failure"):
				migration.execute()

	def test_private_archive_round_trip_is_repeatable_and_never_changes_vehicles(self):
		before = frappe.db.sql("select * from `tabVehicle Master` order by name", as_dict=True)
		children_before = frappe.db.sql("select * from `tabVehicle Technical Specification` where parenttype='Vehicle Master' order by parent, idx, name", as_dict=True)
		archive = migration._archive_legacy_specifications(["brand", "model", "model_year"])
		self.assertEqual(archive.is_private, 1)
		self.assertTrue(archive.file_url.startswith("/private/files/"))
		stored = frappe.get_doc("File", archive.name)
		payload = json.loads(gzip.decompress(stored.get_content(encodings=[])))
		self.assertEqual(payload["source_doctype"], "Vehicle Master")
		self.assertEqual([row["vin"] for row in payload["vehicles"]], [row.vin for row in before])
		self.assertEqual(len(payload["technical_specifications"]), len(children_before))
		for original, saved in zip(before, payload["vehicles"]):
			for field in ("brand", "model", "model_year"):
				if field in payload["fields"]:
					self.assertEqual(saved[field], original[field])
		second = migration._archive_legacy_specifications(["brand", "model", "model_year"])
		self.assertEqual(second.name, archive.name)
		self.assertEqual(frappe.db.sql("select * from `tabVehicle Master` order by name", as_dict=True), before)
		self.assertEqual(frappe.db.sql("select * from `tabVehicle Technical Specification` where parenttype='Vehicle Master' order by parent, idx, name", as_dict=True), children_before)
