# AN Truck — Codex Handoff

> Attach this single file to the new Codex conversation and say:  
> **“Read this handoff completely, then inspect the current `apps/an_truck` working tree before making changes. Preserve existing behavior and do not modify ERPNext or Frappe core.”**

## 1. Project location and current baseline

- Bench: `/home/nagi/my-bench`
- App repository: `/home/nagi/my-bench/apps/an_truck`
- Development site: `dev.localhost`
- Branch: `version-16`
- Framework: Frappe/ERPNext version 16
- Latest known commits at handoff creation:
  - `4df247a fix: use import title for vehicle import naming`
  - `712d3e3 fix: simplify vehicle master list filters`
  - `e03f183 feat: add warranty management and vehicle specifications`
- Never assume the working tree is still clean. Start every task with `git status --short` and preserve unrelated user changes.
- Do not commit or push unless the user explicitly asks.

## 2. What AN Truck does

AN Truck manages the complete truck lifecycle around standard ERPNext documents:

1. Import/contract tracking.
2. Purchasing and receiving.
3. VIN/Serial Number creation and Vehicle Master creation.
4. Landed cost and final vehicle valuation.
5. Quotation, reservation, sale, and physical delivery.
6. Vehicle registration.
7. Warranty activation, provider claims, approvals, repair costs, reporting, and provider portal access.

ERPNext remains the owner of standard accounting, stock, buying, selling, Item, Serial No, Customer, Vehicle, and Warranty Claim documents. AN Truck integrates through hooks, custom fields, child DocTypes, reports, pages, and server-side validations. No Frappe or ERPNext core source files should be modified.

## 3. Main business flow

### 3.1 Import and purchasing

The designed starting point is **Vehicle Import File**, not Purchase Invoice.

```text
Vehicle Import File
  -> Purchase Order
  -> Purchase Receipt + VIN entry
  -> automatic Vehicle Master creation
  -> Purchase Invoice
  -> Supplier Payment
  -> Landed Cost Voucher
  -> refreshed final vehicle valuation
```

Important behavior:

- `Vehicle Import File` is the common operational reference for purchase and sales documents.
- A vehicle Purchase Receipt normally requires a Vehicle Import File, depending on AN Truck Settings.
- Purchase Receipt VIN count must equal received vehicle quantity.
- VINs must be unique and belong to the correct serialized Item.
- Submitting Purchase Receipt creates or re-enables one Vehicle Master per VIN when automatic creation is enabled.
- Cancelling a receipt disables its Vehicle Masters unless a vehicle has already moved to a downstream status such as Reserved, Sold, Delivered, or Under Maintenance.
- Purchase Invoice can be generated from Purchase Order or Purchase Receipt in the unified transaction API.
- Landed Cost Voucher changes refresh Vehicle Master landed cost and final valuation.

Primary code:

- `an_truck/services.py`
- `an_truck/transactions.py`
- `an_truck/an_truck/doctype/vehicle_import_file/`
- `an_truck/public/js/vehicle_import_file.js`

### 3.2 Sales and delivery

```text
Customer Quotation (optional)
  -> Sales Order
  -> Delivery Note
  -> Sales Invoice
  -> Customer Payment
```

Status behavior:

- Submitted Sales Order reserves the linked Vehicle Master and stores customer, order, and selling rate.
- Cancelling the order releases the vehicle only if no delivery or invoice has followed.
- Submitted Delivery Note sets the vehicle to Delivered and is the primary physical-delivery event.
- Submitted Sales Invoice records the customer, invoice, and selling rate; it marks the vehicle Sold unless it is already Delivered.
- Cancellation handlers restore the safest earlier status based on remaining links.
- VIN is the primary vehicle tracking key throughout the flow.

### 3.3 Warranty activation

Primary path:

```text
Submitted Delivery Note
  -> Vehicle Warranty created
  -> coverage snapshot stored
  -> Serial No expiry synchronized
```

Sales Invoice is only a fallback when:

