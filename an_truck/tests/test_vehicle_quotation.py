"""Focused transactional tests. Fixtures and quotations are rolled back."""
import json
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import frappe
from frappe.tests import IntegrationTestCase

from an_truck import vehicle_quotation as domain
from an_truck.an_truck.doctype.vehicle_specification_template import vehicle_specification_template as templates


class TestVehicleQuotation(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.user = frappe.session.user
		frappe.set_user("Administrator")
		frappe.db.savepoint("quotation_feature")
		self.suffix = uuid4().hex[:10]
		self.vehicle = frappe.get_doc("Vehicle Master", frappe.db.get_value("Vehicle Master", {}, "name"))
		self.customer = frappe.db.get_value("Customer", {"disabled": 0}, "name")
		self.first = self.template("DONGFENG KC 6X4", 350, "KC warranty")
		self.second = self.template("CHENGLONG H7 PRO 460 4X2", 460, "H7 warranty")

	def tearDown(self):
		frappe.db.rollback(save_point="quotation_feature")
		frappe.set_user(self.user)
		super().tearDown()

	def template(self, model, power, warranty, **values):
		doc = frappe.get_doc({"doctype": domain.TEMPLATE, "template_name": model + " " + self.suffix,
			"model": model, "item_code": self.vehicle.item_code, "horsepower_hp": power,
			"quotation_warranty_terms": warranty, **values}).insert()
		templates.publish_template(doc.name)
		return doc.reload()

	def quotation(self, models=None):
		doc = frappe.new_doc("Quotation")
		doc.company = self.vehicle.company
		doc.quotation_to = "Customer"
		doc.party_name = self.customer
		doc.currency = frappe.get_cached_value("Company", doc.company, "default_currency")
		for template in models or [self.first]:
			doc.append("items", {"item_code": self.vehicle.item_code, "qty": 2, "rate": 100,
				domain.LINK: template.name})
		return doc.insert()

	def test_multi_model_no_vin_standard_totals_and_one_format(self):
		doc = self.quotation([self.first, self.second])
		self.assertFalse(any(row.get("custom_vehicle_master") for row in doc.items))
		self.assertEqual(doc.net_total, 400)
		self.assertEqual(doc.grand_total, doc.net_total + doc.total_taxes_and_charges)
		data = domain.quotation_print_data(doc)
		self.assertEqual(len(data["models"]), 2)
		self.assertEqual([m["warranty_terms"] for m in data["models"]], ["KC warranty", "H7 warranty"])
		for row in doc.items:
			self.assertTrue(json.loads(row.get(domain.SNAPSHOT))["revision"])
		html = frappe.get_print("Quotation", doc.name, domain.PRINT_FORMAT)
		self.assertIn("DONGFENG KC 6X4", html)
		self.assertIn("CHENGLONG H7 PRO 460 4X2", html)
		self.assertNotIn("s*.15", html)
		self.assertEqual(frappe.db.count("Print Format", {"name": domain.PRINT_FORMAT}), 1)
		pdf = frappe.get_print("Quotation", doc.name, domain.PRINT_FORMAT, as_pdf=True, pdf_generator="chrome")
		self.assertTrue(pdf.startswith(b"%PDF"))
		Path("/tmp/an-truck-unified-quotation.pdf").write_bytes(pdf)
		Path("/tmp/an-truck-unified-quotation.html").write_text(html)
		from io import BytesIO
		from pypdf import PdfReader
		pages = PdfReader(BytesIO(pdf)).pages
		self.assertGreaterEqual(len(pages), 3)
		self.assertTrue(all(abs(float(page.mediabox.width) - 595.3) < 2 and abs(float(page.mediabox.height) - 841.9) < 2 for page in pages))

	def test_vehicle_inference_keeps_manual_selection_and_identity(self):
		vin = "QUOTATION-VIN-" + self.suffix
		frappe.get_doc({"doctype": "Serial No", "serial_no": vin, "item_code": self.vehicle.item_code, "company": self.vehicle.company}).insert()
		vehicle = frappe.get_doc({"doctype": "Vehicle Master", "vin": vin, "engine_number": "ENGINE-" + self.suffix,
			"item_code": self.vehicle.item_code, "company": self.vehicle.company, "specification_template": self.first.name}).insert()
		row = frappe.new_doc("Quotation Item")
		row.item_code, row.custom_vehicle_master = vehicle.item_code, vehicle.name
		self.assertEqual(domain.resolve_line(row, vehicle.company)["template"], self.first.name)
		row.set(domain.LINK, self.second.name)
		self.assertEqual(domain.resolve_line(row, vehicle.company)["template"], self.second.name)
		vehicle.reload()
		self.assertEqual((vehicle.vin, vehicle.engine_number, vehicle.specification_template), (vin, "ENGINE-" + self.suffix, self.first.name))

	def test_compatible_item_or_model_options(self):
		item_name = frappe.db.get_value("Item", self.vehicle.item_code, "item_name")
		generic = self.template(item_name, 300, "Generic", item_code="")
		other = self.template("Unrelated model", 200, "Other", item_code="")
		options = {row.name for row in domain.template_options(self.vehicle.item_code, self.suffix)}
		self.assertTrue({self.first.name, self.second.name, generic.name}.issubset(options))
		self.assertNotIn(other.name, options)

	def test_managed_assets_and_revision_attachment_links(self):
		import base64
		from frappe.utils.file_manager import save_file
		template = frappe.get_doc({"doctype": domain.TEMPLATE, "template_name": "Asset test " + self.suffix,
			"item_code": self.vehicle.item_code, "model": "Asset model"}).insert()
		file = save_file("quotation-" + self.suffix + ".png", base64.b64decode(
			"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jP1EAAAAASUVORK5CYII="),
			template.doctype, template.name, is_private=1)
		template.main_vehicle_photo = file.file_url
		template.save()
		templates.publish_template(template.name)
		quote = self.quotation([template])
		self.assertEqual(json.loads(quote.items[0].get(domain.SNAPSHOT))["images"]["main_vehicle_photo"], file.file_url)
		with self.assertRaises(frappe.ValidationError):
			templates.protect_published_template_file(file, "on_trash")
		with self.assertRaises(frappe.ValidationError):
			file.delete()
		self.assertTrue(Path(file.get_full_path()).exists(), "Rejected deletion must preserve the bytes")
		revision = templates.create_revision(template.name)
		self.assertTrue(frappe.db.exists("File", {"attached_to_doctype": template.doctype,
			"attached_to_name": revision["name"], "file_url": file.file_url}))
		from an_truck_portal.api.specifications import remove_photo
		draft = frappe.get_doc(template.doctype, revision["name"])
		copy = frappe.db.get_value("File", {"attached_to_doctype": template.doctype,
			"attached_to_name": draft.name, "file_url": file.file_url}, "name")
		remove_photo(draft.name, copy, str(draft.modified))
		self.assertTrue(Path(file.get_full_path()).exists())
		self.assertEqual(frappe.db.get_value(template.doctype, template.name, "main_vehicle_photo"), file.file_url)

	def test_submitted_snapshot_does_not_refresh_and_cannot_be_forged(self):
		doc = self.quotation()
		doc.items[0].set(domain.SNAPSHOT, '{"model_name_en":"FORGED"}')
		doc.save()
		doc.submit()
		sealed = doc.items[0].get(domain.SNAPSHOT)
		revision = frappe.get_doc(domain.TEMPLATE, templates.create_revision(self.first.name)["name"])
		revision.horsepower_hp = 999
		revision.quotation_warranty_terms = "New warranty"
		revision.save()
		templates.publish_template(revision.name)
		self.first.active = 0
		self.first.save()
		doc.reload()
		self.assertEqual(doc.items[0].get(domain.SNAPSHOT), sealed)
		with patch.object(domain, "resolve_line", side_effect=AssertionError("Submitted printing must not read templates")):
			self.assertEqual(domain.quotation_print_data(doc)["models"][0]["warranty_terms"], "KC warranty")
		with self.assertRaises(frappe.ValidationError):
			domain.refresh_specifications(doc.name)
		doc.items[0].set(domain.SNAPSHOT, "{}")
		with self.assertRaises(frappe.ValidationError):
			doc.save()
		with self.assertRaises(frappe.ValidationError):
			doc.cancel()
		doc.reload()
		doc.cancel()
		self.assertEqual(doc.items[0].get(domain.SNAPSHOT), sealed)
		amended = frappe.copy_doc(doc)
		amended.docstatus = 0
		amended.amended_from = doc.name
		amended.items[0].set(domain.LINK, revision.name)
		amended.insert()
		amended.submit()
		self.assertEqual(json.loads(amended.items[0].get(domain.SNAPSHOT))["template"], revision.name)
		self.assertEqual(frappe.db.get_value("Quotation Item", doc.items[0].name, domain.SNAPSHOT), sealed)

	def test_long_technical_specifications_continue_without_clipping(self):
		rows = [{"specification_name": f"Technical specification {i}", "value": "Technical detail " + str(i)} for i in range(90)]
		rows[-1]["value"] = "CONTINUATION-END"
		template = self.template("Continuation model", 460, "Warranty", technical_specifications=rows)
		doc = self.quotation([template])
		from io import BytesIO
		from pypdf import PdfReader
		pdf = frappe.get_print("Quotation", doc.name, domain.PRINT_FORMAT, as_pdf=True, pdf_generator="chrome")
		pages = PdfReader(BytesIO(pdf)).pages
		self.assertGreaterEqual(len(pages), 3)
		self.assertIn("CONTINUATION-END", "\n".join(page.extract_text() for page in pages))

	def test_configurations_keep_complete_specs_and_do_not_change_price(self):
		high = self.template("High Cab", 460, "High warranty", configuration_of=self.second.name, configuration_name="High Cab", cabin_type="High")
		low = self.template("Low Cab", 420, "Low warranty", configuration_of=self.second.name, configuration_name="Low Cab", cabin_type="Low")
		doc = self.quotation([high, low])
		data = domain.quotation_print_data(doc)
		self.assertEqual([row["configuration"] for row in data["models"]], ["High Cab", "Low Cab"])
		self.assertEqual([row.rate for row in doc.items], [100, 100])
		self.assertIn('460', doc.items[0].get(domain.SNAPSHOT))
		self.assertNotIn('420', doc.items[0].get(domain.SNAPSHOT))

	def test_actual_tax_rate_and_portal_draft_edit(self):
		from an_truck_portal.api.sales import create_sales_document, get_sales_form
		doc = self.quotation()
		account = frappe.db.get_value("Account", {"company": doc.company, "account_type": "Tax", "is_group": 0}, "name")
		account = account or frappe.db.get_value("Account", {"company": doc.company, "is_group": 0}, "name")
		if not account:
			self.skipTest("A standard company tax account is required")
		doc.append("taxes", {"charge_type": "On Net Total", "account_head": account, "description": "Test actual tax 7%", "rate": 7})
		doc.items[0].page_break = 1
		doc.save()
		self.assertEqual(frappe.db.get_value("Quotation Item", doc.items[0].name, "page_break"), 1)
		row_name = doc.items[0].name
		self.assertEqual(doc.total_taxes_and_charges, 14)
		self.assertEqual(doc.grand_total, 214)
		form = get_sales_form("Quotation", document=doc.name)
		self.assertEqual(form["items"][0][domain.LINK], self.first.name)
		self.assertIsNone(form["items"][0]["max_qty"])
		form["customer"] = doc.party_name
		form["items"][0]["qty"] = 3
		key = "quotation-test-" + self.suffix
		try:
			result = create_sales_document("Quotation", data=form, document=doc.name, idempotency_key=key)
			self.assertEqual(result["name"], doc.name)
			self.assertEqual(frappe.get_doc("Quotation", doc.name).items[0].qty, 3)
			self.assertEqual(frappe.get_doc("Quotation", doc.name).items[0].name, row_name)
			self.assertEqual(frappe.get_doc("Quotation", doc.name).items[0].page_break, 1)
		finally:
			frappe.cache().delete_value(f"an_truck_portal:sales:Quotation:{frappe.session.user}:{doc.name}:{key}")

	def test_item_company_permission_and_unapproved_template_validation(self):
		row = frappe.new_doc("Quotation Item")
		row.item_code = self.vehicle.item_code
		row.set(domain.LINK, self.first.name)
		with patch.object(frappe, "get_doc", wraps=frappe.get_doc) as getter:
			self.assertTrue(domain.resolve_line(row, self.vehicle.company))
			self.assertTrue(getter.called)
		row.item_code = "WRONG-ITEM"
		with self.assertRaises(frappe.ValidationError):
			domain.resolve_line(row, self.vehicle.company)
		row.item_code = self.vehicle.item_code
		row.custom_vehicle_master = self.vehicle.name
		with self.assertRaises(frappe.ValidationError):
			domain.resolve_line(row, "OTHER-COMPANY")
		quote = self.quotation()
		frappe.set_user("Guest")
		context = domain._commercial_context(quote)
		self.assertEqual((context["company"], context["customer"]), ({}, {}))
		with self.assertRaises(frappe.PermissionError):
			domain.resolve_line(row, self.vehicle.company)

	def test_receipt_without_template_keeps_vin_validation(self):
		from an_truck import services
		if not self.vehicle.purchase_receipt:
			self.skipTest("An existing vehicle receipt is required")
		receipt = frappe.get_doc("Purchase Receipt", self.vehicle.purchase_receipt)
		row = next(row for row in receipt.items if row.name == self.vehicle.purchase_receipt_item)
		receipt.items = [row]
		row.qty = 1
		row.custom_vehicle_specification_template = None
		row.serial_and_batch_bundle = None
		row.serial_no = "QUOTATION-RECEIPT-" + self.suffix
		services.validate_purchase_receipt(receipt)
		frappe.get_doc({"doctype": "Serial No", "serial_no": row.serial_no, "item_code": row.item_code, "company": receipt.company}).insert()
		self.assertTrue(services.create_or_update_vehicle_master(receipt, row, row.serial_no))
		created = frappe.get_doc("Vehicle Master", row.serial_no)
		self.assertFalse(created.specification_template)
		self.assertEqual(created.vin, row.serial_no)
		row.serial_no = ""
		with self.assertRaises(frappe.ValidationError):
			services.validate_purchase_receipt(receipt)
