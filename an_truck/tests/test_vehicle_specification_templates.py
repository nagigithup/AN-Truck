"""Transactional tests: all fixtures are rolled back; existing vehicles are read only."""
from uuid import uuid4
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from an_truck.an_truck.doctype.vehicle_specification_template import vehicle_specification_template as api
from an_truck.an_truck.doctype.vehicle_master.vehicle_master import get_specification_values, get_vehicle_specifications


class TestVehicleSpecificationTemplates(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.user = frappe.session.user
		frappe.set_user("Administrator")
		frappe.db.savepoint("vehicle_spec_test")
		self.suffix = uuid4().hex[:12]
		self.base = frappe.db.get_value("Vehicle Master", {}, ["name", "item_code", "company"], as_dict=True)
		if not self.base:
			self.skipTest("An existing vehicle Item and Company are required.")
		self.template = frappe.get_doc({
			"doctype": "Vehicle Specification Template", "template_name": "Spec test " + self.suffix,
			"item_code": self.base.item_code, "model": "Model One", "horsepower_hp": 460,
			"technical_specifications": [{"specification_name": "Package", "value": "Regional"}],
		}).insert()
		api.publish_template(self.template.name)
		self.template.reload()

	def tearDown(self):
		frappe.db.rollback(save_point="vehicle_spec_test")
		frappe.set_user(self.user)
		super().tearDown()

	def vehicle(self, index):
		vin = f"SPEC-{self.suffix}-{index}"
		frappe.get_doc({"doctype": "Serial No", "serial_no": vin, "item_code": self.base.item_code, "company": self.base.company}).insert()
		return frappe.get_doc({"doctype": "Vehicle Master", "vin": vin, "item_code": self.base.item_code,
			"company": self.base.company, "specification_template": self.template.name,
			"engine_number": "ENGINE-" + str(index), "color": "White", "vehicle_status": "Received"}).insert()

	def test_reference_resolution_edit_and_revision_preserve_identity(self):
		first, second = self.vehicle(1), self.vehicle(2)
		self.assertEqual(first.model, "Model One")
		self.assertEqual(get_specification_values(second)["horsepower_hp"], 460)
		self.assertFalse(frappe.db.get_value("Vehicle Master", first.name, "model"))
		first.color = "Blue"
		first.save()
		second.reload()
		self.assertEqual(second.color, "White")
		revision = api.create_revision(self.template.name)
		next_doc = frappe.get_doc("Vehicle Specification Template", revision["name"])
		next_doc.model = "Model Two"
		next_doc.save()
		api.publish_template(next_doc.name)
		first.specification_template = next_doc.name
		first.save()
		self.assertEqual(first.vin, first.name)
		self.assertEqual(first.engine_number, "ENGINE-1")
		self.assertEqual(first.color, "Blue")
		self.assertEqual(first.model, "Model Two")
		self.assertEqual(second.model, "Model One")
		self.assertEqual(get_vehicle_specifications(first.name)["revision"], 2)

	def test_published_revision_immutable_and_linked_vehicles_pagination(self):
		self.vehicle(1)
		self.vehicle(2)
		self.template.model = "Changed"
		with self.assertRaises(frappe.ValidationError):
			self.template.save()
		self.template.reload()
		result = api.get_linked_vehicles(self.template.name, page_length=1, company=self.base.company)
		self.assertEqual(result["total"], 2)
		self.assertEqual(len(result["rows"]), 1)
		self.assertTrue(result["has_more"])
		self.assertEqual(api.get_linked_vehicles(self.template.name, search="ENGINE-2")["total"], 1)
		self.assertEqual(api.get_linked_vehicles(self.template.name, search="White", status="Received")["total"], 2)
		self.assertEqual(api.get_linked_vehicles(self.template.name, status="Sold")["total"], 0)
		with patch.object(frappe, "has_permission", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				api.get_linked_vehicles(self.template.name)

	def test_existing_vehicle_without_template_and_vin_immutability(self):
		name = frappe.db.get_value("Vehicle Master", {"specification_template": ["is", "not set"]}, "name")
		if not name:
			self.skipTest("An existing vehicle without a template is required")
		base = frappe.get_doc("Vehicle Master", name)
		self.assertFalse(base.specification_template)
		self.assertTrue(get_vehicle_specifications(base.name)["legacy"])
		new = self.vehicle(1)
		new.vin = "OTHER-VIN"
		with self.assertRaises(frappe.ValidationError):
			new.save()

	def test_portal_apis_and_vehicle_form(self):
		from an_truck_portal.api import specifications, records
		vehicle = self.vehicle(1)
		listed = specifications.list_templates(search=self.suffix)
		self.assertEqual(listed["rows"][0].name, self.template.name)
		form = records.get_vehicle_form(vehicle.name)
		self.assertEqual(form["specifications"]["template"], self.template.name)
		self.assertEqual(specifications.get_template(self.template.name)["linked_count"], 1)
		self.assertEqual(specifications.get_linked_vehicles(self.template.name)["total"], 1)
		self.assertEqual(records.list_records("Vehicle Master", search=vehicle.vin)["rows"][0].model, "Model One")
		self.assertIn(self.template.name, specifications.template_options(item_code=self.base.item_code))
		self.assertIn(self.template.name, [r.name for r in specifications.list_templates(item_code=self.base.item_code)["rows"]])
		updated = records.update_vehicle(vehicle.name, {"color": "Green"})
		self.assertEqual(updated["vin"], vehicle.vin)
		self.assertEqual(frappe.db.get_value("Vehicle Master", vehicle.name, "color"), "Green")

	def test_sales_receipt_and_print_read_layer(self):
		from an_truck_portal.api.sales import _prepare_sales_rows, _sales_vehicle_options
		vehicle = self.vehicle(1)
		rows = _prepare_sales_rows("Quotation", self.base.company, [
			{"vehicle_master": vehicle.name, "qty": 1, "rate": 100}
		])
		self.assertEqual(rows[0].vin, vehicle.vin)
		self.assertIn("Model One", rows[0].description)
		options = _sales_vehicle_options("Quotation", self.base.company)
		self.assertTrue(any(row["name"] == vehicle.name for row in options))
		self.assertEqual(frappe.render_template("{{ doc.model }} / {{ doc.vin }}", {"doc": vehicle}), f"Model One / {vehicle.vin}")
		# Exercise receipt -> Vehicle Master creation using read-only source documents.
		base_doc = frappe.get_doc("Vehicle Master", self.base.name)
		if base_doc.purchase_receipt and base_doc.purchase_receipt_item:
			from an_truck.services import create_or_update_vehicle_master
			receipt = frappe.get_doc("Purchase Receipt", base_doc.purchase_receipt)
			row = next(row for row in receipt.items if row.name == base_doc.purchase_receipt_item)
			row.custom_vehicle_specification_template = self.template.name
			vin = f"SPEC-RECEIPT-{self.suffix}"
			frappe.get_doc({"doctype": "Serial No", "serial_no": vin, "item_code": row.item_code, "company": receipt.company}).insert()
			self.assertTrue(create_or_update_vehicle_master(receipt, row, vin))
			created = frappe.get_doc("Vehicle Master", vin)
			self.assertEqual(created.specification_template, self.template.name)
			self.assertEqual(created.purchase_receipt, receipt.name)
			self.assertEqual(created.model, "Model One")
			self.assertFalse(frappe.db.get_value("Vehicle Master", vin, "model"))

	def test_optional_template_and_published_child_immutability(self):
		vin = f"SPEC-EMPTY-{self.suffix}"
		frappe.get_doc({"doctype": "Serial No", "serial_no": vin, "item_code": self.base.item_code, "company": self.base.company}).insert()
		vehicle = frappe.get_doc({"doctype": "Vehicle Master", "vin": vin, "item_code": self.base.item_code, "company": self.base.company}).insert()
		self.assertEqual(vehicle.vin, vin)
		self.assertFalse(vehicle.specification_template)
		self.template.technical_specifications[0].value = "Edited"
		with self.assertRaises(frappe.ValidationError):
			self.template.save()
		file = frappe.get_doc({"doctype": "File", "file_name": "spec.pdf", "file_url": "/private/files/spec.pdf",
			"attached_to_doctype": "Vehicle Specification Template", "attached_to_name": self.template.name})
		with self.assertRaises(frappe.ValidationError):
			api.protect_published_template_file(file, "validate")

	def test_reader_permissions_and_vehicle_user_permission_filter_count(self):
		first, second = self.vehicle(1), self.vehicle(2)
		other_company = frappe.db.get_value("Company", {"name": ["!=", self.base.company]}, "name")
		email = f"spec-{self.suffix}@example.invalid"
		frappe.get_doc({"doctype": "User", "email": email, "first_name": "Specification reader",
			"send_welcome_email": 0, "roles": [{"role": "AN Truck Viewer"}, {"role": "AN Truck Portal User"}]}).insert()
		frappe.get_doc({"doctype": "User Permission", "user": email, "allow": "Vehicle Master",
			"for_value": first.name, "apply_to_all_doctypes": 1}).insert()
		frappe.get_doc({"doctype": "User Permission", "user": email, "allow": "Company",
			"for_value": self.base.company, "apply_to_all_doctypes": 1}).insert()
		frappe.clear_cache(user=email)
		frappe.set_user(email)
		result = api.get_linked_vehicles(self.template.name)
		self.assertEqual(result["total"], 1)
		self.assertEqual([row.name for row in result["rows"]], [first.name])
		from an_truck_portal.api import records, specifications
		with self.assertRaises(frappe.PermissionError):
			records.get_vehicle_form(second.name)
		with self.assertRaises(frappe.PermissionError):
			specifications.save_template({"template_name": "Unauthorized"})
		with self.assertRaises(frappe.PermissionError):
			api.create_revision(self.template.name)
		if other_company:
			with self.assertRaises(frappe.PermissionError):
				api.get_linked_vehicles(self.template.name, company=other_company)
