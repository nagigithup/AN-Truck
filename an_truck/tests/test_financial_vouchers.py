"""Real ERPNext posting tests on dev.localhost; every fixture/write is rolled back."""
import hashlib
import json
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import nowdate

from an_truck import financial_vouchers as domain


class TestFinancialVouchers(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.user = frappe.session.user
		frappe.set_user("Administrator")
		frappe.db.savepoint("financial_vouchers")
		self.suffix = uuid4().hex[:10]
		self.company = domain.company()
		self.existing = self.fingerprint()
		source = frappe.db.get_value("Customer", {}, ["customer_group", "territory"], as_dict=True)
		self.customer = frappe.get_doc({"doctype": "Customer", "customer_name": "Voucher test customer " + self.suffix,
			"customer_type": "Company", "customer_group": source.customer_group, "territory": source.territory}).insert()
		self.supplier = frappe.get_doc({"doctype": "Supplier", "supplier_name": "Voucher test supplier " + self.suffix,
			"supplier_type": "Company", "supplier_group": frappe.db.get_value("Supplier", {}, "supplier_group")}).insert()
		cash = frappe.get_cached_value("Company", self.company, "default_cash_account")
		self.cash = frappe.get_doc({"doctype": "Account", "account_name": "Voucher test cash " + self.suffix,
			"company": self.company, "parent_account": frappe.db.get_value("Account", cash, "parent_account"),
			"account_type": "Cash", "account_currency": "SAR", "is_group": 0}).insert()
		self.mode = "Cash"

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="financial_vouchers")
		self.assertEqual(self.fingerprint(), self.existing, "Existing financial documents must not change")
		frappe.set_user(self.user)
		super().tearDown()

	def fingerprint(self):
		rows = frappe.get_all("Payment Entry", filters={"company": self.company}, fields=["name", "docstatus", "paid_amount", "received_amount", "modified"], order_by="name")
		ledger = frappe.get_all("GL Entry", filters={"company": self.company}, fields=["name", "voucher_type", "voucher_no", "account", "debit", "credit", "is_cancelled"], order_by="name")
		return hashlib.sha256(frappe.as_json({"payments": rows, "ledger": ledger}).encode()).hexdigest()

	def data(self, direction="Receive", **values):
		return {"company": self.company, "payment_type": direction,
			"party_type": "Customer" if direction == "Receive" else "Supplier",
			"party": self.customer.name if direction == "Receive" else self.supplier.name,
			"posting_date": nowdate(), "amount": 125.5, "account": self.cash.name,
			"mode_of_payment": self.mode, "remarks": "Voucher integration test " + self.suffix, "references": [], **values}

	def create(self, direction="Receive", **values):
		result = domain.save(self.data(direction, **values), request_key=uuid4().hex)
		return frappe.get_doc("Payment Entry", result["document"]["name"])

	def test_four_language_direction_combinations_post_and_print(self):
		from io import BytesIO
		from pypdf import PdfReader
		artifact = Path("/tmp/an-truck-vouchers")
		artifact.mkdir(exist_ok=True)
		for lang in ("ar", "en"):
			for direction in ("Receive", "Pay"):
				with self.subTest(language=lang, direction=direction):
					doc = self.create(direction)
					self.assertEqual(doc.docstatus, 0)
					self.assertFalse(frappe.db.exists("GL Entry", {"voucher_type": "Payment Entry", "voucher_no": doc.name}))
					posted = domain.act(doc.name, "submit")
					self.assertEqual(posted["document"]["docstatus"], 1)
					entries = frappe.get_all("GL Entry", filters={"voucher_type": "Payment Entry", "voucher_no": doc.name, "is_cancelled": 0}, fields=["debit", "credit"])
					self.assertTrue(entries)
					self.assertAlmostEqual(sum(row.debit-row.credit for row in entries), 0, places=2)
					count = len(entries)
					domain.act(doc.name, "submit")
					self.assertEqual(frappe.db.count("GL Entry", {"voucher_type": "Payment Entry", "voucher_no": doc.name, "is_cancelled": 0}), count)
					doc.reload()
					before = doc.as_json()
					with domain.print_language(lang):
						html = frappe.get_print("Payment Entry", doc.name, domain.FORMAT, no_letterhead=1)
						pdf = frappe.get_print("Payment Entry", doc.name, domain.FORMAT, as_pdf=True, no_letterhead=1, pdf_generator="chrome")
						words = domain.voucher_print_data(doc)["words"]
					if lang == "ar":
						self.assertIn("سند قبض" if direction == "Receive" else "سند صرف", html)
						self.assertNotIn("RECEIPT VOUCHER", html)
						self.assertIn("ريال سعودي", words)
						self.assertIn("هللة", words)
					else:
						self.assertIn("RECEIPT VOUCHER" if direction == "Receive" else "PAYMENT VOUCHER", html)
						self.assertNotIn("سند قبض", html)
						self.assertIn("Fifty", words)
					self.assertEqual(len(PdfReader(BytesIO(pdf)).pages), 1)
					stem = f"{lang}-{direction.lower()}"
					(artifact / (stem + ".pdf")).write_bytes(pdf)
					(artifact / (stem + ".html")).write_text(html)
					self.assertEqual(frappe.get_doc("Payment Entry", doc.name).as_json(), before)

	def test_persistent_create_idempotency_and_draft_update(self):
		key = uuid4().hex
		data = self.data()
		first = domain.save(data, request_key=key)
		second = domain.save(data, request_key=key)
		self.assertEqual(first["document"]["name"], second["document"]["name"])
		with self.assertRaises(frappe.ValidationError):
			domain.save({**data, "amount": 999}, request_key=key)
		updated = domain.save({**data, "amount": 200}, name=first["document"]["name"], modified=str(first["document"]["modified"]))
		self.assertEqual(updated["document"]["paid_amount"], 200)
		with self.assertRaises(frappe.TimestampMismatchError):
			domain.save(data, name=first["document"]["name"], modified=str(first["document"]["modified"]))
		self.assertEqual(frappe.db.count("GL Entry", {"voucher_type": "Payment Entry", "voucher_no": first["document"]["name"]}), 0)

	def test_company_account_and_party_security(self):
		doc = self.create()
		other = frappe.db.get_value("Company", {"name": ["!=", self.company]}, "name")
		with self.assertRaises(frappe.PermissionError):
			domain.company(other)
		foreign = frappe.db.get_value("Account", {"company": other, "is_group": 0, "account_type": "Cash"}, "name")
		if foreign:
			with self.assertRaises(frappe.ValidationError):
				domain.save(self.data(account=foreign), request_key=uuid4().hex)
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			domain.record(doc.name)
		from an_truck_portal.api.vouchers import save_voucher
		with self.assertRaises(frappe.AuthenticationError):
			save_voucher(self.data(), request_key=uuid4().hex)

	def test_validation_and_cancellation(self):
		for amount in (0, -1, "NaN", "Infinity"):
			with self.subTest(amount=amount), self.assertRaises(frappe.ValidationError):
				domain.save(self.data(amount=amount), request_key=uuid4().hex)
		doc = self.create()
		domain.act(doc.name, "submit")
		with self.assertRaises(frappe.ValidationError):
			domain.save(self.data(), name=doc.name, modified=str(doc.modified))
		domain.act(doc.name, "cancel")
		self.assertEqual(frappe.db.get_value("Payment Entry", doc.name, "docstatus"), 2)
		domain.act(doc.name, "cancel")
		self.assertEqual(frappe.db.get_value("Payment Entry", doc.name, "docstatus"), 2)

	def test_search_pagination_and_default_language(self):
		for index in range(3):
			self.create(reference_no="voucher-search-" + self.suffix)
		result = domain.list_vouchers(search="voucher-search-" + self.suffix, page_length=2)
		self.assertEqual(result["counts"]["total"], 3)
		self.assertTrue(result["has_more"])
		self.assertEqual(len(domain.list_vouchers(search="voucher-search-" + self.suffix, page=2, page_length=2)["rows"]), 1)
		self.assertEqual(domain.language("fr"), "ar")
		self.assertEqual(domain.language(""), "ar")

	def invoice(self, direction="Receive"):
		item_name = "Voucher test service " + self.suffix
		if not frappe.db.exists("Item", item_name):
			frappe.get_doc({"doctype": "Item", "item_code": item_name, "item_name": item_name,
				"item_group": "All Item Groups", "stock_uom": "Nos", "is_stock_item": 0}).insert()
		co = frappe.get_doc("Company", self.company)
		doc = frappe.new_doc("Sales Invoice" if direction == "Receive" else "Purchase Invoice")
		doc.company = self.company
		doc.posting_date = nowdate()
		doc.set_posting_time = 1
		doc.currency = "SAR"
		if direction == "Receive":
			doc.customer = self.customer.name
			doc.debit_to = co.default_receivable_account
			doc.taxes_and_charges = frappe.db.get_value("Sales Taxes and Charges Template", {"company": self.company, "is_default": 1, "disabled": 0}, "name")
			if doc.taxes_and_charges:
				doc.set_taxes()
		else:
			doc.supplier = self.supplier.name
			doc.credit_to = co.default_payable_account
			doc.bill_no = "VOUCHER-" + uuid4().hex
			doc.bill_date = nowdate()
		doc.append("items", {"item_code": item_name, "qty": 1, "rate": 100,
			"income_account": co.default_income_account, "expense_account": co.default_expense_account, "cost_center": co.cost_center})
		doc.insert()
		doc.submit()
		return doc

	def test_multiple_invoice_allocations_overallocation_and_restoration(self):
		for direction in ("Receive", "Pay"):
			with self.subTest(direction=direction):
				first, second = self.invoice(direction), self.invoice(direction)
				amount = first.outstanding_amount / 4
				rows = [{"reference_doctype": doc.doctype, "reference_name": doc.name, "allocated_amount": amount} for doc in (first, second)]
				payload = self.data(direction, amount=amount*2, references=rows)
				draft = domain.save(payload, request_key=uuid4().hex)
				first.reload()
				self.assertEqual(first.outstanding_amount, first.grand_total)
				out = domain.outstanding(payload["party_type"], payload["party"], direction)
				self.assertTrue(any(row["voucher_no"] == first.name for row in out["rows"]))
				domain.act(draft["document"]["name"], "submit")
				first.reload()
				self.assertAlmostEqual(first.outstanding_amount, first.grand_total-amount, places=2)
				with self.assertRaises(frappe.ValidationError):
					domain.save(self.data(direction, amount=99999, references=[{**rows[0], "allocated_amount": 99999}]), request_key=uuid4().hex)
				with self.assertRaises(frappe.ValidationError):
					domain.save(self.data(direction, references=[rows[0], rows[0]]), request_key=uuid4().hex)
				domain.act(draft["document"]["name"], "cancel")
				first.reload()
				self.assertAlmostEqual(first.outstanding_amount, first.grand_total, places=2)

	def test_bank_reference_methods_and_foreign_currency_words(self):
		from frappe.utils import add_days
		co = frappe.get_doc("Company", self.company)
		bank = frappe.get_doc({"doctype": "Account", "account_name": "Voucher test USD " + self.suffix,
			"company": self.company, "parent_account": frappe.db.get_value("Account", co.default_bank_account, "parent_account"),
			"account_type": "Bank", "account_currency": "USD", "is_group": 0}).insert()
		date = add_days(nowdate(), 1)
		if not frappe.db.exists("Currency Exchange", {"date": date, "from_currency": "USD", "to_currency": "SAR"}):
			frappe.get_doc({"doctype": "Currency Exchange", "date": date, "from_currency": "USD", "to_currency": "SAR", "exchange_rate": 3.75, "for_buying": 1, "for_selling": 1}).insert()
		for mode_name in ("Wire Transfer", "Cheque"):
			mode = frappe.get_doc("Mode of Payment", mode_name)
			if not any(row.company == self.company for row in mode.accounts):
				mode.append("accounts", {"company": self.company, "default_account": bank.name})
				mode.save()
			with self.assertRaises(frappe.ValidationError):
				domain.save(self.data(account=bank.name, mode_of_payment=mode_name, posting_date=date), request_key=uuid4().hex)
			doc = self.create(account=bank.name, mode_of_payment=mode_name, posting_date=date, reference_no="REF-" + self.suffix, reference_date=date)
			self.assertEqual(doc.paid_to_account_currency, "USD")
			self.assertGreater(doc.paid_amount, doc.received_amount)
			domain.act(doc.name, "submit")
			with domain.print_language("ar"):
				data = domain.voucher_print_data(doc)
				self.assertIn("دولار أمريكي", data["words"])
				self.assertNotIn("ريال سعودي", data["words"])
				self.assertEqual(data["amount"], doc.received_amount)

	def test_workflow_dispatch_and_forbidden_direct_submit(self):
		doc = self.create()
		with patch("frappe.model.workflow.get_workflow_name", return_value="Approval"), \
			patch("frappe.model.workflow.get_transitions", return_value=[frappe._dict(action="Request Approval")]), \
			patch("frappe.model.workflow.get_workflow_state_field", return_value="workflow_state"), \
			patch("frappe.model.workflow.apply_workflow", return_value=doc) as apply:
			with self.assertRaises(frappe.PermissionError):
				domain.act(doc.name, "submit")
			domain.act(doc.name, "Request Approval")
			apply.assert_called_once()
		self.assertFalse(frappe.db.exists("GL Entry", {"voucher_type": "Payment Entry", "voucher_no": doc.name}))

	def test_real_role_restrictions_and_cross_company_ids(self):
		doc = self.create()
		domain.act(doc.name, "submit")
		email = "voucher-cashier-" + self.suffix + "@example.invalid"
		frappe.get_doc({"doctype": "User", "email": email, "first_name": "Voucher test cashier", "send_welcome_email": 0,
			"roles": [{"role": "POSNext Cashier"}, {"role": "AN Truck Portal User"}]}).insert()
		frappe.clear_cache(user=email)
		frappe.set_user(email)
		with self.assertRaises(frappe.PermissionError):
			domain.act(doc.name, "cancel")
		with self.assertRaises(frappe.PermissionError):
			domain.record(doc.name, "print")
		frappe.set_user("Administrator")
		other = frappe.db.get_value("Payment Entry", {"company": ["!=", self.company]}, "name")
		if other:
			with self.assertRaises(frappe.PermissionError):
				domain.record(other)

	def test_viewer_creator_and_existing_approver_profiles(self):
		from an_truck.voucher_permissions import VIEWER, CREATOR
		doc = self.create()
		for role in (VIEWER, CREATOR):
			email = "voucher-role-" + role.split()[-1].lower() + self.suffix + "@example.invalid"
			frappe.get_doc({"doctype": "User", "email": email, "first_name": "Voucher test role", "send_welcome_email": 0,
				"roles": [{"role": role}, {"role": "AN Truck Portal User"}]}).insert()
			frappe.clear_cache(user=email)
			frappe.set_user(email)
			self.assertEqual(domain.record(doc.name, "print").name, doc.name)
			self.assertTrue(all(row.company == self.company for row in frappe.get_list("Payment Entry", fields=["company"], page_length=100)))
			self.assertFalse(domain.details(domain.record(doc.name))["can_submit"])
			with self.assertRaises(frappe.PermissionError):
				domain.act(doc.name, "submit")
			if role == VIEWER:
				with self.assertRaises(frappe.PermissionError):
					domain.save(self.data(), request_key=uuid4().hex)
			else:
				self.assertTrue(domain.options()["accounts"])
				self.assertTrue(all(row.company == self.company for row in frappe.get_list("Account", fields=["company"], page_length=1000)))
				self.assertTrue(domain.save(self.data(), request_key=uuid4().hex)["document"]["name"])
			other = frappe.db.get_value("Payment Entry", {"company": ["!=", self.company]}, "name")
			if other:
				with self.assertRaises(frappe.PermissionError):
					frappe.get_doc("Payment Entry", other).check_permission("read")
			frappe.set_user("Administrator")
		manager = "voucher-approver-" + self.suffix + "@example.invalid"
		frappe.get_doc({"doctype": "User", "email": manager, "first_name": "Voucher test approver", "send_welcome_email": 0,
			"roles": [{"role": "Accounts Manager"}, {"role": VIEWER}, {"role": "AN Truck Portal User"}]}).insert()
		frappe.clear_cache(user=manager)
		frappe.set_user(manager)
		self.assertEqual(domain.act(doc.name, "submit")["document"]["docstatus"], 1)
		self.assertEqual(domain.act(doc.name, "cancel")["document"]["docstatus"], 2)

	def test_long_content_language_override_and_transfer_label(self):
		doc = self.create(remarks="بيان طويل مختلط ABC ١٢٣ 456\n"*30)
		with domain.print_language("ar"):
			html = frappe.get_print("Payment Entry", doc.name, domain.FORMAT, no_letterhead=1)
			self.assertIn("سند قبض", html)
			self.assertNotIn("RECEIPT VOUCHER", html)
		self.assertIn("ABC", html)
		from io import BytesIO
		from pypdf import PdfReader
		with domain.print_language("en"):
			pdf = frappe.get_print("Payment Entry", doc.name, domain.FORMAT, as_pdf=True, no_letterhead=1, pdf_generator="chrome")
		pages = PdfReader(BytesIO(pdf)).pages
		Path('/tmp/an-truck-vouchers/long-content.pdf').write_bytes(pdf)
		self.assertTrue(all(len(page.extract_text().strip()) > 10 for page in pages))
		self.assertTrue(any("Accountant" in page.extract_text() and "Manager" in page.extract_text() for page in pages))
		with patch.object(frappe.db, "get_value", return_value=None), patch.dict(frappe.form_dict, clear=True):
			self.assertEqual(domain.language(), "ar")
		# Explicitly exercise transfer title without writing or reclassifying a document.
		doc.payment_type = "Internal Transfer"
		with domain.print_language("en"):
			self.assertIn("TRANSFER VOUCHER", frappe.render_template(frappe.get_doc("Print Format", domain.FORMAT).html, {"doc": doc}))
