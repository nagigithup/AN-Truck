# ANYUAN quotation design restoration — 2026-11-06

The single format remains **AN Truck - Unified Vehicle Quotation**. This review
supersedes the generic layout described in the initial quotation implementation.
No Portal frontend, ERPNext core, Vehicle Master, stock or financial records were
changed by this fix.

## References actually inspected

Both supplied originals are accessible as attached HTML, including embedded images:

| Original design | Attached source |
| --- | --- |
| H7 PRO 460 4X2 | `/home/nagi/.codex/attachments/3c1f75a0-3c9a-4242-83bb-15e3a220d06e/Pasted text.txt` |
| DONGFENG KC 6X4 | `/home/nagi/.codex/attachments/53da303b-2957-4a33-ab3b-a0b0b231b5f3/Pasted text.txt` |

The earlier format used a generic flowing ERPNext table with a reduced hero,
`ANYUAN MOTORS`/internal Company identifier and sequential technical sections.
It did not preserve the originals' commercial sheet or technical cards.

The restored format retains the original A4 210 × 297 mm sheet, ANYUAN MOTORS CO
masthead, navy/gold colours, hero at 25 mm, information panel at 75 mm, five-column
product grid at 122 mm, cabin cards at 162 mm, price/terms at 205 mm, signatures at
267 mm and footer. The original stylesheet is retained and scoped to this format;
input/select elements become printed values, with no interactive JavaScript.
The two-photo H7 technical sheet and the KC single-wide-photo/compact-card variant
share the same Jinja format. Frappe's implicit 15 mm Chrome PDF margins were
overriding the intended full A4 proportions; explicit zero margins now apply only
to this format.

## Dynamic data and historical safety

- Quotation/Quotation Item supply customer, dates, quantity, net rate, net amount,
  actual tax/charge rows, discounts, rounding and totals. No tax is calculated by
  the template. Price summary is labelled Grand Total, not assumed VAT-inclusive.
- Draft specifications resolve the existing selected template/configuration.
  Submitted documents use only their sealed item/context JSON; they do not read
  newer template revisions or refresh historical Company/customer facts.
- Existing `main_vehicle_photo`, `technical_photo`, `cabin_photo`, additional File
  links, model names, configuration, technical fields and approved warranty/delivery
  text remain authoritative. No reference specifications are embedded as defaults.
- Each quotation item receives its own commercial sheet so the original geometry
  is preserved; quotation-level totals appear only on the final commercial sheet.
  Technical cards, long terms, payment schedules and additional photos continue
  on bounded extra sheets. A row without a selected template has commercial output
  without invented technical specifications.
- Company legal name/tax/contact data come from Company, a single readable active
  ZATCA seller configuration where applicable, Company-linked Address/Contact and
  the explicitly selected company Bank Account. CR reuses ZATCA's seller CRN ID.
  ZATCA Phase 1 can supply its configured VAT number when Company has none.
  The internal `alnagi` identifier is not printed as the brand/legal name. The
  explicitly requested ANYUAN brand masthead remains part of the supplied design.
- Bank, CR, VAT, phone and email values in the reference artwork are **not** copied
  into Company configuration. Missing values stay blank. The original static QR
  and phone list are not presented as configured company data.

## Actual local configuration gaps

On dev.localhost, Company `alnagi` has no configured tax ID, official contact
details, default letterhead or company bank record, and there is no active ZATCA
seller configuration. Supply approved legal/seller name, CR, VAT, address and
contact details using the existing Company/ZATCA/Address/Contact mechanisms and
select a valid company Bank Account on the quotation. No automatic rename,
transaction change, bank creation or data import was performed.

Existing local specification templates are blank/test revisions, not populated
DONGFENG/H7 models; their three quotation image fields are empty. Publish properly
associated model/configuration revisions with the original images and actual
specifications. Do not edit immutable published revisions or historical snapshots.

