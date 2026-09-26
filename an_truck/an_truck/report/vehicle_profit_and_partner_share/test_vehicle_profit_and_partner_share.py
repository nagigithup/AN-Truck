import unittest
from unittest.mock import patch

import frappe

from an_truck.an_truck.report.vehicle_profit_and_partner_share.vehicle_profit_and_partner_share import (
	_distribution_totals,
	_validate_distribution_rows,
	calculate_partner_shares,
	mark_profit_distributed,
)


def vehicle_row(name="VIN-1", **overrides):
	values = {
		"name": name,
		"vin": name,
		"vehicle_status": "Sold",
		"sales_invoice": "SINV-1",
		"sales_invoice_docstatus": 1,
		"selling_rate": 100000,
		"final_valuation_rate": 45000,
		"profit_distributed": 0,
	}
	values.update(overrides)
	return frappe._dict(values)


class TestVehicleProfitCalculation(unittest.TestCase):
	def test_profit_partner_split(self):
		self.assertEqual(calculate_partner_shares(45000, 100000), (55000, 26950, 28050))

	def test_loss_partner_split(self):
		self.assertEqual(calculate_partner_shares(45000, 40000), (-5000, -2450, -2550))

	def test_batch_totals_reconcile_from_each_vehicle(self):
		rows = [vehicle_row(), vehicle_row("VIN-2", selling_rate=40000)]
		self.assertEqual(_distribution_totals(rows), (50000, 24500, 25500))


class TestProfitDistributionValidation(unittest.TestCase):
	def test_already_distributed_vehicle_is_rejected(self):
		row = vehicle_row(profit_distributed=1)
		with self.assertRaises(frappe.ValidationError):
			_validate_distribution_rows([row.name], [row])

	def test_unsold_vehicle_is_rejected(self):
		row = vehicle_row(vehicle_status="Received", sales_invoice=None, sales_invoice_docstatus=None)
		with self.assertRaises(frappe.ValidationError):
			_validate_distribution_rows([row.name], [row])

	def test_delivered_vehicle_with_submitted_invoice_is_eligible(self):
		row = vehicle_row(vehicle_status="Delivered")
		_validate_distribution_rows([row.name], [row])

	def test_multiple_valid_vehicles_are_processed_with_audit_fields(self):
		rows = [vehicle_row(), vehicle_row("VIN-2", selling_rate=40000)]
		with (
			patch(
				"an_truck.an_truck.report.vehicle_profit_and_partner_share.vehicle_profit_and_partner_share.frappe.only_for"
			),
			patch(
				"an_truck.an_truck.report.vehicle_profit_and_partner_share.vehicle_profit_and_partner_share._get_distribution_rows",
				return_value=rows,
			),
			patch(
				"an_truck.an_truck.report.vehicle_profit_and_partner_share.vehicle_profit_and_partner_share.frappe.has_permission",
				return_value=True,
			),
			patch(
				"an_truck.an_truck.report.vehicle_profit_and_partner_share.vehicle_profit_and_partner_share.frappe.get_precision",
				return_value=2,
			),
			patch(
				"an_truck.an_truck.report.vehicle_profit_and_partner_share.vehicle_profit_and_partner_share.frappe.db.set_value"
			) as set_value,
		):
			result = mark_profit_distributed(["VIN-1", "VIN-2"])

		self.assertEqual(result["count"], 2)
		self.assertEqual(result["profit_loss"], 50000)
		self.assertEqual(set_value.call_count, 2)
		for call in set_value.call_args_list:
			updates = call.args[2]
			self.assertEqual(updates["profit_distributed"], 1)
			self.assertIsNotNone(updates["profit_distributed_on"])
			self.assertEqual(updates["profit_distributed_by"], frappe.session.user)

	def test_invalid_vehicle_prevents_entire_batch_update(self):
		rows = [vehicle_row(), vehicle_row("VIN-2", vehicle_status="Received", sales_invoice_docstatus=None)]
		with (
			patch(
				"an_truck.an_truck.report.vehicle_profit_and_partner_share.vehicle_profit_and_partner_share.frappe.only_for"
			),
			patch(
				"an_truck.an_truck.report.vehicle_profit_and_partner_share.vehicle_profit_and_partner_share._get_distribution_rows",
				return_value=rows,
			),
			patch(
				"an_truck.an_truck.report.vehicle_profit_and_partner_share.vehicle_profit_and_partner_share.frappe.has_permission",
				return_value=True,
			),
			patch(
				"an_truck.an_truck.report.vehicle_profit_and_partner_share.vehicle_profit_and_partner_share.frappe.db.set_value"
			) as set_value,
		):
			with self.assertRaises(frappe.ValidationError):
				mark_profit_distributed(["VIN-1", "VIN-2"])

		set_value.assert_not_called()

	def test_unauthorized_user_cannot_process_distribution(self):
		with (
			patch(
				"an_truck.an_truck.report.vehicle_profit_and_partner_share.vehicle_profit_and_partner_share.frappe.only_for",
				side_effect=frappe.PermissionError,
			),
			patch(
				"an_truck.an_truck.report.vehicle_profit_and_partner_share.vehicle_profit_and_partner_share._get_distribution_rows"
			) as get_rows,
		):
			with self.assertRaises(frappe.PermissionError):
				mark_profit_distributed(["VIN-1"])

		get_rows.assert_not_called()


if __name__ == "__main__":
	unittest.main()