- no Delivery Note exists for the vehicle; and
- Sales Invoice contains an explicit delivery date.

Warranty activation is idempotent. It must not create duplicate active warranties for the same delivery event.

## 4. Vehicle Master

There is exactly one existing `Vehicle Master` DocType. Do not create another vehicle or specification master.

### 4.1 Existing data compatibility

Important reused fields include:

- `vin`, with hidden compatibility field `chassis_number`
- `item_code`, `item_name`
- `brand`, `model`, `model_year`, `color`
- `engine_number`, `engine_type`, `transmission`, `fuel_type`
- manufacturing/country/photo/specification attachment
- import file, supplier, purchase order/receipt, warehouse, receipt date, company
- purchase valuation, landed cost, final valuation, and currency
- customer, quotation, sales order/invoice, delivery note, and selling rate

Do not rename or remove these without searching all dependencies first.

### 4.2 Technical sections

Vehicle Master is organized into:

1. Vehicle Identity
2. Chassis Dimensions
3. Weights & Capacity
4. Engine Specifications
5. Transmission / Gearbox
6. Clutch
7. Braking System
8. Cabin Specifications
9. Axles
10. Tyres
11. Suspension
12. Fuel Tank
13. Fifth Wheel / Coupling
14. Additional Technical Specifications
15. Registration
16. Import & Purchasing References
17. Cost Information
18. Sales & Warranty
19. Notes

Secondary sections are collapsible. Rare manufacturer-specific values belong in the `Vehicle Technical Specification` child table with Category, Name, Value, UOM, and Notes. Important searchable/reportable specifications remain normal Vehicle Master fields.

### 4.3 Current list/search behavior

Standard filters are intentionally limited to:

- VIN / Chassis Number
- Item Name, translated as **اسم السيارة**
- Vehicle Status
- Plate Number
- Vehicle Import File
- Supplier
- Customer

The internal document `ID/name` is hidden from both the standard search area and list columns. VIN is the title/subject column and opens the record.

Relevant files:

- `an_truck/an_truck/doctype/vehicle_master/vehicle_master.json`
- `an_truck/an_truck/doctype/vehicle_master/vehicle_master.py`
- `an_truck/an_truck/doctype/vehicle_master/vehicle_master_list.js`
- `an_truck/an_truck/doctype/vehicle_master/vehicle_master_dashboard.py`
- `an_truck/public/js/vehicle_master_warranty.js`
- `an_truck/tests/test_vehicle_master_specs.py`

### 4.4 Costing

Do not change the existing costing rules casually:

- Purchase valuation is taken from Purchase Receipt Item base rates.
- Landed cost is allocated per received stock quantity.
- `final_valuation_rate = purchase_valuation_rate + landed_cost_added`.
- Cost fields are refreshed before save and after landed-cost changes.

## 5. Warranty domain model

Main custom DocTypes:

- Vehicle Warranty
- Vehicle Warranty Coverage Item
- Warranty Coverage Category
- Warranty Coverage Template
- Warranty Coverage Item
- Warranty Provider
- Warranty Provider Branch
- Warranty Provider Contract
- Warranty Provider User Access
- Warranty Claim Part
- Warranty Claim Service
- Warranty Claim Document

ERPNext `Warranty Claim` is extended with custom fields rather than replaced.

### 5.1 Setup hierarchy

```text
Coverage Categories
  -> Coverage Template + rows

Warranty Provider
  -> Provider Branches
  -> Provider Contract

AN Truck Settings or Item override
  -> default Provider + Coverage Template
```

An issued Vehicle Warranty stores a coverage snapshot. Later template changes must not rewrite historical warranties.

### 5.2 Provider branch rule

- Provider-created claims require the actual provider branch once leaving Draft.
- Server validation confirms the branch is active and belongs to the claim provider.
- Fixed-branch portal users are forced to their assigned branch.
- All-Branches provider managers may select only active branches belonging to their provider.
- Branch remains available for claim-count and warranty-cost reporting.

### 5.3 Claim workflow

