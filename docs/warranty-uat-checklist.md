# Vehicle Warranty UAT Checklist

Use production-like, non-sensitive test records in a staging site. Record tester, date, VIN, document links, screenshots, and Pass/Fail for every step.

## A. New truck delivery and activation

- Submit a Delivery Note containing a linked Vehicle Master/VIN.
- Confirm one Vehicle Warranty is created with the intended customer, company, provider, template, valid contract, Delivery Note date, coverage snapshot, inclusive expiry, and Serial No expiry.
- Resubmit/replay the activation path and confirm no duplicate is created.
- Automated coverage: passed by `test_delivery_activation_snapshot_expiry_and_idempotency`.

## B. Provider visit and claim

- Sign in as a fixed-branch provider user, search the exact VIN, and confirm status/coverage with no internal financial or approval data.
- Create a claim and confirm the assigned branch cannot be changed.
- Add inspection, diagnosis, one covered part, one outside part, covered/outside labor, report/photos/invoice, then submit.
- Confirm every uploaded File is private and the invoice/VAT summary is correct.
- Automated coverage: passed by portal journey, branch scope, file security, and mixed-cost tests.

## C. Internal review and more information

- As Warranty Manager: Start Review, request more information, and verify the internal system notification.
- As provider: update permitted details and Resubmit; confirm internal-only fields remain absent.
- Approve and repeat with Partially Approve on a second claim; verify decision/audit metadata and approved amount.
- Automated coverage: passed for request/resubmit, approve, partial approve, approved-amount validation, and internal field isolation. Manual UAT remains for visual notification wording.

## D. Repair to close

- Move Approved/Partially Approved to Repair In Progress, Repair Completed, and Final Documents Submitted.
- Confirm final-document internal notification, then close as Warranty Manager.
- Confirm a provider cannot invoke an action unavailable for the current state.
- Automated coverage: passed through Final Documents and manager Close. Manual UAT remains for notification presentation.

## E. Expired warranty

- Search an expired VIN as its provider. Status must be visible and Create Claim unavailable.
- Attempt the create API directly and confirm rejection unless a separately approved exception rule is introduced in a future phase.
- Automated coverage: passed.

## F. Unauthorized provider

- As provider B, attempt provider A's exact VIN, claim URL/API, list, and private file download.
- Confirm no data is returned and no existence-sensitive detail leaks.
- Automated coverage: passed.

## G. Fixed branch boundary

- As a fixed Riyadh user, attempt to create/read/update a Jeddah claim and spoof the branch in API payloads.
- Confirm the server forces Riyadh and rejects Jeddah.
- Automated coverage: passed.

## H. Renewal/extension

- Expire/cancel the old warranty, issue a same-VIN renewal with `renewal_of` and Is Extension, and confirm it becomes effective.
- Confirm the old warranty, coverage snapshot, claims, and VIN history remain accessible and unchanged.
- Confirm two active warranties are rejected.
- Automated coverage: passed for preservation/link, previous-claim visibility in VIN history, and single-active enforcement; manually review the combined VIN history presentation.

## Mixed-cost acceptance case

Enter covered engine part SAR 3,000, covered labor SAR 500, outside brake part SAR 700, and outside labor SAR 300. Expected totals are Total SAR 4,500, Warranty Covered/Provider Claim SAR 3,500, Customer Payable SAR 1,000. Confirm the same values on Warranty Claim, provider portal, dashboard month delta, Cost by VIN report, and Warranty History by VIN. Automated result: passed.

## Customer certificate

- Print `Vehicle Warranty Certificate` in English/Arabic.
- Visually verify Arabic shaping/direction, page breaks, company branding, contact data, coverage/conditions/exclusions, and exact dates.
- Confirm purchase cost, margin, provider settlement, and internal notes are absent.
- Automated content/security assertions: passed. PDF typography and branding require manual sign-off.
