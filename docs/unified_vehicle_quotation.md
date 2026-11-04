# Unified vehicle quotations

The authoritative document is standard ERPNext **Quotation**. No second sales,
stock, pricing or accounting engine is introduced. The format is named
**AN Truck - Unified Vehicle Quotation** and uses Frappe's standard Chrome PDF
generator. It is offered in Desk and preselected by the portal print dialog.

## Data and field mapping

| Document | Fields | Behavior |
| --- | --- | --- |
| Vehicle Master | `specification_template` | Existing Link, now optional for new vehicles as well as existing ones. VIN, serial, operational and transaction fields are untouched. |
| Purchase Receipt Item | `custom_vehicle_specification_template` | Existing optional Link. Stock, import-file and VIN quantity/uniqueness checks remain. |
| Quotation Item | `custom_vehicle_specification_template` | Optional Link to a specific published revision, independent for every item. An explicitly associated Item must match; unassociated templates must match the Item code/name through their model. |
| Quotation Item | `custom_vehicle_warranty_terms`, `custom_vehicle_delivery_terms` | Quotation-specific text. Empty warranty uses that revision's approved template text. No hardcoded model warranty or invented warranty coverage. |
| Quotation Item | `custom_vehicle_quotation_snapshot` | Hidden, read-only, no-copy JSON containing the resolved revision, configuration, sections, bilingual labels, images and commercial terms. Server-generated; client JSON is ignored. |
| Quotation | `custom_company_bank_account` | Optional standard Bank Account Link, checked for company ownership, enabled status, company-account classification and read permission. |
| Quotation | `custom_vehicle_quotation_context` | Hidden, read-only, no-copy JSON recording bank details, company contact details, and available Customer CR/VAT/mobile at save/submission. |
| Quotation | `custom_vehicle_quotation_notes` | Portal Notes. Quotation has no standard `remarks` database field; existing invoice/order Notes retain their mapping. |
| Vehicle Specification Template | `model_name_ar`, `model_name_en` | Optional display names. |
| Vehicle Specification Template | `configuration_of`, `configuration_name` | Optional published base revision and configuration name. Each configuration is a complete, independently published template with its own specifications/images, using the same Item as its base. |
| Vehicle Specification Template | `main_vehicle_photo`, `technical_photo`, `cabin_photo` | Managed image File references, never external mutable URLs. |
| Vehicle Specification Template | `technical_highlights`, `quotation_warranty_terms` | Optional highlights and approved model-specific warranty text, frozen with publication. |
| File | Existing attached image records | Additional technical photographs. New revisions reuse File references without copying image bytes. Portal uploads, previews and removes draft photographs through standard File permissions. |

Customer commercial registration reuses `an_truck.portal_parties._commercial_registration`
and the installed Additional Buyer IDs CRN mechanism. No duplicate Customer field
is created. Addresses use the Quotation's normal saved address display, never an
overwrite of historical address snapshots.
Optional company/customer extras are omitted when unreadable; this does not add
party-read requirements to unrelated standard Quotation creation workflows.

## Workflow and historical accuracy

- New receipts, vehicle creation and edits no longer require a specification template.
  The receipt's unsupported `frappe.has_role` call was replaced with the equivalent
  membership check against `frappe.get_roles()`. Its existing expected-quantity
  restriction and System Manager exception are unchanged.
- Quotations can use Item/quantity/rate without a vehicle or VIN. Selecting a VIN
  fills its template only when no template was explicitly selected. No vehicle is saved.
- High/Low Cab or another configuration is selected by its own published revision
  in the same searchable template selector. Configurations never silently change a rate.
- The portal reuses its existing create popup and sales APIs, adds draft editing,
  price-list/tax/bank selectors, per-line terms and read-only specification previews.
  Draft edits include a modified timestamp to detect concurrent changes.
- Price lookups use ERPNext `get_item_details`; totals, pricing rules, discounts and
  tax calculations remain ERPNext's. VAT is printed from actual tax rows, never 15% by assumption.
- Draft save/submission generates snapshots on the server. Published revisions are
  immutable, so a normal draft save cannot pick up altered technical values. An
  explicit, confirmed refresh is available in both Desk and Portal.
  Desk asks users to save unsaved edits first so refresh cannot discard them.
- Submitted and cancelled quotation prints read their saved JSON only. They never
  infer new specifications from a current vehicle/template. Preexisting submitted
  quotations without snapshots retain their commercial content and get no invented
  technical pages. Use normal ERPNext cancellation/amendment to change approved specs.
