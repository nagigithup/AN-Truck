# Copyright (c) 2026, AN and Contributors
# See license.txt

import unittest
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from an_truck.an_truck.doctype.vehicle_master.vehicle_master import (
	VehicleMaster,
	get_landed_cost_added,
	get_purchase_rate,
)

# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]



class IntegrationTestVehicleMaster(IntegrationTestCase):
	"""
	Integration tests for VehicleMaster.
	Use this class for testing interactions between multiple components.
	"""

	pass


class TestVehicleMasterCostCalculation(unittest.TestCase):
	def test_landed_cost_added_is_split_per_purchase_receipt_stock_qty(self):
		def get_value(doctype, name, fieldname, as_dict=False):
			self.assertEqual(doctype, "Purchase Receipt Item")
			self.assertEqual(name, "PRI-1")
			self.assertEqual(fieldname, ["landed_cost_voucher_amount", "stock_qty", "qty"])
			self.assertTrue(as_dict)
			return frappe._dict(landed_cost_voucher_amount=10000, stock_qty=3, qty=3)

		with (
			patch("an_truck.an_truck.doctype.vehicle_master.vehicle_master.frappe.get_all", return_value=["LCV-1"]),
			patch("an_truck.an_truck.doctype.vehicle_master.vehicle_master.frappe.db.has_column", return_value=True),
			patch("an_truck.an_truck.doctype.vehicle_master.vehicle_master.frappe.db.get_value", side_effect=get_value),
			):
				self.assertAlmostEqual(get_landed_cost_added("PR-1", "PRI-1"), 3333.3333333333335)

	def test_final_valuation_rate_adds_landed_cost_to_purchase_rate(self):
		vm = VehicleMaster(
			{
				"doctype": "Vehicle Master",
				"company": None,
				"purchase_receipt": "PR-1",
				"purchase_receipt_item": "PRI-1",
				"purchase_valuation_rate": 0,
			}
		)

		def get_value(doctype, name, fieldname, as_dict=False):
			if fieldname == ["base_net_rate", "base_rate", "valuation_rate"]:
				return frappe._dict(base_net_rate=32500, base_rate=32500, valuation_rate=35833.333333333)
			return frappe._dict(landed_cost_voucher_amount=10000, stock_qty=3, qty=3)

		with (
			patch("an_truck.an_truck.doctype.vehicle_master.vehicle_master.frappe.get_all", return_value=["LCV-1"]),
			patch("an_truck.an_truck.doctype.vehicle_master.vehicle_master.frappe.db.has_column", return_value=True),
			patch("an_truck.an_truck.doctype.vehicle_master.vehicle_master.frappe.db.get_value", side_effect=get_value),
		):
			vm.refresh_costs()

		self.assertAlmostEqual(vm.purchase_valuation_rate, 32500)
		self.assertAlmostEqual(vm.landed_cost_added, 3333.3333333333335)
		self.assertAlmostEqual(vm.final_valuation_rate, 35833.333333333)

	def test_purchase_rate_excludes_landed_cost(self):
		with patch(
			"an_truck.an_truck.doctype.vehicle_master.vehicle_master.frappe.db.get_value",
			return_value=frappe._dict(base_net_rate=35000, base_rate=35000, valuation_rate=45000),
		):
			self.assertEqual(get_purchase_rate("PRI-1"), 35000)
