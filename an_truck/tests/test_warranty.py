import base64
from io import BytesIO
from datetime import datetime, timezone
from unittest.mock import patch

import frappe
from frappe.desk.query_report import run as run_report
from frappe.desk.search import search_link
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_years, now_datetime

from an_truck.warranty.activation import activate_vehicle_warranty, activate_warranties_from_delivery
from an_truck.warranty.backfill import execute_historical_backfill, preview_historical_warranties
from an_truck.warranty.claim import validate_warranty_claim
from an_truck.warranty.portal_api import (
	apply_claim_action as portal_action,
	create_claim as portal_create_claim,
	download_claim_file,
	get_claim as portal_get_claim,
	get_portal_context,
	search_vin,
	update_claim as portal_update_claim,
	upload_claim_file,
)
from an_truck.warranty.setup import INTERNAL_MANAGER, INTERNAL_USER, PROVIDER_USER
from an_truck.warranty.quality import get_warranty_data_quality
from an_truck.warranty.tasks import expire_vehicle_warranties, send_warranty_expiry_reminders
from an_truck.warranty.timezone import get_company_local_date
from an_truck.warranty.reporting import (
	active_vehicle_warranties,
	expiring_warranties,
	get_vehicle_warranty_summary,
	get_warranty_dashboard,
	outside_warranty_repairs,
	provider_performance,
	warranty_claim_history_by_vin,
	warranty_claims as warranty_claims_report,
	warranty_cost_by_branch,
	warranty_cost_by_component,
	warranty_cost_by_provider,
	warranty_cost_by_vehicle_model,
	warranty_cost_by_vin,
)


