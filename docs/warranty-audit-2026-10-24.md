# Vehicle Warranty Audit — 2026-10-24

Scope: repository code and the `dev.localhost` site after migration. Status reflects both the checked-out implementation and the inspected site state. `CONFIGURATION ONLY` means the required implementation exists, but the site cannot use it until business master data or user assignments are configured.

| Requirement | Status (PASS/PARTIAL/MISSING/CONFIG) | Existing implementation | Missing work |
|---|---|---|---|
| 1. Warranty Provider | PASS | Tracked `Warranty Provider` DocType with identity, supplier, contact, address, status, permissions, and server-side records. Portal-native list/detail added. | Create approved provider masters before go-live. |
| 2. Warranty Provider Branch | PASS | `Warranty Provider Branch` validates provider ownership, active provider, and provider-unique branch code. Claim validation enforces the actual provider branch. Portal-native list/detail added. | Create active branch masters. |
| 3. Warranty Provider Contract; history and open-ended terms | PASS | `Warranty Provider Contract` supports Fixed Period, Annual, and Open Ended contracts; end date is optional only for Open Ended; dated contract selection preserves historical contract links. Financial terms use permission level 1. | Create approved contracts with correct validity dates. |
| 4. Warranty Coverage Category | PASS | Tracked category DocType with Arabic name, active flag, permissions, and portal-native list/detail. | Create approved categories. |
| 5. Warranty Coverage Template with duration, mileage/financial limits, covered items, exclusions, conditions | PASS | Template validates positive duration and unique categories. Child rows contain covered flag, coverage and mileage limits, descriptions, conditions, and exclusions. Portal-native list/detail added. | Create and approve at least one active template. |
| 6. Vehicle Warranty linked to Vehicle Master/VIN with immutable issued snapshot | PASS | Vehicle Warranty links ERPNext `Serial No` VIN and `Vehicle Master`; validation rejects mismatches and does not duplicate VIN logic. Issuance copies template rows. This audit added server-side comparison that rejects any later coverage snapshot mutation, including API/import writes. | None. |
| 7. Activation source, uniqueness, expiry, renewal/replacement, override audit, scheduler | CONFIGURATION ONLY | Delivery Note submission is primary. Sales Invoice fallback requires explicit `custom_delivery_date` and skips vehicles with a Delivery Note. Sales Order and invoice posting date do not activate warranties. Unique `active_vin_key`, validation, inclusive expiry calculation, renewal links, manager-only reasoned expiry override, cancellation handling, and hourly expiry are implemented. | On `dev.localhost`, auto activation is disabled and both default provider/template are empty. Configure provider/template/contract, then enable activation after UAT. |
| 8. Historical warranty/backfill with safe preview | PASS | `Historical Warranty Backfill Preview` is read-only; execution is manager-only, rerunnable, savepoint-isolated, revalidates source dates, snapshots coverage, syncs Serial No, and writes an audit Comment. | Run preview/export and approve a controlled production batch before execution. |
| 9. Extend ERPNext Warranty Claim | PASS | ERPNext core `Warranty Claim` is extended through Custom Fields, hooks, Custom DocPerms, workflow, and child tables. No duplicate claim DocType exists. | None. |
| 10. Claim content and approval workflow | PASS | Claim extension includes VIN/warranty, Vehicle Master, provider/actual branch, complaint, inspection, diagnosis, eligibility, provider recommendation, internal decision, parts, labour/services, calculated costs, private documents, and the active 11-state workflow. Portal-native list/detail displays these fields subject to permitted fields. | Configure operational users and execute workflow UAT. |
| 11. Server-side validation and calculations | PASS | Hooks populate authoritative warranty values; validate branches/dates/coverage/internal decisions/private documents; calculate rows, VAT, repair, covered, customer-payable, and provider totals on the server. | None. |
| 12. Provider/Branch access enforced server-side | PASS | Permission query/has-permission hooks and every provider portal endpoint recheck active provider access and fixed/all-branch ownership; spoofed branches are rejected. | Create one approved `Warranty Provider User Access` per provider user. |
| 13. Provider users cannot enumerate unrelated VINs or confidential data | PASS | Provider lookup is exact-VIN and provider scoped; claim responses use an allowlist and omit internal approval/accounting fields; file downloads recheck claim/provider/branch ownership. Adversarial tests cover enumeration, cross-provider access, branch spoofing, and private files. | None. |
| 14. Warranty Provider portal/access | PASS | Existing `/warranty-provider` flow supports scoped VIN lookup, claims, workflow actions, parts/services, inspection/diagnosis, and private files. | No provider/user-access records exist on the site; configure them when external provider access is required. |
| 15. Internal Warranty Dashboard | PASS | Existing Desk dashboard/reporting service remains. This work also adds `/an-truck-portal/warranty-dashboard` with six cards and recent warranties/claims. | None. |
| 16. Reports/KPIs | PASS | Standard reports cover active/expiring warranties, claims/status, VIN/provider/branch/model/component costs, outside-warranty repairs, provider performance, and VIN history. Dashboards expose operational and financial KPIs. | Data is currently empty, so KPI acceptance needs seeded/UAT or production data. |
| 17. Warranty Data Quality audit | PASS | Read-only report detects missing/invalid links, duplicate-active symptoms, bad dates, claim branch/provider/total inconsistencies, public claim files, and unsafe provider access. | Run/export after master-data setup and before backfill. |
| 18. Bilingual Vehicle Warranty Certificate | PASS | Standard Arabic/English `Vehicle Warranty Certificate` print format exists and passes print generation tests. Portal warranty detail links to it. | Production PDF rendering must use a compatible renderer for this custom HTML format. |
| 19. Internal claim notifications | PASS | Three enabled standard System Notifications cover new provider submission, resubmission, and final documents. Their `method` values are blank, and no stale notification Python-path errors were found in Error Log. | Assign real warranty manager/user recipients; only Administrator currently has the roles. |
| 20. Company-aware 30-day/7-day expiry reminders | PASS | Hourly idempotent scheduler computes company-local dates, respects Company User Permissions, and creates internal 30/7-day Notification Logs. Main company `alnagi` uses `Asia/Riyadh`. | Configure `custom_warranty_timezone` for any additional operating company before issuing its warranties. |
| 21. Audit trail and security controls | PASS | Tracked changes on warranty masters, Version tracking on Warranty Claim, immutable issued snapshot, manager-only approval/override fields, protected claim deletion, private-file enforcement, User Permissions, provider scope, and audit comments are present. | Review production role assignments and least privilege before go-live. |
| 22. Arabic and English translations | PASS | Backend Arabic catalogue covers warranty labels/messages; portal now includes Arabic/English navigation, filters, dashboard, warranty, claim, cost, coverage, and document labels with RTL support. | Linguistic/business review is recommended before production. |
| 23. No ERPNext core changes | PASS | Warranty implementation is confined to `an_truck` and `an_truck_portal`; ERPNext is extended by hooks/custom fields/permissions/workflow. | None. |
| 24. Reuse ERPNext/Frappe functionality | PASS | Reuses Serial No, Vehicle, Warranty Claim, Delivery Note, Sales Invoice, Workflow, Notification, Print Format, Script Report, User Permission, File, Version, scheduler, and Frappe permission APIs. | None. |