- One commercial section presents all items. Technical sections are deduplicated
  by revision/configuration. Content can continue onto additional A4 pages; no
  fixed-height clipping is used. Empty specification values and unit-only defaults
  are omitted. Warranty and delivery terms remain tied to their individual lines.
- A cooperative `extend_doctype_class` File mixin guards published assets **before**
  core File methods can move/delete bytes. Other File mixins, warranty validation,
  and normal permissions continue running. A draft revision's duplicate File link
  may be removed when a protected published File with the same hash retains the bytes.

## Setup and deployment

On dev.localhost, only the template DocType was reloaded and the idempotent
`an_truck.patches.v1_0.setup_vehicle_quotation.execute` setup was applied directly.
The new print format was refreshed during development. No full migration was run.

For another site, deploy both apps and run the normal versioned migration:

```sh
bench --site <site> migrate
```

The migration creates the fields and the new print format when absent. It does
not replace a preexisting same-name print format, update vehicles, or rewrite
quotations. Portal compiled assets/manifest are included in the change. To rebuild
them from source when needed:

```sh
npm --prefix apps/an_truck_portal/frontend run build
```

Administrators must configure real published model/configuration templates, their
actual photographs and approved warranty text, standard selling prices/taxes,
company contact details and optional Bank Accounts. The supplied KC/H7 HTML files
are design references; their hardcoded bank numbers, prices and warranty promises
are not imported into business records. No model sample records remain.

## Focused verification

- `an_truck.tests.test_vehicle_quotation`: receipt without template, quotation
  without VIN, both reference model names in the same format, High/Low Cab isolation,
  standard 7% tax arithmetic, portal draft editing, Item/model compatibility,
  company/reader checks, manual-vs-inferred template selection, VIN/engine identity,
  submitted snapshot persistence, protected image bytes and revision attachments,
  and actual standard Chrome A4 PDF generation.
- `an_truck.tests.test_vehicle_specification_templates`: published revisions,
  read compatibility, linked vehicles and company/user permissions.
- `an_truck.tests.test_vehicle_master_specs`: schema and translations.
- `frontend/tests/vehicle-quotation.browser.cjs`: real portal create/save/reopen,
  manual-rate preservation, print selection, Arabic/mobile RTL and Desk fields/
  refresh action. It deletes only its uniquely marked draft using standard deletion.
- Stock/sales/warranty checks remain focused on the existing service test modules;
  no real stock, purchasing, delivery, warranty or accounting transactions are posted.

Tests roll back their temporary templates, vehicles, serials and quotations.
The PDF/HTML and mobile screenshots used for review are temporary `/tmp` artifacts.
Actual customer-specific bank/warranty approval and final populated model artwork
remain business configuration, not assumptions made by this implementation.

Final focused results on dev.localhost: **26 Python tests passed** (10 quotation,
7 templates, 4 schema/translation, 3 service and 2 selected invoice/delivery warranty
tests). The live browser check passed with no page errors. Standard Chrome produced
three A4 pages for two models (commercial/signatures on page one and one technical
page per model); the 90-row technical test continued to extra pages and retained
its final row. Portal Vite build passed with the existing large-bundle advisory.
No uniquely marked UI-test quotations, quotation-template fixtures or test vehicles
remain. No commit or push was performed.

## Changed source files

Under `apps/an_truck`:

- `an_truck/vehicle_quotation.py`
- `an_truck/public/js/vehicle_quotation.js`
- `an_truck/print_formats/unified_vehicle_quotation.html`
- `an_truck/patches/v1_0/setup_vehicle_quotation.py`
- `an_truck/patches.txt`, `an_truck/hooks.py`
- `an_truck/an_truck/doctype/vehicle_master/vehicle_master.py` and `.js`
- `an_truck/an_truck/doctype/vehicle_specification_template/vehicle_specification_template.py` and `.json`
- `an_truck/services.py`, `an_truck/transactions.py`
- `an_truck/translations/ar.csv`
- `an_truck/tests/test_vehicle_quotation.py`
- `an_truck/tests/test_vehicle_specification_templates.py`
- `docs/vehicle_specification_templates.md`, this document

Under `apps/an_truck_portal`:

- `an_truck_portal/api/vehicle_quotation.py`, `api/sales.py`, `api/specifications.py`, `api/dashboard.py`
- `frontend/src/components/SalesDocumentDialog.vue`
- `frontend/src/views/SalesDocumentDetail.vue`, `ImportWorkspace.vue`, `SpecificationTemplates.vue`
- `frontend/src/locales/ar.json` and `en.json`
- `frontend/tests/vehicle-quotation.browser.cjs`
- `an_truck_portal/public/frontend/manifest.json` and its generated JS/CSS assets
