"""Company-scoped adapters to standard ERPNext Payment Entry, never a ledger."""
import hashlib
import json
import math
from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, nowdate

DT = "Payment Entry"
FORMAT = "AN Truck Voucher"
TYPES = {"Receive", "Pay"}
TOKEN = "custom_portal_voucher_request"
PAYLOAD = "custom_portal_voucher_payload"


def _party_types():
	return {name for name in frappe.get_all("Party Type", filters={"account_type": ["in", ["Receivable", "Payable"]]}, pluck="name") if frappe.db.exists("DocType", name)}


def company(requested=None):
	name = frappe.db.get_single_value("AN Truck Settings", "voucher_company")
	if not name:
		frappe.throw(_("Configure Financial Voucher Company in AN Truck Settings."))
	if requested and requested != name:
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	frappe.get_doc("Company", name).check_permission("read")
	return name


def record(name, permission="read", lock=False):
	doc = frappe.get_doc(DT, name, for_update=lock)
	company(doc.company)
	doc.check_permission(permission)
	if permission == "write" and not _reference_access(doc):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return doc


def _reference_access(doc):
	return all(frappe.has_permission(row.reference_doctype, "read", row.reference_name) for row in doc.references)


def payment_type(value):
	if value not in TYPES:
		frappe.throw(_("Select a receipt or payment voucher."))
	return value


def _party(doctype, name, co):
	if doctype not in _party_types():
		frappe.throw(_("Unsupported party type."))
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	if doc.get("disabled") or (doc.meta.has_field("company") and doc.get("company") and doc.company != co):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return doc


def _account(name, co, bank=False):
	doc = frappe.get_doc("Account", name)
	doc.check_permission("read")
	if doc.company != co or doc.is_group or doc.disabled or (bank and doc.account_type not in {"Bank", "Cash"}):
		frappe.throw(_("Select an enabled account belonging to the voucher company."))
	# Match the accounting controller's reference-doctype User Permission rules.
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_account_details
	get_account_details(name, nowdate())
	return doc