## Portal work completed

- Added permission-filtered `Warranty / الضمان` navigation for dashboard, warranties, claims, providers, branches, contracts, templates, and categories.
- Added portal-native Vehicle Warranty search/filter/list/detail views, coverage snapshot, related claims, and certificate link.
- Added portal-native Warranty Claim search/filter/list/detail views for complaint, inspection, diagnosis, eligibility/decision, parts, services, costs, private documents, and status.
- Added portal-native master-data list/detail views. Financial contract fields remain governed by Frappe permitted fields.
- Added dashboard cards for active, 30-day, 7-day, expired, open, and awaiting-approval counts plus recent records.
- The portal APIs require portal entry plus the relevant DocType permissions, honor Company permissions, reject provider-mode users, and expose explicit field allowlists.

## Inspected site state

- Migration completed successfully; all five warranty patches are recorded and reporting/security indexes exist.
- Scheduler is enabled.
- Warranty Claim workflow and all three standard claim notifications are active.
- Counts are zero for providers, branches, contracts, categories, templates, warranties, claims, and provider access records.
- Auto activation is disabled; default provider and template are unset.
- Administrator is the only user assigned each of `AN Truck Warranty Manager`, `AN Truck Warranty User`, `AN Truck Warranty Provider User`, and `AN Truck Portal User`.
- `alnagi` has warranty timezone `Asia/Riyadh`; non-operating test/sample companies are mostly unset.

## Verification

- `bench --site dev.localhost migrate --skip-search-index`: passed.
- Warranty API smoke tests for dashboard, warranties, claims, and providers: passed on the empty live dataset.
- `bench --site dev.localhost run-tests --app an_truck --module an_truck.tests.test_warranty`: 15/15 passed after the changes.
- Vite production build: passed (88 modules).
- Ruff checks for changed Python implementation: passed.
- A focused Chromium run against `dev.localhost:8000/an-truck-portal` passed all eight Warranty sidebar routes, seven fixture detail routes, dashboard data, claim status/costs, immutable snapshot presentation, bilingual certificate content, Arabic RTL/English LTR switching, mobile menu/overflow, Vehicle Master warranty status, permission-aware navigation, unauthorized API denial, and cross-provider record denial with no console errors.
- Verification found and fixed two integration defects: Frappe v16 rejected a SQL aggregate string used for warranty mileage, and Vehicle Master rows did not supply the warranty context expected by their drawer.
- The controlled Delivery Note activation ran inside a database savepoint and was rolled back. Global automatic activation remained disabled with default provider/template unset.
- All prefixed verification records and temporary users were deleted in dependency order; the post-cleanup audit reported zero residue across every fixture DocType.
- The existing broad browser regression harness still times out on the unrelated `+ New Customer` flow. It did not block the focused Warranty browser run, so it was not changed.