```text
Draft
  -> Submitted by Provider
  -> Under Internal Review
  -> Need More Information -> Submitted by Provider
  -> Approved / Partially Approved / Rejected
  -> Repair In Progress
  -> Repair Completed
  -> Final Documents Submitted
  -> Closed
```

Internal approval fields use permission level 1. Provider users must never receive internal approval notes, confidential notes, buying information, margins, or unrestricted reports.

### 5.4 Cost calculation

- Parts and services are classified Inside Warranty or Outside Warranty.
- Server validation recalculates row totals and authoritative claim totals.
- Covered rows feed Warranty Covered Amount and Provider Claim Amount.
- Outside-warranty rows feed Customer Payable Amount.
- VAT/invoice and approved settlement information are stored on the claim.
- Dashboard, portal, reports, and VIN history read stored server-calculated totals.

Primary warranty code:

- `an_truck/warranty/access.py`
- `an_truck/warranty/activation.py`
- `an_truck/warranty/claim.py`
- `an_truck/warranty/portal_api.py`
- `an_truck/warranty/reporting.py`
- `an_truck/warranty/tasks.py`
- `an_truck/warranty/timezone.py`
- `an_truck/warranty/backfill.py`
- `an_truck/warranty/quality.py`
- `an_truck/warranty/setup.py`

## 6. Warranty provider portal

- Route: `/warranty-provider`
- Role: `AN Truck Warranty Provider User`
- Access is controlled by one active Warranty Provider User Access record.
- Portal supports exact VIN lookup, provider-scoped claims, inspection/diagnosis, parts/services, allowed workflow actions, and private document upload/download.
- Attachments must be private.
- Portal upload allowlist: PDF, PNG, JPG/JPEG, WebP, maximum 10 MB.
- Download always revalidates provider and branch ownership.

Files:

- `an_truck/www/warranty-provider.html`
- `an_truck/www/warranty_provider.py`
- `an_truck/public/js/warranty_provider_portal.js`
- `an_truck/public/css/warranty_provider.css`

## 7. Warranty reports and controls

Implemented reports/dashboard cover:

- Active and expiring warranties
- Warranty claims
- Cost by VIN, provider, branch, vehicle model, and component
- Outside-warranty repairs
- Provider performance
- Complete warranty/claim history by VIN
- Historical Warranty Backfill Preview
- Warranty Data Quality

Backfill is controlled and idempotent. It accepts only a submitted linked Delivery Note posting date or an explicit linked Sales Invoice delivery date; it never invents a date. Data Quality is read-only and does not silently repair ambiguous business data.

## 8. Timezone behavior

- Do not change the global site timezone for this module.
- Each Company has a Warranty Processing Time Zone.
- Saudi operations use `Asia/Riyadh`.
- Warranty start/expiry uses date-only Frappe values, never browser timezone.
- Warranty stays active through its expiry date and expires only when the company-local date becomes later.
- The hourly scheduler expires warranties and creates idempotent internal 30-day/7-day reminders.

## 9. Roles

- `System Manager`: full administration and controlled backfill.
- `AN Truck Manager`: general truck operations and visibility.
- `AN Truck Import User`: import and buying operations.
- `AN Truck Receiving User`: receipt/VIN operations.
- `AN Truck Viewer`: read-only operational visibility.
- `AN Truck Warranty Manager`: warranty administration, internal approvals, reports, quality, and backfill.
- `AN Truck Warranty User`: internal warranty operations without manager-only approval access.
- `AN Truck Warranty Provider User`: website-only, provider/branch scoped.

Company User Permissions additionally restrict internal reporting.

## 10. Custom ERPNext links

Fixtures/patches add `custom_vehicle_import_file` to purchasing, stock, payment, quotation, and sales documents. Transaction item rows carry:

- `custom_vehicle_master`
- `custom_vin`
- `custom_vehicle_import_file`

ERPNext Vehicle is extended with Vehicle Import File, Vehicle Master, VIN, and registration status links. Item is extended with default Warranty Provider and Coverage Template. Warranty Claim receives the warranty, provider/branch, inspection, assessment, approval, parts/services, cost, document, and workflow fields.