def options():
	co = company()
	if not frappe.has_permission(DT, "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	from an_truck_portal.api.import_file import _payment_modes
	from frappe.model.workflow import get_workflow_name
	return {"company": co, "today": nowdate(), "party_types": [dt for dt in sorted(_party_types())
		if frappe.db.exists("DocType", dt) and frappe.db.exists("Party Type", dt) and frappe.has_permission(dt, "read")],
		"accounts": frappe.get_list("Account", filters={"company": co, "is_group": 0, "disabled": 0,
			"account_type": ["in", ["Bank", "Cash"]]}, fields=["name", "account_currency", "account_type"],
			reference_doctype=DT, page_length=1000),
		"modes": [{**mode, "default_account": frappe.db.get_value("Mode of Payment Account",
			{"parent": mode["name"], "company": co}, "default_account")} for mode in _payment_modes(co)],
		"can_create": bool(frappe.has_permission(DT, "create")),
		"can_submit": bool(not get_workflow_name(DT) and frappe.has_permission(DT, "submit"))}


def parties(party_type, search="", page=1):
	co = company()
	if party_type not in _party_types():
		frappe.throw(_("Unsupported party type."))
	meta = frappe.get_meta(party_type)
	title = meta.title_field or "name"
	filters = {"disabled": 0} if meta.has_field("disabled") else {}
	if meta.has_field("company"):
		filters["company"] = co
	term = f"%{cstr(search).strip()[:100]}%"
	return frappe.get_list(party_type, filters=filters,
		or_filters=[[party_type, field, "like", term] for field in {"name", title}],
		fields=["name", f"{title} as label"], order_by="name", start=(max(cint(page), 1)-1)*30, page_length=30)


def outstanding(party_type, party, direction, date=None):
	co = company()
	payment_type(direction)
	_party(party_type, party, co)
	from erpnext.accounts.party import get_party_account
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_outstanding_reference_documents
	account = get_party_account(party_type, party, co)
	if not account:
		frappe.throw(_("Configure the party account before creating a voucher."))
	_account(account, co)
	rows = get_outstanding_reference_documents({"company": co, "party_type": party_type,
		"party": party, "party_account": account, "payment_type": direction,
		"posting_date": date or nowdate(), "get_outstanding_invoices": True}) or []
	# Core outstanding retrieval is ledger-based; additionally enforce invoice read permissions.
	result = []
	for row in rows:
		dt = row.get("voucher_type")
		if dt not in {"Sales Invoice", "Purchase Invoice"}:
			continue
		if frappe.has_permission(dt, "read", row.get("voucher_no")):
			result.append({key: row.get(key) for key in ("voucher_type", "voucher_no", "posting_date",
				"invoice_amount", "outstanding_amount", "payment_term", "payment_term_outstanding")})
	return {"rows": result, "party_account": account,
		"currency": frappe.get_cached_value("Account", account, "account_currency")}


def build(data, doc=None):
	data = frappe._dict(data)
	previous_party = (doc.party_type, doc.party, doc.payment_type) if doc else None
	previous_refs = {(row.reference_doctype, row.reference_name, row.payment_term or ""): row for row in doc.references} if doc else {}
	co = company(data.get("company"))
	direction = payment_type(data.get("payment_type"))
	_party(data.get("party_type"), data.get("party"), co)
	bank = _account(data.get("account"), co, bank=True)
	mode = frappe.get_doc("Mode of Payment", data.get("mode_of_payment"))
	mode.check_permission("read")
	if not mode.enabled or not frappe.db.exists("Mode of Payment Account", {"parent": mode.name, "company": co}):
		frappe.throw(_("Configure the payment method account for the voucher company."))
	if mode.type in {"Bank", "Cash"} and bank.account_type != mode.type:
		frappe.throw(_("The payment account does not match the payment method."))
	from erpnext.accounts.party import get_party_account
	party_account = get_party_account(data.party_type, data.party, co)
	if not party_account:
		frappe.throw(_("Configure the party account before creating a voucher."))
	party_account = _account(party_account, co)
	doc = doc or frappe.new_doc(DT)
	for field, value in {"company": co, "payment_type": direction, "party_type": data.party_type,
		"party": data.party, "posting_date": data.get("posting_date") or nowdate(),
		"mode_of_payment": mode.name, "reference_no": data.get("reference_no"),
		"reference_date": data.get("reference_date"), "custom_remarks": 1,
		"remarks": cstr(data.get("remarks"))[:10000]}.items():
		doc.set(field, value)
	doc.paid_from = party_account.name if direction == "Receive" else bank.name
	doc.paid_to = bank.name if direction == "Receive" else party_account.name
	doc.paid_from_account_currency = party_account.account_currency if direction == "Receive" else bank.account_currency
	doc.paid_to_account_currency = bank.account_currency if direction == "Receive" else party_account.account_currency
	doc.paid_from_account_type = party_account.account_type if direction == "Receive" else bank.account_type
	doc.paid_to_account_type = bank.account_type if direction == "Receive" else party_account.account_type
	doc.setup_party_account_field()
	# Recompute both FX rates using ERPNext, including after editing accounts/dates.
	doc.source_exchange_rate = doc.target_exchange_rate = None
	doc.set_exchange_rate()
	if flt(doc.source_exchange_rate) <= 0 or flt(doc.target_exchange_rate) <= 0:
		frappe.throw(_("Configure the exchange rate before creating this voucher."))
	amount = flt(data.get("amount"))
	if not math.isfinite(amount) or amount <= 0:
		frappe.throw(_("Voucher amount must be greater than zero."))
	if direction == "Receive":
		doc.received_amount = amount
		doc.paid_amount = flt(amount * doc.target_exchange_rate / doc.source_exchange_rate, doc.precision("paid_amount"))
	else:
		doc.paid_amount = amount
		doc.received_amount = flt(amount * doc.source_exchange_rate / doc.target_exchange_rate, doc.precision("received_amount"))
	doc.set("references", [])
	seen = set()
	for row in data.get("references") or []:
		row = frappe._dict(row)
		if not flt(row.get("allocated_amount")):
			continue
		if not math.isfinite(flt(row.get("allocated_amount"))):
			frappe.throw(_("Invalid voucher data."))
		dt, name = row.get("reference_doctype"), row.get("reference_name")
		key = (dt, name, row.get("payment_term") or "")
		if key in seen:
			frappe.throw(_("An invoice allocation cannot be repeated."))
		seen.add(key)
		original = previous_refs.get(key)
		if dt not in {"Sales Invoice", "Purchase Invoice"}:
			if not original or previous_party != (data.party_type, data.party, direction) or flt(row.allocated_amount) != flt(original.allocated_amount):
				frappe.throw(_("Select a valid invoice reference."))
			reference = frappe.get_doc(dt, name, for_update=True)
			reference.check_permission("read")
			if reference.get("company") != co or reference.docstatus != 1:
				frappe.throw(_("Invoice references must belong to this party and company."))
			original.idx = len(doc.references) + 1
			doc.append("references", original)
			continue
		invoice = frappe.get_doc(dt, name, for_update=True)
		invoice.check_permission("read")
		party_field = "customer" if dt == "Sales Invoice" else "supplier"
		if invoice.company != co or invoice.docstatus != 1 or invoice.get(party_field) != data.party or data.party_type != ("Customer" if dt == "Sales Invoice" else "Supplier"):
			frappe.throw(_("Invoice references must belong to this party and company."))
		if original:
			original.allocated_amount = flt(row.allocated_amount)
			original.idx = len(doc.references) + 1
			doc.append("references", original)
		else:
			doc.append("references", {"reference_doctype": dt, "reference_name": name,
				"allocated_amount": flt(row.allocated_amount), "payment_term": row.get("payment_term")})
	doc.set_missing_values()
	doc.set_missing_ref_details(force=True)
	doc.set_amounts()
	return doc


def actions(doc):
	from frappe.model.workflow import get_workflow_name, get_transitions, get_workflow_state_field
	workflow = get_workflow_name(DT)
	state = doc.get(get_workflow_state_field(workflow)) if workflow else None
	return {"can_edit": bool(doc.docstatus == 0 and doc.payment_type in TYPES and doc.has_permission("write") and _reference_access(doc)),
		"can_print": bool(doc.has_permission("print")), "has_workflow": bool(workflow),
		"can_submit": bool(not workflow and doc.docstatus == 0 and doc.has_permission("submit")),
		"can_cancel": bool(not workflow and doc.docstatus == 1 and doc.has_permission("cancel")),
		"workflow_state": _(state) if state else None,
		"workflow_actions": [{"action": row.action, "label": _(row.action)} for row in get_transitions(doc)] if workflow and state else []}


def details(doc):
	return {"document": {key: doc.get(key) for key in ("name", "company", "payment_type", "party_type", "party",
		"party_name", "posting_date", "mode_of_payment", "paid_from", "paid_to", "paid_amount", "received_amount",
		"paid_from_account_currency", "paid_to_account_currency", "source_exchange_rate", "target_exchange_rate",
		"reference_no", "reference_date", "remarks", "total_allocated_amount", "unallocated_amount", "status", "docstatus", "modified")},
		"references": [{key: row.get(key) for key in ("reference_doctype", "reference_name", "payment_term",
			"total_amount", "outstanding_amount", "allocated_amount", "exchange_rate")} for row in doc.references], **actions(doc)}


def save(data, name=None, modified=None, request_key=None):
	data = frappe.parse_json(data) if isinstance(data, str) else data
	if not isinstance(data, dict):
		frappe.throw(_("Invalid voucher data."))
	co = company(data.get("company"))
	if name:
		doc = record(name, "write", lock=True)
		if doc.docstatus != 0 or doc.payment_type not in TYPES:
			frappe.throw(_("Only draft receipt and payment vouchers can be edited."))
		if not modified or cstr(doc.modified) != modified:
			frappe.throw(_("This record changed. Reload it before saving."), frappe.TimestampMismatchError)
		return details(build(data, doc).save())
	if not frappe.has_permission(DT, "create"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not request_key or len(cstr(request_key)) > 100:
		frappe.throw(_("Reopen the voucher form and try again."))
	token = hashlib.sha256(f"{co}:{frappe.session.user}:{request_key}".encode()).hexdigest()
	payload = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
	def existing():
		rows = frappe.db.sql("select name from `tabPayment Entry` where custom_portal_voucher_request=%s for update", token)
		if rows:
			doc = record(rows[0][0])
			if doc.get(PAYLOAD) != payload:
				frappe.throw(_("This voucher request was already used with different data."))
			return details(doc)
	if result := existing():
		return result
	doc = build(data)
	doc.set(TOKEN, token)
	doc.set(PAYLOAD, payload)
	frappe.db.savepoint("portal_voucher_insert")
	try:
		doc.insert()
	except (frappe.UniqueValidationError, frappe.DuplicateEntryError):
		frappe.db.rollback(save_point="portal_voucher_insert")
		if result := existing():
			return result
		raise
	return details(doc)


def act(name, action, modified=None):
	doc = record(name, lock=True)
	from frappe.model.workflow import get_workflow_name, apply_workflow, get_transitions
	if action == "submit" and doc.docstatus == 1:
		doc.check_permission("submit")
		return details(doc)
	if action == "cancel" and doc.docstatus == 2:
		doc.check_permission("cancel")
		return details(doc)
	if modified and modified != cstr(doc.modified):
		frappe.throw(_("This record changed. Reload it before saving."), frappe.TimestampMismatchError)
	if get_workflow_name(DT):
		if action not in {row.action for row in get_transitions(doc)}:
			frappe.throw(_("Not a valid Workflow Action"), frappe.PermissionError)
		doc = apply_workflow(doc.as_dict(), action)
	elif action == "submit" and doc.docstatus == 0:
		doc.check_permission("submit")
		_account(doc.paid_from, doc.company)
		_account(doc.paid_to, doc.company)
		if doc.party_type and doc.party:
			_party(doc.party_type, doc.party, doc.company)
		# Recheck each reference's access/company/party immediately before posting.
		for ref in doc.references:
			invoice = frappe.get_doc(ref.reference_doctype, ref.reference_name, for_update=True)
			invoice.check_permission("read")
			if invoice.company != doc.company:
				frappe.throw(_("Not permitted"), frappe.PermissionError)
		doc.submit()
	elif action == "cancel" and doc.docstatus == 1:
		doc.check_permission("cancel")
		doc.cancel()
	else:
		frappe.throw(_("This voucher action is not allowed."), frappe.PermissionError)
	return details(doc)


def list_vouchers(search="", direction="", status="", from_date=None, to_date=None, page=1, page_length=20):
	co = company()
	filters = {"company": co}
	if direction:
		if direction not in TYPES | {"Internal Transfer"}:
			frappe.throw(_("Select a receipt or payment voucher."))
		filters["payment_type"] = direction
	if status != "" and status is not None:
		if cint(status) not in (0, 1, 2) or cstr(status) not in ("0", "1", "2"):
			frappe.throw(_("Invalid voucher status."))
		filters["docstatus"] = cint(status)
	if from_date and to_date:
		filters["posting_date"] = ["between", [from_date, to_date]]
	elif from_date:
		filters["posting_date"] = [">=", from_date]
	elif to_date:
		filters["posting_date"] = ["<=", to_date]
	search_filters = [[DT, key, "like", f"%{cstr(search).strip()[:100]}%"] for key in ("name", "party", "party_name", "reference_no")] if search else None
	page, length = max(cint(page), 1), min(max(cint(page_length), 1), 100)
	query = {"filters": filters, "or_filters": search_filters}
	rows = frappe.get_list(DT, **query, fields=["name", "posting_date", "payment_type", "party", "party_name", "paid_amount",
		"received_amount", "paid_from_account_currency", "paid_to_account_currency", "mode_of_payment", "docstatus", "status"],
		order_by="posting_date desc, creation desc", start=(page-1)*length, page_length=length)
	groups = frappe.get_list(DT, **query, fields=["payment_type", "docstatus", {"COUNT": "name", "as": "count"}],
		group_by="payment_type, docstatus", page_length=0)
	counts = {"total": sum(row.count for row in groups), "receipts": 0, "payments": 0, "draft": 0, "submitted": 0, "cancelled": 0}
	for row in groups:
		counts[{0: "draft", 1: "submitted", 2: "cancelled"}[row.docstatus]] += row.count
		if row.payment_type in TYPES:
			counts["receipts" if row.payment_type == "Receive" else "payments"] += row.count
	for row in rows:
		row["actions"] = actions(frappe.get_doc(DT, row.name))
	return {"company": co, "rows": rows, "counts": counts, "page": page, "has_more": page*length < counts["total"],
		"can_create": bool(frappe.has_permission(DT, "create"))}


def language(value=None):
	if value is None:
		value = frappe.flags.get("an_truck_voucher_language")
	if value is None:
		value = frappe.form_dict.get("voucher_lang") or frappe.form_dict.get("_lang")
	if value is None and frappe.session.user != "Guest":
		value = frappe.db.get_value("User", frappe.session.user, "language")
	return value if value in {"ar", "en"} else "ar"


@contextmanager
def print_language(value):
	from frappe.translate import print_language as standard_language
	previous = frappe.flags.get("an_truck_voucher_language")
	frappe.flags.an_truck_voucher_language = language(value)
	try:
		with standard_language(language(value)):
			yield
	finally:
		frappe.flags.an_truck_voucher_language = previous


def voucher_print_data(doc):
	company(doc.company)
	doc.check_permission("read")
	doc.check_permission("print")
	lang = language()
	amount = doc.received_amount if doc.payment_type == "Receive" else doc.paid_amount
	currency = doc.paid_to_account_currency if doc.payment_type == "Receive" else doc.paid_from_account_currency
	with print_language(lang):
		words = frappe.utils.money_in_words(amount, currency)
	co = frappe.get_doc("Company", doc.company)
	logo = co.company_logo
	if not logo and co.default_letter_head and frappe.has_permission("Letter Head", "read", co.default_letter_head):
		letter = frappe.get_doc("Letter Head", co.default_letter_head)
		logo = letter.get("image")
	contact = {field: co.get(field) for field in ("phone_no", "email", "website")}
	if (not contact["phone_no"] or not contact["email"]) and frappe.has_permission("Contact", "read"):
		from frappe.contacts.doctype.contact.contact import get_default_contact
		name = get_default_contact("Company", co.name)
		if name and frappe.has_permission("Contact", "read", name):
			person = frappe.get_doc("Contact", name)
			contact["phone_no"] = contact["phone_no"] or person.phone or person.mobile_no
			contact["email"] = contact["email"] or person.email_id
	address = ""
	from erpnext.setup.doctype.company.company import get_default_company_address
	from frappe.contacts.doctype.address.address import get_address_display
	address_name = get_default_company_address(co.name)
	if address_name and frappe.has_permission("Address", "read", address_name):
		address = get_address_display(address_name)
	return {"lang": lang, "rtl": lang == "ar", "amount": amount, "currency": currency, "words": words,
		"logo": logo or "/assets/an_truck_portal/logo.svg", "company": co, "address": address, "contact": contact,
		"references": doc.references}
