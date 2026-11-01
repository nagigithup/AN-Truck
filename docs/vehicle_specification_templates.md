# Vehicle specification templates

Vehicle Master stores `specification_template`, a Link to one specific Vehicle
Specification Template revision. New Vehicle Masters require an active published
revision. Existing vehicles may retain an empty link. No migration assigns links,
saves vehicles, renames VINs, or updates transaction records.

Shared fieldnames were moved from Vehicle Master into Vehicle Specification
Template. `country_of_origin` is represented as `default_country_of_origin` on
the template. `engine_number`, color, actual manufacturing date, vehicle photo,
registration, stock, purchasing, sales, and costing fields remain on Vehicle
Master. `specification_exceptions` holds individual exceptions.

Publish a completed draft before receiving new vehicles. Published specification
values and additional-specification rows are immutable, including for managers.
Use **Create New Revision** to produce an editable draft. Deactivation prevents
new selection while existing links remain readable. Published revisions cannot
be deleted or renamed. Changing a vehicle's revision requires confirmation in
both interfaces and is blocked after invoicing, delivery, or warranty issuance.

Purchase Receipt Item uses `custom_vehicle_specification_template`. Receiving
copies only this reference to a newly created Vehicle Master. Re-receipt retains
an existing vehicle's original revision. The normal ERPNext stock and serial
workflows continue to own stock movements.

## Migration and rollout

1. Take the normal site/database backup before deployment.
2. Deploy both applications together.
3. Run `bench --site <site> migrate`.
4. Run `npm run build` in `apps/an_truck_portal/frontend` if frontend assets were
   not already built in the release.
5. Create and publish templates manually. Choose them during receipt or manual
   vehicle creation. No sample templates or automatic vehicle backfill are installed.

The pre-model-sync patch audits every removed shared field and the old child
table. If any values exist, it saves and verifies a private compressed JSON
archive before continuing. The archive contains the existing VIN/name, legacy
specification values, and technical-specification child rows. Its name starts
with `vehicle-specifications-before-template-migration-` and it is available to
authorized administrators in Files. Migration stops if the archive cannot be
saved or verified. Retries reuse the same archive for unchanged data. This
replaces the earlier behavior that blocked migration on populated fields.

The default capacity unit `kg` alone does not require an archive. A non-default
unit is included in the archive with all other legacy specification values.
There is no automatic assignment of templates or conversion of existing vehicles.

Frappe removes the old fields from DocType metadata but retains their physical
database columns. No `DROP COLUMN`, document deletion, stock transaction, or mass
update is performed. Existing transaction snapshots are not overwritten.

## Read compatibility and linked vehicles

Existing document consumers may read `vehicle.model`, `vehicle.brand`,
`vehicle.get("model")`, `vehicle.country_of_origin`, and
`vehicle.technical_specifications` through the read layer. These values are
resolved at read time and never persisted back to Vehicle Master. Use
`get_specification_values` or `resolve_vehicle_rows` for new integrations.
Direct SQL querying the retained old columns does not resolve template values;
SQL reports must join `Vehicle Specification Template` through
`specification_template`, as the vehicle profit report does.

The **View Linked Vehicles** count/table queries Vehicle Master directly by
`specification_template`. Search, status/company filters, and pagination run on
the server. Rows and counts use Frappe's permission-aware `get_list`. A compound
index covers template/company/status, and a unique constraint protects revision
numbers. There is no linked-vehicles child table or background synchronization.

## Focused verification

- `an_truck.tests.test_vehicle_specification_templates`
- `an_truck.tests.test_vehicle_master_specs`
- `an_truck.tests.test_services`
- Warranty delivery activation and invoice-context tests in `test_warranty`
- `frontend/tests/vehicle-specifications.browser.cjs`

Integration fixtures are transactionally rolled back. The browser test uses
the real dev site, its metadata and vehicle detail APIs; saved-template/linked
vehicle responses are fixtures so it does not save test documents. It covers
the Desk modal, portal pagination/search/status, vehicle navigation, English,
Arabic RTL, and a mobile viewport. It does not post stock/accounting documents.

## Files changed for this feature

In `an_truck`:

- `an_truck/an_truck/doctype/vehicle_specification_template/`: new JSON,
  controller, Desk script, and package initializer.
- `an_truck/an_truck/doctype/vehicle_master/vehicle_master.{json,py,js}`.
- `an_truck/an_truck/doctype/vehicle_warranty/vehicle_warranty.py`.
- `an_truck/an_truck/report/vehicle_profit_and_partner_share/vehicle_profit_and_partner_share.py`.
- `an_truck/hooks.py`, `an_truck/services.py`, `an_truck/transactions.py`,
  `an_truck/portal_search.py`, `an_truck/warranty/workflow.py`.
- `an_truck/public/js/purchase_receipt.js`, `an_truck/patches.txt`.
- `an_truck/patches/v1_0/verify_vehicle_specification_fields_empty.py`.
- `an_truck/patches/v1_0/add_vehicle_specification_receipt_field.py`.
- `an_truck/patches/v1_0/index_vehicle_specification_links.py`.
- `an_truck/translations/ar.csv`.
- `an_truck/tests/test_vehicle_specification_templates.py`,
  `an_truck/tests/test_vehicle_master_specs.py`, `an_truck/tests/test_warranty.py`.
- `docs/vehicle_specification_templates.md`.

In `an_truck_portal`:

- `an_truck_portal/api/{specifications,context,dashboard,records,sales}.py`.
- `frontend/src/components/{FormField,VehicleDrawer,LinkedVehiclesDialog,TemplateSpecifications}.vue`.
- `frontend/src/views/{SpecificationTemplates,Detail,ImportWorkspace}.vue`.
- `frontend/src/{navigation,router}.js`, `frontend/src/locales/{ar,en}.json`.
- `frontend/tests/vehicle-specifications.browser.cjs`.
- `an_truck_portal/public/frontend/manifest.json` and the generated JavaScript asset.

Earlier customer-form and vehicles-table changes in the working tree were
preserved and are not part of this feature's source-file list.