These are custom fields. Do not edit ERPNext JSON/Python files directly.

## 11. Arabic translations

Translations are maintained directly in:

`an_truck/translations/ar.csv`

Every new visible field, section, action, workflow label, report label, and validation message should receive an Arabic translation. Avoid duplicate/conflicting CSV source keys. Existing vehicle terminology was deliberately standardized, including رقم الشاسيه, اسم السيارة, حالة المركبة, رقم اللوحة, ملف استيراد المركبة, المورد, and العميل.

## 12. Important routes

- Main operational page: `/app/an-truck-portal`
- Vehicle Import Files: `/app/vehicle-import-file`
- Vehicle Masters: `/app/vehicle-master`
- Warranty Dashboard: `/app/warranty-dashboard`
- Provider portal: `/warranty-provider`

## 13. Known UI audit notes

Verify these points before assuming the UI is complete:

1. `an_truck/public/js/vehicle_import_file.js` defines dialogs for creating Purchase Order, Purchase Receipt, Purchase Invoice, payments, landed cost, sales documents, vehicle completion, and inspection. At the time of this handoff, its `refresh` handler visibly adds only **Refresh Totals**; search for actual callers before changing anything. The dialog functions may need explicit action-button wiring.
2. `an_truck/portal.py` returns sidebar items and action definitions, while `an_truck/an_truck/page/an_truck_portal/an_truck_portal.js` currently renders the overview/KPI cards. Confirm whether another layer renders actions; otherwise the operational page may not expose all intended shortcuts.
3. Treat these as audit observations, not permission to redesign. Reproduce in the browser and obtain user direction before broad UI changes.

## 14. Tests and verification

Main test modules:

- `an_truck/tests/test_services.py`
- `an_truck/tests/test_vehicle_master_specs.py`
- `an_truck/tests/test_warranty.py`
- `an_truck/an_truck/doctype/vehicle_master/test_vehicle_master.py`
- vehicle profit report tests

Common commands from `/home/nagi/my-bench`:

```bash
bench --site dev.localhost migrate
bench build --app an_truck
bench --site dev.localhost clear-cache
bench --site dev.localhost clear-website-cache
bench --site dev.localhost run-tests --app an_truck
```

Before handoff, the complete app suite had passed after the warranty/Vehicle Master implementation. The focused Vehicle Master suite currently contains five passing integration tests. Always rerun tests after new edits; do not rely only on this historical result.

Also verify:

```bash
git -C apps/an_truck diff --check
git -C apps/frappe status --porcelain
git -C apps/erpnext status --porcelain
```

Frappe and ERPNext should remain clean.

## 15. Safe working rules for the next Codex session

1. Read this file completely.
2. Run `git status --short` before editing.
3. Read the exact attached/user request; do not infer authorization for unrelated changes.
4. Search dependencies with `rg` before renaming/removing fields.
5. Preserve VIN, import, costing, sales, delivery, warranty, Arabic, and portal behavior.
6. Use `apply_patch` for manual file edits.
7. Run JSON/Python/JavaScript validation proportional to the change.
8. Run focused tests, then the full app suite for cross-flow changes.
9. Run migrate/build/cache clearing when schema/assets/translations change.
10. Verify no core files changed.
11. Do not commit or push unless explicitly requested.
12. Report any unrelated dirty files instead of overwriting them.

## 16. Suggested opening prompt for the new account

```text
This repository is a Frappe/ERPNext v16 bench. Read the attached
AN_TRUCK_CODEX_HANDOFF.md completely, then inspect /home/nagi/my-bench/apps/an_truck.
Start with git status and verify the current code rather than assuming the handoff
is perfectly current. Preserve unrelated changes. Do not modify Frappe/ERPNext core,
do not commit or push unless I explicitly ask, and run relevant tests after changes.
My next request is: [WRITE THE NEW TASK HERE]
```