The default Sales Taxes and Charges Template **15% - A** contains an On Net Total
row with description **Marketing Expenses**, account **Marketing Expenses - A**,
rate 15. The Account is **Chargeable / Expense / Profit and Loss**, not Tax.
That existing configuration explains the displayed line. It remains labelled a
**Charge**, with its actual description/rate/amount; it was not renamed to VAT.
An administrator must correct the intended tax template/account configuration
before issuing quotations that should contain VAT. This fix does not reclassify
accounts, replace defaults or rewrite existing quotations.

## Verification and deliverables

- Thirteen focused quotation tests pass, including real template linking, multiple
  models, permissions, immutable submitted snapshots, actual charge/tax data,
  no-template output, long technical specifications and long commercial terms.
- Standard ERPNext Chrome rendering produces **two A4 pages for each model preview**.
  Both use the same saved print format. No blank PDF pages were found.
- Browser geometry checks for both models pass: no broken images, clipped text,
  overflowing technical tables or blocks extending beyond the footer. Commercial
  and technical PDFs/screenshots were visually compared with both original HTML
  references, including RTL, images, type sizes, card positions and page breaks.
- Existing source quotation JSON is compared before/after printing. The preview
  generator uses unsaved in-memory reference snapshots: it never inserts, saves or
  submits a Quotation, template, vehicle, stock transaction or accounting entry.
- Python compilation and `git diff --check` pass. No full migration, frontend
  rebuild, service restart, commit or push was needed/performed for this fix.

Artifacts: `/home/nagi/my-bench/artifacts/anyuan-quotation/`:

- `before-live-page-1.png`, `after-live-page-1.png`: the same real source quotation
  before/after the presentation fix, without modifying that quotation.
- `h7-pro.pdf`, `dongfeng.pdf`: model design previews and their page PNGs.
- `reference-h7-page-{1,2}.png`, `reference-dongfeng-page-{1,2}.png`: original sheets.
- `visual-checks.json`: browser geometry and image results.

**Preview limitations:** model photos/specifications/warranty text are extracted
from the supplied references only for these unsaved `DESIGN-PREVIEW-*` examples.
Amounts, customer and existing Marketing Expenses charge come from source draft
`SAL-QTN-2026-00007`. Blank company/bank fields reflect the actual missing local
configuration. These previews are not newly issued or submitted business offers.

Focused checks:

```sh
bench --site dev.localhost run-tests --module an_truck.tests.test_vehicle_quotation
bench --site dev.localhost execute an_truck.tests.preview_anyuan_quotation.generate \
  --kwargs '{"reference_files":["/path/to/H7.html","/path/to/KC.html"]}'
PORTAL_PLAYWRIGHT_PATH=/tmp/an-truck-browser-check/node_modules/playwright \
  node apps/an_truck/an_truck/tests/quotation_visual_review.cjs
```

Deployment: the versioned patch is included in normal migration. A targeted
application after deploying these files is also supported:

```sh
bench --site <site> execute an_truck.patches.v1_0.restore_anyuan_quotation_design.execute
```

Only the named Print Format HTML/CSS/PDF-engine configuration is updated; no new
database fields or business-record migrations are required. Already applied on
dev.localhost. Existing format defaults and other formats remain unchanged.

## Changed files (all under apps/an_truck)

- `an_truck/print_formats/unified_vehicle_quotation.html`
- `an_truck/print_formats/anyuan_quotation.css`
- `an_truck/quotation_presentation.py`
- `an_truck/vehicle_quotation.py`
- `an_truck/patches/v1_0/restore_anyuan_quotation_design.py`
- `an_truck/patches.txt`
- `an_truck/tests/test_vehicle_quotation.py`
- `an_truck/tests/preview_anyuan_quotation.py`
- `an_truck/tests/quotation_visual_review.cjs`
- `docs/anyuan_quotation_design_review.md`
- `docs/unified_vehicle_quotation.md` (link to this current review)