class TestVehicleWarrantyFlow(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.suffix = now_datetime().strftime("%Y%m%d%H%M%S%f")
		self.vehicle = self.get_delivered_vehicle()
		self.provider = frappe.get_doc({
			"doctype": "Warranty Provider",
			"provider_name": f"Test Warranty Provider {self.suffix}",
			"commercial_registration": f"CR-{self.suffix}",
			"status": "Active",
			"active": 1,
		}).insert()
		self.branch = self.make_branch("RUH", "Riyadh")
		self.other_branch = self.make_branch("JED", "Jeddah")
		self.contract = frappe.get_doc({
			"doctype": "Warranty Provider Contract",
			"contract_number": f"WPC-{self.suffix}",
			"warranty_provider": self.provider.name,
			"contract_type": "Fixed Period",
			"status": "Active",
			"start_date": "2020-01-01",
			"end_date": "2035-12-31",
		}).insert()
		self.engine = self.make_category("Engine")
		self.brakes = self.make_category("Brakes")
		self.template = frappe.get_doc({
			"doctype": "Warranty Coverage Template",
			"template_name": f"Two Year Truck Warranty {self.suffix}",
			"duration": 2,
			"duration_unit": "Years",
			"active": 1,
			"coverage_items": [
				{"coverage_category": self.engine.name, "covered": 1, "description": "Engine system"},
				{"coverage_category": self.brakes.name, "covered": 0, "description": "Wear items excluded"},
			],
		}).insert()

	def tearDown(self):
		frappe.set_user("Administrator")

	def get_delivered_vehicle(self):
		base_name = frappe.db.get_value(
			"Vehicle Master",
			{"customer": ["is", "set"], "disabled": 0},
			"name",
		)
		if not base_name:
			self.skipTest("A sold Vehicle Master fixture is required for warranty integration tests.")
		base = frappe.get_doc("Vehicle Master", base_name)
		vin = f"TEST-WARRANTY-VIN-{self.suffix}"
		frappe.get_doc({
			"doctype": "Serial No", "serial_no": vin, "item_code": base.item_code,
			"company": base.company,
		}).insert(ignore_permissions=True)
		return frappe.get_doc({
			"doctype": "Vehicle Master", "vin": vin, "item_code": base.item_code,
			"company": base.company, "customer": base.customer, "vehicle_status": "Delivered",
		}).insert(ignore_permissions=True)

	def make_branch(self, code, city):
		return frappe.get_doc({
			"doctype": "Warranty Provider Branch",
			"warranty_provider": self.provider.name,
			"branch_name": f"{city} Test Branch {self.suffix}",
			"branch_code": f"{code}-{self.suffix}",
			"city": city,
			"active": 1,
		}).insert()

	def make_category(self, label):
		return frappe.get_doc({
			"doctype": "Warranty Coverage Category",
			"category_name": f"{label} {self.suffix}",
			"active": 1,
		}).insert()

	def make_vehicle(self, company=None):
		company = company or self.vehicle.company
		vin = f"TEST-WARRANTY-EXTRA-{self.suffix}-{frappe.generate_hash(length=6)}"
		frappe.get_doc({
			"doctype": "Serial No", "serial_no": vin, "item_code": self.vehicle.item_code,
			"company": company,
		}).insert(ignore_permissions=True)
		return frappe.get_doc({
			"doctype": "Vehicle Master", "vin": vin, "item_code": self.vehicle.item_code,
			"company": company, "customer": self.vehicle.customer, "vehicle_status": "Delivered",
		}).insert(ignore_permissions=True)

	def make_warranty(self, vehicle=None):
		vehicle = vehicle or self.vehicle
		return frappe.get_doc({
			"doctype": "Vehicle Warranty", "vehicle_master": vehicle.name,
			"coverage_template": self.template.name, "warranty_provider": self.provider.name,
			"provider_contract": self.contract.name, "warranty_start_date": "2026-10-01", "status": "Active",
		}).insert(ignore_permissions=True)

	def make_provider_user(self, branch=None, all_branches=0, provider=None):
		email = f"portal-{frappe.generate_hash(length=8)}-{self.suffix}@example.com"
		user = frappe.get_doc({
			"doctype": "User", "email": email, "first_name": "Provider Portal Test",
			"enabled": 1, "user_type": "Website User", "send_welcome_email": 0,
		}).insert(ignore_permissions=True)
		user.add_roles(PROVIDER_USER)
		access = frappe.get_doc({
			"doctype": "Warranty Provider User Access", "user": email,
			"warranty_provider": provider or self.provider.name,
			"warranty_provider_branch": None if all_branches else (branch or self.branch.name),
			"all_branches": all_branches, "active": 1,
		}).insert(ignore_permissions=True)
		return user, access

	def make_reporting_claim(self, warranty, branch=None, complaint_date="2026-10-02", part_cost=100, service_cost=50):
		return frappe.get_doc({
			"doctype": "Warranty Claim", "custom_vehicle_warranty": warranty.name,
			"custom_warranty_provider_branch": (branch or self.branch).name,
			"complaint": "Reporting engine failure", "complaint_date": complaint_date,
			"custom_failure_date": complaint_date, "custom_root_cause": "Engine Sensor",
			"custom_parts": [{
				"coverage_category": self.engine.name, "description": "Covered sensor", "qty": 1,
				"uom": "Nos", "unit_cost": part_cost, "coverage_status": "Inside Warranty",
			}],
			"custom_services": [{
				"coverage_category": self.engine.name, "service_type": "Customer labor", "hours": 1,
				"rate": service_cost, "coverage_status": "Outside Warranty",
			}],
		}).insert(ignore_permissions=True)

	def configure_defaults(self):
		settings = frappe.get_doc("AN Truck Settings")
		settings.auto_activate_vehicle_warranty = 1
		settings.default_warranty_provider = self.provider.name
		settings.default_warranty_coverage_template = self.template.name
		settings.save(ignore_permissions=True)

	def activate_sample_warranty(self):
		self.configure_defaults()
		created = activate_warranties_from_delivery(
			frappe._dict(
				name=None,
				posting_date="2026-10-01",
				items=[frappe._dict(custom_vehicle_master=self.vehicle.name, item_code=self.vehicle.item_code)],
			)
		)
		return frappe.get_doc("Vehicle Warranty", created[0])

	def test_delivery_activation_snapshot_expiry_and_idempotency(self):
		warranty = self.activate_sample_warranty()
		self.assertEqual(warranty.vin, self.vehicle.vin)
		self.assertEqual(warranty.status, "Active")
		self.assertEqual(str(warranty.warranty_expiry_date), str(add_days(add_years(warranty.warranty_start_date, 2), -1)))
		self.assertEqual(len(warranty.coverage_snapshot), 2)
		self.assertEqual(frappe.db.get_value("Serial No", warranty.vin, "warranty_expiry_date"), warranty.warranty_expiry_date)
		second = activate_vehicle_warranty(self.vehicle.name, warranty.delivery_date, activation_source="Delivery Note")
		self.assertEqual(second, warranty.name)
		duplicate = frappe.get_doc({
			"doctype": "Vehicle Warranty", "vehicle_master": self.vehicle.name,
			"coverage_template": self.template.name, "warranty_provider": self.provider.name,
			"provider_contract": self.contract.name, "warranty_start_date": "2026-10-01", "status": "Active",
		})
		self.assertRaises(frappe.ValidationError, duplicate.insert)
		warranty.status = "Expired"
		warranty.save(ignore_permissions=True)
		historical_claim = self.make_reporting_claim(warranty)
		renewal = frappe.get_doc({
			"doctype": "Vehicle Warranty", "vehicle_master": self.vehicle.name,
			"coverage_template": self.template.name, "warranty_provider": self.provider.name,
			"provider_contract": self.contract.name, "warranty_start_date": "2026-10-02", "status": "Active",
			"renewal_of": warranty.name, "is_extension": 1,
		}).insert(ignore_permissions=True)
		self.assertEqual(renewal.status, "Active")
		self.assertEqual(renewal.renewal_of, warranty.name)
		self.assertTrue(frappe.db.exists("Vehicle Warranty", warranty.name))
		self.assertEqual(frappe.db.get_value("Warranty Claim", historical_claim.name, "custom_vehicle_warranty"), warranty.name)
		self.assertIn(historical_claim.name, {row.claim for row in warranty_claim_history_by_vin({"vin": warranty.vin})[1]})

	def test_complete_claim_cost_and_internal_approval_flow(self):
		warranty = self.activate_sample_warranty()
		claim = frappe.get_doc({
			"doctype": "Warranty Claim",
			"custom_vehicle_warranty": warranty.name,
			"custom_warranty_provider_branch": self.branch.name,
			"complaint_date": warranty.warranty_start_date,
			"complaint": "Engine sensor failure",
			"custom_failure_date": warranty.warranty_start_date,
			"custom_inspection_date": warranty.warranty_start_date,
			"custom_technician_name": "Test Technician",
			"custom_diagnosis": "Sensor failure confirmed",
			"custom_provider_recommendation": "Partially Covered",
			"custom_parts": [
				{"coverage_category": self.engine.name, "description": "Engine Sensor", "qty": 1, "uom": "Nos", "unit_cost": 750, "coverage_status": "Inside Warranty"},
				{"coverage_category": self.brakes.name, "description": "Brake Pads", "qty": 2, "uom": "Nos", "unit_cost": 300, "coverage_status": "Outside Warranty"},
			],
			"custom_services": [
				{"coverage_category": self.engine.name, "service_type": "Engine Diagnosis", "hours": 2, "rate": 300, "coverage_status": "Inside Warranty"},
			],
			"custom_other_charges": 500,
			"custom_other_covered_amount": 0,
		}).insert(ignore_permissions=True)
		self.assertEqual(claim.serial_no, warranty.vin)
		self.assertEqual(claim.custom_total_repair_cost, 2450)
		self.assertEqual(claim.custom_warranty_covered_amount, 1350)
		self.assertEqual(claim.custom_customer_payable_amount, 1100)
		self.assertEqual(claim.custom_provider_claim_amount, 1350)
		email = f"warranty-internal-{self.suffix}@example.com"
		user = frappe.get_doc({
			"doctype": "User", "email": email, "first_name": "Internal Warranty Test", "enabled": 1,
			"user_type": "System User", "send_welcome_email": 0,
		}).insert(ignore_permissions=True)
		user.add_roles(INTERNAL_USER, INTERNAL_MANAGER)
		frappe.set_user(email)
		self.assertTrue(frappe.has_permission("Warranty Claim", "read", doc=claim))
		claim = apply_workflow(claim, "Submit Claim")
		claim = apply_workflow(claim, "Start Review")
		claim = apply_workflow(claim, "Approve")
		self.assertEqual(claim.custom_claim_status, "Approved")
		self.assertEqual(claim.custom_internal_decision, "Approved")
		self.assertEqual(claim.custom_approved_provider_claim_amount, 1350)
		partial = self.make_reporting_claim(warranty)
		partial = apply_workflow(partial, "Submit Claim")
		partial = apply_workflow(partial, "Start Review")
		partial.custom_approved_provider_claim_amount = 50
		partial.save()
		partial = apply_workflow(partial, "Partially Approve")
		self.assertEqual(partial.custom_internal_decision, "Partially Approved")
		self.assertEqual(partial.custom_approved_provider_claim_amount, 50)

	def test_branch_must_belong_to_provider(self):
		warranty = self.activate_sample_warranty()
		other_provider = frappe.get_doc({"doctype": "Warranty Provider", "provider_name": f"Other Provider {self.suffix}", "status": "Active", "active": 1}).insert()
		wrong_branch = frappe.get_doc({
			"doctype": "Warranty Provider Branch", "warranty_provider": other_provider.name,
			"branch_name": f"Wrong Branch {self.suffix}", "branch_code": f"WRONG-{self.suffix}", "city": "Dammam", "active": 1,
		}).insert()
		claim = frappe.get_doc({
			"doctype": "Warranty Claim", "custom_vehicle_warranty": warranty.name,
			"custom_warranty_provider_branch": wrong_branch.name, "complaint": "Test", "complaint_date": warranty.warranty_start_date,
		})
		self.assertRaises(frappe.ValidationError, validate_warranty_claim, claim)

	def test_restricted_provider_user_branch_is_forced(self):
		warranty = self.activate_sample_warranty()
		email = f"warranty-{self.suffix}@example.com"
		user = frappe.get_doc({
			"doctype": "User", "email": email, "first_name": "Warranty Test", "enabled": 1,
			"user_type": "Website User", "send_welcome_email": 0,
		}).insert(ignore_permissions=True)
		user.add_roles(PROVIDER_USER)
		frappe.get_doc({
			"doctype": "Warranty Provider User Access", "user": email,
			"warranty_provider": self.provider.name, "warranty_provider_branch": self.branch.name,
			"all_branches": 0, "active": 1,
		}).insert(ignore_permissions=True)
		frappe.set_user(email)
		claim = frappe.get_doc({
			"doctype": "Warranty Claim", "custom_vehicle_warranty": warranty.name,
			"complaint": "Provider-created claim", "complaint_date": warranty.warranty_start_date,
		})
		validate_warranty_claim(claim)
		self.assertEqual(claim.custom_warranty_provider_branch, self.branch.name)
		claim.custom_warranty_provider_branch = self.other_branch.name
		self.assertRaises(frappe.PermissionError, validate_warranty_claim, claim)

	def test_company_aware_expiry_is_date_based_and_idempotent(self):
		saudi_warranty = self.make_warranty()
		frappe.db.set_value("Vehicle Warranty", saudi_warranty.name, "warranty_expiry_date", "2026-10-03", update_modified=False)
		self.assertEqual(frappe.db.get_value("Company", self.vehicle.company, "custom_warranty_timezone"), "Asia/Riyadh")

		other_company = frappe.db.get_value("Company", {"name": ["!=", self.vehicle.company]}, "name")
		if not other_company:
			self.skipTest("A second Company is required for multi-timezone scheduler testing.")
		frappe.db.set_value("Company", other_company, "custom_warranty_timezone", "America/Los_Angeles")
		other_warranty = self.make_warranty(self.make_vehicle(other_company))
		frappe.db.set_value("Vehicle Warranty", other_warranty.name, "warranty_expiry_date", "2026-10-03", update_modified=False)

		already_expired = self.make_warranty(self.make_vehicle())
		frappe.db.set_value(
			"Vehicle Warranty", already_expired.name,
			{"warranty_expiry_date": "2026-10-02", "status": "Expired", "active_vin_key": None},
			update_modified=False,
		)
		unchanged_modified = frappe.db.get_value("Vehicle Warranty", already_expired.name, "modified")

		instant = datetime(2026, 10, 3, 22, 30, tzinfo=timezone.utc)
		first = expire_vehicle_warranties(now_utc=instant)
		self.assertEqual(frappe.db.get_value("Vehicle Warranty", saudi_warranty.name, "status"), "Expired")
		self.assertEqual(frappe.db.get_value("Vehicle Warranty", other_warranty.name, "status"), "Active")
		self.assertEqual(frappe.db.get_value("Vehicle Warranty", already_expired.name, "modified"), unchanged_modified)
		self.assertEqual(first["expired"], 1)
		second = expire_vehicle_warranties(now_utc=instant)
		self.assertEqual(second["expired"], 0)

	def test_portal_scope_branch_spoofing_allowlist_and_disabled_access(self):
		warranty = self.make_warranty()
		user, access = self.make_provider_user()
		frappe.set_user("Guest")
		self.assertRaises(frappe.PermissionError, search_vin, warranty.vin)
		frappe.set_user(user.name)
		context = get_portal_context()
		self.assertEqual(context["branch_mode"], "fixed")
		self.assertEqual(search_vin(warranty.vin)["name"], warranty.name)
		self.assertRaises(frappe.DoesNotExistError, search_vin, warranty.vin[:8])
		self.assertRaises(
			frappe.PermissionError,
			portal_create_claim,
			warranty.name,
			"Spoofed branch claim",
			self.other_branch.name,
			None,
			frappe.as_json({"custom_failure_date": "2026-10-02"}),
		)
		claim_data = portal_create_claim(
			warranty.name, "Engine fault", self.branch.name, None,
			frappe.as_json({"custom_failure_date": "2026-10-02"}),
		)
		self.assertEqual(claim_data["branch"], self.branch.name)
		for forbidden in ("custom_internal_notes", "custom_internal_decision", "custom_approved_provider_claim_amount", "customer"):
			self.assertNotIn(forbidden, claim_data)
		self.assertRaises(
			frappe.PermissionError,
			portal_update_claim,
			claim_data["name"],
			frappe.as_json({"custom_internal_notes": "attempted disclosure"}),
		)

		frappe.set_user("Administrator")
		all_branch_user, _all_access = self.make_provider_user(all_branches=1)
		frappe.set_user(all_branch_user.name)
		other_branch_claim = portal_create_claim(
			warranty.name, "All-branches manager claim", self.other_branch.name, None,
			frappe.as_json({"custom_failure_date": "2026-10-02"}),
		)
		self.assertEqual(other_branch_claim["branch"], self.other_branch.name)
		frappe.set_user(user.name)
		self.assertRaises(frappe.PermissionError, portal_get_claim, other_branch_claim["name"])

		frappe.set_user("Administrator")
		other_provider = frappe.get_doc({
			"doctype": "Warranty Provider", "provider_name": f"Portal Other {self.suffix}",
			"status": "Active", "active": 1,
		}).insert()
		other_provider_branch = frappe.get_doc({
			"doctype": "Warranty Provider Branch", "warranty_provider": other_provider.name,
			"branch_name": f"Other Provider Branch {self.suffix}", "branch_code": f"OP-{self.suffix}",
			"city": "Riyadh", "active": 1,
		}).insert()
		other_user, _ = self.make_provider_user(other_provider_branch.name, provider=other_provider.name)
		frappe.set_user(other_user.name)
		self.assertRaises(frappe.DoesNotExistError, search_vin, warranty.vin)
		self.assertRaises(frappe.PermissionError, portal_get_claim, claim_data["name"])

		frappe.set_user("Administrator")
		frappe.db.set_value("Warranty Provider Contract", self.contract.name, "status", "Terminated")
		frappe.set_user(user.name)
		self.assertFalse(search_vin(warranty.vin)["can_create_claim"])
		self.assertRaises(
			frappe.ValidationError,
			portal_create_claim,
			warranty.name,
			"Contract terminated",
			self.branch.name,
			None,
			frappe.as_json({"custom_failure_date": "2026-10-02"}),
		)
		frappe.set_user("Administrator")
		frappe.db.set_value(
			"Vehicle Warranty", warranty.name,
			{"status": "Expired", "active_vin_key": None},
			update_modified=False,
		)
		frappe.set_user(user.name)
		self.assertEqual(search_vin(warranty.vin)["status"], "Expired")
		self.assertFalse(search_vin(warranty.vin)["can_create_claim"])

		frappe.set_user("Administrator")
		frappe.db.set_value("Warranty Provider Branch", self.branch.name, "active", 0)
		frappe.set_user(user.name)
		self.assertRaises(frappe.PermissionError, get_portal_context)
		frappe.set_user("Administrator")
		frappe.db.set_value("Warranty Provider Branch", self.branch.name, "active", 1)
		frappe.db.set_value("Warranty Provider User Access", access.name, "active", 0)
		frappe.set_user(user.name)
		self.assertRaises(frappe.PermissionError, get_portal_context)

	def test_provider_portal_complete_claim_journey_and_private_file_security(self):
		warranty = self.make_warranty()
		provider_user, _ = self.make_provider_user()
		frappe.set_user(provider_user.name)
		claim = portal_create_claim(
			warranty.name, "Engine sensor failure", self.branch.name, None,
			frappe.as_json({"custom_failure_date": "2026-10-02"}),
		)
		claim = portal_action(claim["name"], "Submit Claim")
		self.assertEqual(claim["status"], "Submitted by Provider")

		frappe.set_user("Administrator")
		manager_email = f"portal-manager-{self.suffix}@example.com"
		manager = frappe.get_doc({
			"doctype": "User", "email": manager_email, "first_name": "Portal Manager",
			"enabled": 1, "user_type": "System User", "send_welcome_email": 0,
		}).insert(ignore_permissions=True)
		manager.add_roles(INTERNAL_USER, INTERNAL_MANAGER)
		frappe.set_user(manager.name)
		manager_claim = apply_workflow(frappe.get_doc("Warranty Claim", claim["name"]), "Start Review")
		manager_claim = apply_workflow(manager_claim, "Request More Information")

		frappe.set_user(provider_user.name)
		updated = portal_update_claim(
			claim["name"],
			frappe.as_json({
				"custom_inspection_date": "2026-10-02", "custom_technician_name": "Portal Technician",
				"custom_diagnosis": "Sensor circuit failure", "custom_provider_recommendation": "Covered",
			}),
		)
		self.assertEqual(updated["inspection"]["technician"], "Portal Technician")
		portal_action(claim["name"], "Resubmit")

		frappe.set_user(manager.name)
		manager_claim = apply_workflow(frappe.get_doc("Warranty Claim", claim["name"]), "Start Review")
		apply_workflow(manager_claim, "Approve")

		frappe.set_user(provider_user.name)
		portal_action(claim["name"], "Start Repair")
		portal_update_claim(
			claim["name"],
			frappe.as_json({
				"parts": [{
					"coverage_category": self.engine.name, "description": "Engine Sensor", "qty": 1,
					"uom": "Nos", "unit_cost": 750, "coverage_status": "Inside Warranty",
				}],
				"services": [{
					"coverage_category": self.engine.name, "service_type": "Diagnosis", "hours": 2,
					"rate": 300, "coverage_status": "Inside Warranty",
				}],
			}),
		)
		portal_action(claim["name"], "Complete Repair")
		from pypdf import PdfWriter
		pdf = BytesIO()
		writer = PdfWriter()
		writer.add_blank_page(width=72, height=72)
		writer.write(pdf)
		with_document = upload_claim_file(
			claim["name"], "repair-report.pdf", base64.b64encode(pdf.getvalue()).decode(),
			"Repair Report", invoice_number="INV-TEST", invoice_amount=1350, vat_amount=202.5,
		)
		self.assertEqual(with_document["documents"][0]["total_including_vat"], 1552.5)
		final = portal_action(claim["name"], "Submit Final Documents")
		self.assertEqual(final["status"], "Final Documents Submitted")
		self.assertEqual(final["cost_summary"]["provider_claim_amount"], 1350)
		frappe.set_user(manager.name)
		closed = apply_workflow(frappe.get_doc("Warranty Claim", claim["name"]), "Close")
		self.assertEqual(closed.custom_claim_status, "Closed")

		frappe.set_user("Administrator")
		other_provider = frappe.get_doc({
			"doctype": "Warranty Provider", "provider_name": f"File Other {self.suffix}",
			"status": "Active", "active": 1,
		}).insert()
		other_branch = frappe.get_doc({
			"doctype": "Warranty Provider Branch", "warranty_provider": other_provider.name,
			"branch_name": f"File Other Branch {self.suffix}", "branch_code": f"FILE-{self.suffix}",
			"city": "Jeddah", "active": 1,
		}).insert()
		other_user, _ = self.make_provider_user(other_branch.name, provider=other_provider.name)
		frappe.set_user(other_user.name)
		self.assertRaises(frappe.PermissionError, download_claim_file, with_document["documents"][0]["file_id"])

	def test_phase5_report_filters_and_server_calculated_totals(self):
		warranty = self.make_warranty()
		claim_one = self.make_reporting_claim(warranty, self.branch, "2026-10-02", 100, 50)
		claim_two = self.make_reporting_claim(warranty, self.other_branch, "2026-10-03", 200, 75)

		_columns, rows = warranty_claims_report({"vin": warranty.vin})
		self.assertEqual({row.claim_number for row in rows}, {claim_one.name, claim_two.name})
		self.assertEqual(sum(row.total_repair_cost for row in rows), 425)
		self.assertEqual(sum(row.warranty_covered_amount for row in rows), 300)
		self.assertEqual(sum(row.customer_payable for row in rows), 125)
		self.assertEqual(sum(row.provider_claim_amount for row in rows), 300)

		self.assertEqual(len(warranty_claims_report({"provider": self.provider.name})[1]), 2)
		self.assertEqual(len(warranty_claims_report({"branch": self.branch.name})[1]), 1)
		self.assertEqual(len(warranty_claims_report({"vin": warranty.vin, "from_date": "2026-10-03", "to_date": "2026-10-03"})[1]), 1)
		self.assertEqual(len(warranty_claims_report({"vin": warranty.vin, "company": self.vehicle.company})[1]), 2)
		self.assertFalse(warranty_claims_report({
			"vin": warranty.vin,
			"company": frappe.db.get_value("Company", {"name": ["!=", self.vehicle.company]}, "name"),
		})[1])

		vin_row = warranty_cost_by_vin({"vin": warranty.vin})[1][0]
		self.assertEqual(vin_row.number_of_claims, 2)
		self.assertEqual(vin_row.total_repair_cost, 425)
		provider_row = warranty_cost_by_provider({"provider": self.provider.name})[1][0]
		self.assertEqual(provider_row.provider_claim_amount, 300)
		self.assertEqual(len(warranty_cost_by_branch({"branch": self.branch.name})[1]), 1)
		component_row = warranty_cost_by_component({"coverage_category": self.engine.name})[1][0]
		self.assertEqual(component_row.number_of_claims, 2)
		self.assertEqual(component_row.number_of_parts_services, 4)
		self.assertEqual(component_row.total_cost, 425)
		outside = outside_warranty_repairs({"vin": warranty.vin})[1]
		self.assertEqual(len(outside), 2)
		self.assertEqual(sum(row.customer_payable for row in outside), 125)
		model_row = warranty_cost_by_vehicle_model({"company": self.vehicle.company, "provider": self.provider.name})[1][0]
		self.assertEqual(model_row.warranty_claims, 2)
		self.assertEqual(model_row.total_warranty_cost, 300)
		performance = provider_performance({"provider": self.provider.name})[1]
		self.assertEqual(sum(row.claims_received for row in performance), 2)

	def test_phase5_expiry_summary_vin_history_and_dashboard(self):
		warranty = self.make_warranty()
		today = get_company_local_date(self.vehicle.company)
		frappe.db.set_value("Vehicle Warranty", warranty.name, "warranty_expiry_date", add_days(today, 10), update_modified=False)
		claim = self.make_reporting_claim(warranty, self.branch, str(today), 350, 150)

		active = active_vehicle_warranties({"vin": warranty.vin})[1]
		self.assertEqual(active[0].remaining_days, 10)
		self.assertFalse(expiring_warranties({"days_to_expiry": 5, "provider": self.provider.name})[1])
		self.assertEqual(expiring_warranties({"days_to_expiry": 10, "provider": self.provider.name})[1][0].vin, warranty.vin)

		summary = get_vehicle_warranty_summary(vehicle_master=self.vehicle.name)
		self.assertEqual(summary["warranty"].name, warranty.name)
		self.assertEqual(summary["number_of_claims"], 1)
		self.assertEqual(summary["total_warranty_cost"], 500)
		self.assertEqual(summary["open_claims"], 1)
		columns, history, message = warranty_claim_history_by_vin({"vin": warranty.vin})
		self.assertTrue(columns)
		self.assertEqual(history[0].claim, claim.name)
		self.assertEqual(history[0].parts_cost, 350)
		self.assertEqual(history[0].labor_cost, 150)
		self.assertIn(warranty.name, message)
		dashboard = get_warranty_dashboard(self.vehicle.company)
		self.assertTrue(dashboard["kpis"])
		self.assertEqual(len(dashboard["charts"]), 7)

	def test_phase5_provider_user_cannot_access_internal_reporting(self):
		warranty = self.make_warranty()
		provider_user, _access = self.make_provider_user()
		frappe.set_user(provider_user.name)
		for method, args in (
			(warranty_claims_report, ({"vin": warranty.vin},)),
			(get_warranty_dashboard, (self.vehicle.company,)),
			(get_vehicle_warranty_summary, (self.vehicle.name,)),
		):
			with self.assertRaises(frappe.PermissionError):
				method(*args)

	def test_phase6_backfill_preview_execution_and_idempotency(self):
		self.configure_defaults()
		missing_date = preview_historical_warranties({"vin": self.vehicle.vin})[0]
		self.assertEqual(missing_date.result, "MISSING DELIVERY DATE")
		self.assertEqual(missing_date.eligibility, "REQUIRES MANUAL REVIEW")

		delivery = frappe._dict(
			delivery_source="Sales Invoice Delivery Date",
			delivery_document=None,
			delivery_date=frappe.utils.getdate("2026-10-01"),
		)
		with patch("an_truck.warranty.backfill._delivery_source", return_value=delivery):
			ready = preview_historical_warranties({"vin": self.vehicle.vin})[0]
			self.assertEqual(ready.result, "READY")
			self.assertEqual(str(ready.calculated_expiry_date), "2028-09-30")
			summary = execute_historical_backfill(vin=self.vehicle.vin)
		self.assertEqual(summary["eligible"], 1)
		self.assertEqual(summary["created"], 1)
		warranty = frappe.get_doc("Vehicle Warranty", summary["results"][0]["warranty"])
		self.assertEqual(len(warranty.coverage_snapshot), 2)
		self.assertEqual(frappe.db.get_value("Serial No", warranty.vin, "warranty_expiry_date"), warranty.warranty_expiry_date)
		self.assertTrue(frappe.db.exists("Comment", {
			"reference_doctype": "Vehicle Warranty", "reference_name": warranty.name,
		}))
		second = execute_historical_backfill(vin=self.vehicle.vin)
		self.assertEqual(second["created"], 0)
		self.assertEqual(second["skipped"], 1)

	def test_phase6_mixed_costs_match_claim_portal_dashboard_reports_and_history(self):
		warranty = self.make_warranty()
		today = get_company_local_date(self.vehicle.company)
		before = {
			row["label"]: row["value"] for row in get_warranty_dashboard(self.vehicle.company)["financial_kpis"]
		}
		claim = frappe.get_doc({
			"doctype": "Warranty Claim", "custom_vehicle_warranty": warranty.name,
			"custom_warranty_provider_branch": self.branch.name,
			"complaint": "Mixed covered and customer-payable repair", "complaint_date": today,
			"custom_parts": [
				{"coverage_category": self.engine.name, "description": "Engine component", "qty": 1, "uom": "Nos", "unit_cost": 3000, "coverage_status": "Inside Warranty"},
				{"coverage_category": self.brakes.name, "description": "Brake item", "qty": 1, "uom": "Nos", "unit_cost": 700, "coverage_status": "Outside Warranty"},
			],
			"custom_services": [
				{"coverage_category": self.engine.name, "service_type": "Covered labor", "hours": 1, "rate": 500, "coverage_status": "Inside Warranty"},
				{"coverage_category": self.brakes.name, "service_type": "Outside labor", "hours": 1, "rate": 300, "coverage_status": "Outside Warranty"},
			],
		}).insert(ignore_permissions=True)
		self.assertEqual(claim.custom_total_repair_cost, 4500)
		self.assertEqual(claim.custom_warranty_covered_amount, 3500)
		self.assertEqual(claim.custom_customer_payable_amount, 1000)
		self.assertEqual(claim.custom_provider_claim_amount, 3500)

		vin_row = warranty_cost_by_vin({"vin": warranty.vin})[1][0]
		self.assertEqual((vin_row.total_repair_cost, vin_row.warranty_covered_cost, vin_row.customer_payable), (4500, 3500, 1000))
		history = warranty_claim_history_by_vin({"vin": warranty.vin})[1][0]
		self.assertEqual((history.parts_cost, history.labor_cost, history.warranty_covered, history.customer_payable), (3700, 800, 3500, 1000))
		after = {
			row["label"]: row["value"] for row in get_warranty_dashboard(self.vehicle.company)["financial_kpis"]
		}
		self.assertEqual(after["Total Warranty Cost This Month"] - before["Total Warranty Cost This Month"], 3500)
		self.assertEqual(after["Customer Payable Amount This Month"] - before["Customer Payable Amount This Month"], 1000)

		provider_user, _access = self.make_provider_user()
		frappe.set_user(provider_user.name)
		portal = portal_get_claim(claim.name)
		self.assertEqual(portal["cost_summary"]["total_repair_cost"], 4500)
		self.assertEqual(portal["cost_summary"]["warranty_covered_amount"], 3500)
		self.assertEqual(portal["cost_summary"]["customer_payable_amount"], 1000)

	def test_phase6_data_quality_detects_unsafe_records_without_repair(self):
		warranty = self.make_warranty()
		claim = self.make_reporting_claim(warranty)
		uncovered_vehicle = self.make_vehicle()
		frappe.db.set_value("Warranty Claim", claim.name, "custom_total_repair_cost", 9999, update_modified=False)
		file_doc = frappe.get_doc({
			"doctype": "File", "file_name": f"quality-{self.suffix}.txt",
			"content": b"quality audit fixture", "is_private": 1,
			"attached_to_doctype": "Warranty Claim", "attached_to_name": claim.name,
		}).insert(ignore_permissions=True)
		frappe.db.set_value("File", file_doc.name, "is_private", 0, update_modified=False)
		issues = get_warranty_data_quality({"company": self.vehicle.company})
		by_type = {(row["issue_type"], row["document_name"]) for row in issues}
		self.assertIn(("Sold/delivered VIN without Vehicle Warranty", uncovered_vehicle.name), by_type)
		self.assertIn(("Claim financial totals inconsistent with child rows", claim.name), by_type)
		self.assertIn(("Non-private Warranty Claim attachment", claim.name), by_type)
		self.assertEqual(frappe.db.get_value("Warranty Claim", claim.name, "custom_total_repair_cost"), 9999)
		self.assertEqual(frappe.db.get_value("File", file_doc.name, "is_private"), 0)

	def test_phase6_expiry_reminders_are_company_aware_and_idempotent(self):
		warranty = self.make_warranty()
		instant = datetime(2026, 10, 4, 9, 0, tzinfo=timezone.utc)
		local_date = get_company_local_date(self.vehicle.company, now_utc=instant)
		frappe.db.set_value("Vehicle Warranty", warranty.name, "warranty_expiry_date", add_days(local_date, 30), update_modified=False)
		email = f"reminder-{self.suffix}@example.com"
		user = frappe.get_doc({
			"doctype": "User", "email": email, "first_name": "Warranty Reminder Test",
			"enabled": 1, "user_type": "System User", "send_welcome_email": 0,
		}).insert(ignore_permissions=True)
		user.add_roles(INTERNAL_USER)
		first = send_warranty_expiry_reminders(now_utc=instant)
		second = send_warranty_expiry_reminders(now_utc=instant)
		self.assertGreaterEqual(first["created"], 1)
		self.assertEqual(second["created"], 0)
		self.assertEqual(frappe.db.count("Notification Log", {
			"for_user": email, "document_type": "Vehicle Warranty", "document_name": warranty.name,
		}), 1)

	def test_phase6_print_naming_and_provider_adversarial_access(self):
		warranty = self.make_warranty()
		claim = self.make_reporting_claim(warranty)
		self.assertTrue(warranty.name.startswith("VW-"))
		self.assertTrue(claim.name.startswith("SER-WRN-"))
		html = frappe.get_print("Vehicle Warranty", warranty.name, "Vehicle Warranty Certificate")
		self.assertIn("شهادة ضمان المركبة", html)
		self.assertNotIn("Purchase Price", html)
		self.assertNotIn("Internal Notes", html)

		provider_user, _access = self.make_provider_user()
		frappe.set_user(provider_user.name)
		self.assertFalse(frappe.has_permission("Vehicle Warranty", "read", doc=warranty))
		with self.assertRaises(frappe.PermissionError):
			frappe.get_list("Vehicle Warranty", fields=["name"], limit_page_length=1)
		with self.assertRaises(frappe.PermissionError):
			search_link("Vehicle Warranty", warranty.vin)
		with self.assertRaises((frappe.PermissionError, frappe.ValidationError)):
			run_report("Warranty Data Quality", filters={"company": self.vehicle.company})
		with self.assertRaises(frappe.PermissionError):
			preview_historical_warranties({"vin": warranty.vin})
		with self.assertRaises(frappe.PermissionError):
			get_warranty_data_quality({"company": self.vehicle.company})
		with self.assertRaises(frappe.PermissionError):
			execute_historical_backfill(vin=warranty.vin)
