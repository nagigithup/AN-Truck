"""Supplier reference data stays current and follows normal Frappe permissions."""

from uuid import uuid4
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from an_truck.portal_lookups import get_supplier_form_options


class TestSupplierFormOptions(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.user = frappe.session.user
		frappe.set_user("Administrator")
		frappe.db.savepoint("supplier_lookup_test")

	def tearDown(self):
		frappe.db.rollback(save_point="supplier_lookup_test")
		frappe.set_user(self.user)
		super().tearDown()

	def make_group(self, is_group=0):
		return frappe.get_doc({
			"doctype": "Supplier Group",
			"supplier_group_name": "Portal Lookup " + uuid4().hex[:12],
			"is_group": is_group,
			"parent_supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 1}),
		}).insert()

	def test_three_fixed_master_sets_without_default_twenty_row_limit(self):
		result = get_supplier_form_options()
		self.assertEqual(set(result), {"supplier_groups", "countries", "currencies"})
		for rows in result.values():
			self.assertTrue(all(set(row) == {"value", "label"} for row in rows))
			self.assertTrue(all(row["value"] == row["label"] for row in rows))
		self.assertEqual(
			{row["value"] for row in result["countries"]},
			set(frappe.get_list("Country", pluck="name", limit=0)),
		)
		with self.assertRaises(TypeError):
			get_supplier_form_options(doctype="User")

	def test_new_group_appears_on_next_request_and_parent_groups_are_excluded(self):
		before = get_supplier_form_options()
		leaf, parent = self.make_group(), self.make_group(is_group=1)
		after = get_supplier_form_options()
		self.assertNotIn(leaf.name, {row["value"] for row in before["supplier_groups"]})
		self.assertIn(leaf.name, {row["value"] for row in after["supplier_groups"]})
		self.assertNotIn(parent.name, {row["value"] for row in after["supplier_groups"]})

	def test_disabled_currency_is_excluded_and_reenabled_currency_appears(self):
		currency = frappe.db.get_value("Currency", {"enabled": 1})
		self.assertTrue(currency)
		frappe.db.set_value("Currency", currency, "enabled", 0)
		self.assertNotIn(currency, {row["value"] for row in get_supplier_form_options()["currencies"]})
		frappe.db.set_value("Currency", currency, "enabled", 1)
		self.assertIn(currency, {row["value"] for row in get_supplier_form_options()["currencies"]})

	def test_guest_portal_role_and_supplier_permissions_are_enforced(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.AuthenticationError):
			get_supplier_form_options()
		frappe.set_user("Administrator")
		with patch.object(frappe, "get_roles", return_value=[]):
			with self.assertRaises(frappe.PermissionError):
				get_supplier_form_options()
		with patch.object(frappe, "has_permission", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				get_supplier_form_options()

	def test_supplier_group_user_permissions_filter_options(self):
		allowed, other = self.make_group(), self.make_group()
		email = "lookup-" + uuid4().hex[:10] + "@example.invalid"
		frappe.get_doc({
			"doctype": "User", "email": email, "first_name": "Lookup test",
			"send_welcome_email": 0,
			"roles": [{"role": "AN Truck Portal User"}, {"role": "Purchase User"}],
		}).insert()
		frappe.get_doc({
			"doctype": "User Permission", "user": email, "allow": "Supplier Group",
			"for_value": allowed.name, "apply_to_all_doctypes": 1,
		}).insert()
		frappe.clear_cache(user=email)
		frappe.set_user(email)
		values = {row["value"] for row in get_supplier_form_options()["supplier_groups"]}
		self.assertIn(allowed.name, values)
		self.assertNotIn(other.name, values)
