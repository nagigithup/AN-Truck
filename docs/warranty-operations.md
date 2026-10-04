# Vehicle Warranty Operations

## Architecture and lifecycle

AN Truck owns the warranty extension while ERPNext continues to own sales, delivery, Serial No, Item, Customer, and the core Warranty Claim DocType. No Frappe or ERPNext source file is modified. Vehicle Warranty is the issued, immutable coverage snapshot for one VIN. A claim links the warranty, Vehicle Master, provider, and actual provider branch, then follows the controlled workflow.

The normal lifecycle is `Delivery -> Active Vehicle Warranty -> Claim -> Inspection -> Internal Decision -> Repair -> Final Documents -> Closed`. Expiry is company-local and date-only. A warranty remains active through its expiry date. Renewal creates a new Vehicle Warranty linked through `renewal_of`; the earlier record and its claims remain historical.

## Initial setup

1. Create active Warranty Coverage Categories and a Warranty Coverage Template. Set duration, coverage, limits, conditions, and exclusions carefully; an issued warranty receives a snapshot and later template edits do not rewrite history.
2. Create an active Warranty Provider and its active branches. Branch is mandatory once a provider claim leaves Draft and must belong to the claim provider.
3. Create an active Warranty Provider Contract whose provider and validity period cover the intended warranty start date.
4. In AN Truck Settings, enable automatic activation and set a default provider/template. Item-level `custom_warranty_provider` and `custom_warranty_coverage_template` override the defaults.
5. Set each operating Company's Warranty Processing Time Zone. Saudi operations use `Asia/Riyadh`. The global site timezone is deliberately unchanged.

## Activation and expiry

A submitted Delivery Note activates from its posting date. A submitted Sales Invoice is a fallback only when it contains an explicit `custom_delivery_date` and the vehicle has no Delivery Note. Calculations use Frappe Date values, not browser timestamps. The duration end is inclusive, so a two-year warranty starting 2026-10-01 expires 2028-09-30. The active expiry is synchronized to Serial No.

The hourly scheduler expires records only after the applicable Company's local date passes the expiry date. It also produces one internal Notification Log per recipient, warranty, expiry date, and 30/7-day milestone. It never contacts customers.

## Provider users and portal

Create a Website User with role `AN Truck Warranty Provider User`, then create one active Warranty Provider User Access. A fixed-branch access record forces its branch server-side. An All Branches record permits selection only among active branches owned by that provider.

The `/warranty-provider` portal offers exact-VIN lookup, provider/branch-scoped claim lists, inspection and diagnosis, parts/services, private supporting files, and allowed workflow actions. It does not expose internal approval notes, approved settlement fields, buying/cost/margin data, other providers' data, or generic internal reports.

## Claim workflow and costs

The workflow is:

`Draft -> Submitted by Provider -> Under Internal Review -> Need More Information -> Submitted by Provider`, or internal `Approved / Partially Approved / Rejected`; approved claims continue through `Repair In Progress -> Repair Completed -> Final Documents Submitted -> Closed`.

Warranty managers control internal decisions, notes, approved provider amount, and closure. Every part and service is classified Inside Warranty or Outside Warranty. Server validation calculates row totals and the authoritative claim totals. Covered rows feed Warranty Covered and Provider Claim Amount; outside rows feed Customer Payable. Portal, dashboard, reports, and VIN history all read those stored server-calculated totals.

All Warranty Claim attachments must be private. Portal uploads are allowlisted to PDF and common image formats, size-limited, and downloaded only after provider/branch ownership is rechecked.

## Reporting and controls

The internal Warranty Dashboard and reports cover active/expiring warranties, claims, VIN/provider/branch/model/component cost, outside-warranty repairs, provider performance, and VIN history. Company User Permissions are applied server-side. Provider portal users are rejected by internal report and dashboard methods.

`Historical Warranty Backfill Preview` is a dry run. It never guesses a date: it accepts a submitted linked Delivery Note posting date, otherwise a submitted linked Sales Invoice's explicit Delivery Date. Review/export results first. Only Warranty Manager/System Manager can execute READY rows. Execution reruns validation, uses record savepoints, is idempotent, snapshots coverage, synchronizes Serial No, and adds an audit Comment. Existing sales documents are read, never changed.

`Warranty Data Quality` is read-only. It identifies missing warranties, invalid VIN/vehicle/customer/provider/contract/coverage links, duplicate-active symptoms, invalid dates, claim provider/branch/link/total discrepancies, public claim files, and unsafe provider access records. Correct business data manually after source evidence is approved; the report intentionally performs no repair.

## Roles and security

- System Manager: full administration and controlled backfill execution.
- AN Truck Manager: read/report visibility; not a warranty approval substitute.
- AN Truck Warranty Manager: warranty administration, internal approval, reports, quality review, and backfill execution.
- AN Truck Warranty User: internal warranty operations and reporting without manager-only approval fields/actions.
- AN Truck Warranty Provider User: website portal only, scoped to one provider and optionally one branch.

Company User Permissions further restrict internal reporting/backfill/quality. Provider users have no Vehicle Warranty DocPerm, no internal report access, and all portal APIs reapply provider and branch checks. Direct File access is not used by the portal; the download endpoint requires a private file attached to an accessible claim.

## Troubleshooting

- No automatic warranty: verify auto-activation, VIN/Vehicle Master/customer/company, Item/default provider/template, active template, and an active contract valid on the delivery date.
- Backfill says MISSING DELIVERY DATE: link a trustworthy submitted delivery document after business review; never populate an invented date.
- Provider cannot claim: verify provider access, active provider/branch/contract, warranty status/expiry, and exact provider ownership.
- Wrong expiry: verify Company Warranty Processing Time Zone and template duration; do not change the global site timezone for this module.
- Totals differ: save the claim to run server calculation, then use Warranty Data Quality to find direct/database tampering.
- File rejected: attach it privately; portal uploads accept PDF, PNG, JPG/JPEG, and WebP up to 10 MB.
- Scheduler concern: verify scheduler status and inspect Error Log plus Notification Log; rerunning reminders is safe because milestone notifications are idempotent.

See [warranty-uat-checklist.md](warranty-uat-checklist.md) and [warranty-production-deployment.md](warranty-production-deployment.md).
