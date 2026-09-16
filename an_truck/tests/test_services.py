import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from an_truck import services


class MockDoc(SimpleNamespace):
	def get(self, key, default=None):
		return getattr(self, key, default)

	def set(self, key, value):
		setattr(self, key, value)


class TestServices(unittest.TestCase):
	def test_get_serials_for_row_deduplicates_bundle_and_legacy_serials(self):
		row = frappe._dict(serial_and_batch_bundle="SABB-1", serial_no="VIN-002\nVIN-003")

		with patch("an_truck.services.frappe.get_all", return_value=["VIN-001", "VIN-002"]):
			self.assertEqual(services.get_serials_for_row(row), ["VIN-001", "VIN-002", "VIN-003"])

	def test_purchase_receipt_import_file_infers_from_purchase_order(self):
		doc = MockDoc(
			custom_vehicle_import_file=None,
			items=[frappe._dict(purchase_order="PO-1"), frappe._dict(purchase_order="PO-1")],
		)

		with patch("an_truck.services.frappe.db.get_value", return_value="VIF-1"):
			services.set_purchase_receipt_import_file(doc)

		self.assertEqual(doc.custom_vehicle_import_file, "VIF-1")

	def test_purchase_receipt_blocks_multiple_import_files(self):
		doc = MockDoc(
			custom_vehicle_import_file=None,
			items=[frappe._dict(purchase_order="PO-1"), frappe._dict(purchase_order="PO-2")],
		)

		with patch("an_truck.services.frappe.db.get_value", side_effect=["VIF-1", "VIF-2"]):
			with self.assertRaises(frappe.ValidationError):
				services.set_purchase_receipt_import_file(doc)
