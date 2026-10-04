### AN Truck

Truck Import, VIN Tracking, Vehicle Costing, Sales, Delivery, Warranty, and After-Sales Management.

### Vehicle warranty setup

1. Create coverage categories and a Warranty Coverage Template.
2. Create a Warranty Provider, its branches, and an Active provider contract.
3. Set the default provider/template in AN Truck Settings, or override them on an Item.
4. A submitted Delivery Note activates the warranty from its posting date. A Sales Invoice is only used as a fallback when it has an explicit Delivery Date and no Delivery Note exists.
5. Assign both `AN Truck Warranty User` and `AN Truck Warranty Manager` to managers who must perform operational and approval workflow actions.

Warranty Provider Branch is mandatory when a provider claim leaves Draft. Branch ownership and active status are validated on the server. Claim costs and VAT totals are also recalculated on the server.

Warranty calculations use Frappe `Date` values and never depend on browser time. Configure `Warranty Processing Time Zone` on every Company that owns vehicle warranties. The hourly expiry job evaluates each Company independently: a warranty remains Active through its expiry date and becomes Expired only when the Company's local date is later. The global site timezone is not used or changed.

### Warranty Provider Portal

The restricted portal is available at `/warranty-provider`. Create a Website User with the `AN Truck Warranty Provider User` role, then add one active `Warranty Provider User Access` record. Fixed-branch users are automatically scoped to that branch; All Branches users may choose only active branches belonging to their provider.

The portal provides exact-VIN warranty lookup, provider-scoped claims, inspection and diagnosis, parts and services, coverage costs, private documents, and the provider workflow actions. It intentionally does not expose internal approval notes, approved accounting fields, purchasing data, or unrestricted document APIs.

### Internal warranty reporting

Internal warranty managers and users can open the `Warranty Dashboard` from the AN Truck workspace. It contains operational and financial KPIs, management charts, and the VIN-first after-sales lookup. Eleven standard Script Reports cover active/expiring warranties, claims, cost by VIN/provider/branch/model/component, outside-warranty repairs, provider performance, and the complete warranty claim history by VIN. All financial reporting reads the totals calculated and stored by Warranty Claim validation.

### Production readiness

The `Historical Warranty Backfill Preview` report provides a controlled, exportable dry run for older sold/delivered VINs. It accepts only a linked submitted Delivery Note date or an explicit linked Sales Invoice Delivery Date and never invents a date. Warranty Manager/System Manager execution is rerunnable, savepoint-isolated, and audited. The read-only `Warranty Data Quality` report identifies unsafe master, warranty, claim, attachment, and provider-access inconsistencies without repairing ambiguous business data.

A bilingual `Vehicle Warranty Certificate` is available as a standard print format. Internal System Notifications cover new/resubmitted provider claims and final documents; an idempotent company-aware scheduler creates 30-day and 7-day internal expiry reminders. No customer messages are sent.

Complete operating, security, workflow, backfill, and troubleshooting guidance is in [Vehicle Warranty Operations](docs/warranty-operations.md). Use the [UAT Checklist](docs/warranty-uat-checklist.md) before release and the [Production Deployment and Rollback Runbook](docs/warranty-production-deployment.md) during change approval.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch version-16
bench install-app an_truck
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/an_truck
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
