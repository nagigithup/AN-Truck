"""Transactional coverage for the portal's ERPNext party adapters."""
from uuid import uuid4
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from an_truck import portal_parties as api


class TestPortalParties(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.user = frappe.session.user
		frappe.set_user("Administrator")
		self.savepoint = "portal_party_test"
		frappe.db.savepoint(self.savepoint)

	def tearDown(self):
		frappe.db.rollback(save_point=self.savepoint)
		frappe.set_user(self.user)
		super().tearDown()

	def data(self, doctype):
		prefix = doctype.lower()
		group = frappe.db.get_value(f"{doctype} Group", {"is_group": 0}, "name")
		data = {f"{prefix}_name": f"Portal test {uuid4().hex[:12]}", f"{prefix}_type": "Company", f"{prefix}_group": group}
		if doctype == "Customer":
			data["territory"] = frappe.db.get_value("Territory", {"is_group": 0}, "name")
		return data

	def test_customer_and_supplier_create_read_update_linked_documents(self):
		for doctype in ("Customer", "Supplier"):
			with self.subTest(doctype=doctype):
				data = self.data(doctype)
				data["contact"] = {"first_name": "Portal Contact", "email_id": "portal-test@example.invalid", "mobile_no": "+971501234567", "phone": "+97141234567"}
				data["address"] = (
					{"country": "United Arab Emirates", "city": "Dubai", "district": "Test District", "street": "Test Street", "building_number": "B1", "additional_number": "A1", "pincode": "00000", "short_address": "TEST0000"}
					if doctype == "Customer"
					else {"country": "United Arab Emirates", "city": "Dubai", "address_line1": "Test Street", "address_line2": "Suite 1", "pincode": "00000"}
				)
				created = api.save_party(doctype, data)
				result = api.get_party(doctype, created["name"])
				self.assertEqual(result["record"]["contact"]["email_id"], data["contact"]["email_id"])
				self.assertEqual(result["record"]["address"]["city"], "Dubai")
				result["record"]["contact"]["phone"] = "+97147654321"
				api.save_party(doctype, result["record"], name=created["name"], modified=result["modified"])
				updated = api.get_party(doctype, created["name"])
				self.assertEqual(updated["record"]["contact"]["phone"], "+97147654321")
				listed = api.list_parties(doctype, search="+97147654321")
				self.assertIn(created["name"], [row.name for row in listed["rows"]])

	def test_customer_commercial_registration_and_national_address_round_trip(self):
		data = self.data("Customer")
		data.update(
			{
				"default_currency": "SAR",
				"tax_id": "310000000000003",
				"commercial_registration_number": "1010123456",
				"address": {
					"country": "Saudi Arabia",
					"city": "Riyadh",
					"district": "Al Olaya",
					"street": "King Fahd Road",
					"building_number": "1234",
					"additional_number": "5678",
					"pincode": "12345",
					"short_address": "ABCD1234",
				},
			}
		)
		created = api.save_party("Customer", data)
		customer = frappe.get_doc("Customer", created["name"])
		self.assertEqual(customer.tax_id, data["tax_id"])
		self.assertEqual(customer.custom_vat_registration_number, data["tax_id"])
		self.assertEqual(
			[(row.type_code, row.value) for row in customer.custom_additional_ids],
			[("CRN", data["commercial_registration_number"])],
		)
		address_name = customer.customer_primary_address
		address = frappe.get_doc("Address", address_name)
		self.assertEqual(address.custom_area, "Al Olaya")
		self.assertEqual(address.address_line1, "King Fahd Road")
		self.assertEqual(address.custom_building_number, "1234")
		self.assertEqual(address.custom_additional_number, "5678")
		self.assertEqual(address.custom_short_address, "ABCD1234")
		self.assertTrue(address.is_primary_address)
		self.assertTrue(
			any(row.link_doctype == "Customer" and row.link_name == customer.name for row in address.links)
		)
		from erpnext.accounts.party import get_party_details

		invoice_party = get_party_details(
			party=customer.name,
			party_type="Customer",
			company=frappe.defaults.get_global_default("company"),
			doctype="Sales Invoice",
		)
		self.assertEqual(invoice_party.customer_address, address_name)
		self.assertEqual(invoice_party.currency, "SAR")

		loaded = api.get_party("Customer", customer.name)
		self.assertEqual(loaded["record"]["commercial_registration_number"], "1010123456")
		self.assertEqual(loaded["record"]["address"], data["address"])
		loaded["record"]["address"]["district"] = "Al Malqa"
		api.save_party(
			"Customer",
			loaded["record"],
			name=customer.name,
			modified=loaded["modified"],
		)
		customer.reload()
		self.assertEqual(customer.customer_primary_address, address_name)
		address.reload()
		self.assertEqual(address.custom_area, "Al Malqa")
		self.assertEqual(
			frappe.db.count(
				"Dynamic Link",
				{"parenttype": "Address", "link_doctype": "Customer", "link_name": customer.name},
			),
			1,
		)

	def test_saudi_address_validation_does_not_apply_to_other_countries(self):
		bad_saudi = self.data("Customer")
		bad_saudi["address"] = {
			"country": "Saudi Arabia",
			"city": "Riyadh",
			"street": "Test",
			"building_number": "12",
		}
		with self.assertRaises(frappe.ValidationError):
			api.save_party("Customer", bad_saudi)

		non_saudi = self.data("Customer")
		non_saudi["address"] = {
			"country": "United Arab Emirates",
			"city": "Dubai",
			"street": "Test",
			"building_number": "12",
		}
		api.save_party("Customer", non_saudi)

	def test_guest_and_missing_role_are_denied(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.AuthenticationError):
			api.list_parties("Customer")
		frappe.set_user("Administrator")
		with patch.object(frappe, "get_roles", return_value=[]):
			with self.assertRaises(frappe.PermissionError):
				api.get_options("Customer")

	def test_failed_address_rolls_back_customer_and_contact_creation(self):
		data = self.data("Customer")
		data["contact"] = {"first_name": data["customer_name"], "email_id": "atomic-test@example.invalid"}
		data["address"] = {"country": "Saudi Arabia", "city": "Riyadh", "street": "Test Street", "building_number": "12"}
		with self.assertRaises(frappe.ValidationError):
			api.save_party("Customer", data)
		self.assertFalse(frappe.db.exists("Customer", {"customer_name": data["customer_name"]}))
		self.assertFalse(frappe.db.exists("Contact", {"first_name": data["customer_name"]}))

	def test_failed_address_rolls_back_customer_edit(self):
		data = self.data("Customer")
		created = api.save_party("Customer", data)
		loaded = api.get_party("Customer", created["name"])
		with self.assertRaises(frappe.ValidationError):
			api.save_party("Customer", {
				"customer_name": "Name must roll back",
				"address": {"country": "Saudi Arabia", "city": "Riyadh", "street": "Test", "pincode": "123"},
			}, name=created["name"], modified=loaded["modified"])
		self.assertEqual(frappe.db.get_value("Customer", created["name"], "customer_name"), data["customer_name"])

	def test_billing_fallback_does_not_overwrite_shipping_address(self):
		data = self.data("Customer")
		created = api.save_party("Customer", data)
		shipping = frappe.get_doc({
			"doctype": "Address", "address_title": data["customer_name"], "address_type": "Shipping",
			"country": "Saudi Arabia", "city": "Jeddah", "address_line1": "Shipping only",
			"links": [{"link_doctype": "Customer", "link_name": created["name"]}],
		}).insert()
		loaded = api.get_party("Customer", created["name"])
		self.assertFalse(loaded["record"]["address"]["street"])
		api.save_party("Customer", {"address": {
			"country": "Saudi Arabia", "city": "Riyadh", "street": "Billing Street",
			"district": "Olaya", "building_number": "1234", "additional_number": "5678",
			"pincode": "12345", "short_address": "ABCD1234",
		}}, name=created["name"], modified=loaded["modified"])
		primary = frappe.db.get_value("Customer", created["name"], "customer_primary_address")
		self.assertNotEqual(primary, shipping.name)
		shipping.reload()
		self.assertEqual(shipping.address_line1, "Shipping only")
		frappe.db.set_value("Customer", created["name"], "customer_primary_address", None)
		loaded = api.get_party("Customer", created["name"])
		self.assertEqual(loaded["record"]["address"]["street"], "Billing Street")
		api.save_party("Customer", {"address": loaded["record"]["address"]}, name=created["name"], modified=loaded["modified"])
		self.assertEqual(frappe.db.get_value("Customer", created["name"], "customer_primary_address"), primary)
		self.assertEqual(frappe.db.count("Dynamic Link", {"parenttype": "Address", "link_doctype": "Customer", "link_name": created["name"]}), 2)

	def test_create_permission_is_enforced(self):
		data = self.data("Customer")
		with patch.object(frappe, "has_permission", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				api.save_party("Customer", data)

	def test_payload_and_filter_allowlists(self):
		with self.assertRaises(frappe.ValidationError):
			api.save_party("User", {})
		with self.assertRaises(frappe.ValidationError):
			api.save_party("Customer", {"owner": "Administrator"})
		with self.assertRaises(frappe.ValidationError):
			api.list_parties("Customer", filters={"owner": "Administrator"})
		with self.assertRaises(frappe.ValidationError):
			api.list_parties("Customer", filters={"disabled": ["!=", 1]})
		with self.assertRaises(frappe.ValidationError):
			api.link_options("Customer", "owner")

	def test_required_and_invalid_links_use_erpnext_validation(self):
		with self.assertRaises(frappe.MandatoryError):
			api.save_party("Customer", {})
		data = self.data("Supplier")
		data["supplier_group"] = "Nonexistent Portal Group"
		with self.assertRaises(frappe.LinkValidationError):
			api.save_party("Supplier", data)

	def test_stale_update_and_exact_identity_duplicate_are_rejected(self):
		data = self.data("Customer")
		data["tax_id"] = uuid4().hex
		created = api.save_party("Customer", data)
		with self.assertRaises(frappe.TimestampMismatchError):
			api.save_party("Customer", data, name=created["name"], modified="2000-01-01")
		with self.assertRaises(frappe.ValidationError):
			api.save_party("Customer", data)

	def test_secondary_contact_channels_are_preserved(self):
		data = self.data("Supplier")
		data["contact"] = {"first_name": "Portal", "email_id": "first@example.invalid"}
		created = api.save_party("Supplier", data)
		party = frappe.get_doc("Supplier", created["name"])
		contact = frappe.get_doc("Contact", party.supplier_primary_contact)
		contact.append("email_ids", {"email_id": "secondary@example.invalid"})
		contact.save()
		result = api.get_party("Supplier", created["name"])
		api.save_party("Supplier", {"contact": {"email_id": "new@example.invalid"}}, name=created["name"], modified=result["modified"])
		contact.reload()
		self.assertEqual({row.email_id for row in contact.email_ids}, {"secondary@example.invalid", "new@example.invalid"})

	def test_shared_contact_cannot_be_changed_from_one_party(self):
		data = self.data("Supplier")
		data["contact"] = {"first_name": "Shared", "email_id": "shared@example.invalid"}
		first = api.save_party("Supplier", data)
		second = api.save_party("Supplier", self.data("Supplier"))
		party = frappe.get_doc("Supplier", first["name"])
		contact = frappe.get_doc("Contact", party.supplier_primary_contact)
		contact.append("links", {"link_doctype": "Supplier", "link_name": second["name"]})
		contact.save()
		result = api.get_party("Supplier", first["name"])
		with self.assertRaises(frappe.ValidationError):
			api.save_party("Supplier", {"contact": {"email_id": "changed@example.invalid"}}, name=first["name"], modified=result["modified"])
		contact.reload()
		self.assertEqual(contact.email_id, "shared@example.invalid")

	def test_real_read_only_role_and_document_user_permissions(self):
		first = api.save_party("Customer", self.data("Customer"))
		second = api.save_party("Customer", self.data("Customer"))
		role = "Portal Test " + uuid4().hex[:8]
		frappe.get_doc({"doctype": "Role", "role_name": role}).insert()
		frappe.get_doc({"doctype": "Custom DocPerm", "parent": "Customer", "role": role, "permlevel": 0, "read": 1, "select": 1}).insert()
		email = f"portal-{uuid4().hex[:8]}@example.invalid"
		frappe.get_doc({"doctype": "User", "email": email, "first_name": "Portal test", "send_welcome_email": 0, "roles": [{"role": role}, {"role": "AN Truck Portal User"}]}).insert()
		frappe.get_doc({"doctype": "User Permission", "user": email, "allow": "Customer", "for_value": first["name"], "apply_to_all_doctypes": 1}).insert()
		frappe.clear_cache(user=email)
		frappe.set_user(email)
		self.assertFalse(api.get_party("Customer", first["name"])["can_write"])
		self.assertEqual([row.name for row in api.list_parties("Customer")["rows"]], [first["name"]])
		with self.assertRaises(frappe.PermissionError):
			api.get_party("Customer", second["name"])
		with self.assertRaises(frappe.PermissionError):
			api.save_party("Customer", {}, name=first["name"])
