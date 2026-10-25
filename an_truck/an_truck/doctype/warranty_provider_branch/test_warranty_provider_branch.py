# Copyright (c) 2026, AN and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase


# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = [
	"Warranty Provider",
	"Supplier",
	"Contact",
	"Address",
	"Country",
	"Customer",
	"Warehouse",
]


class IntegrationTestWarrantyProviderBranch(IntegrationTestCase):
	"""
	Integration tests for WarrantyProviderBranch.
	Use this class for testing interactions between multiple components.
	"""

	def setUp(self):
		super().setUp()
		self.provider = frappe.get_doc(
			{
				"doctype": "Warranty Provider",
				"provider_name": f"Branch Code Test {frappe.generate_hash(length=8)}",
				"status": "Active",
				"active": 1,
			}
		).insert()

	def test_branch_code_is_generated_and_immutable(self):
		branch = frappe.get_doc(
			{
				"doctype": "Warranty Provider Branch",
				"warranty_provider": self.provider.name,
				"branch_name": "Main Branch",
				"branch_code": "USER-SUPPLIED",
				"city": "Dubai",
			}
		).insert()

		self.assertRegex(branch.branch_code, r"^WBR-\d{5}$")
		self.assertNotEqual(branch.branch_code, "USER-SUPPLIED")
		original_code = branch.branch_code

		branch.branch_code = "CHANGED"
		branch.branch_name = "Updated Branch"
		branch.save()
		self.assertEqual(branch.branch_code, original_code)
		self.assertEqual(frappe.db.get_value(branch.doctype, branch.name, "branch_code"), original_code)

	def test_generated_branch_codes_are_unique(self):
		codes = set()
		for index in range(3):
			branch = frappe.get_doc(
				{
					"doctype": "Warranty Provider Branch",
					"warranty_provider": self.provider.name,
					"branch_name": f"Branch {index}",
					"city": "Dubai",
				}
			).insert()
			codes.add(branch.branch_code)

		self.assertEqual(len(codes), 3)
