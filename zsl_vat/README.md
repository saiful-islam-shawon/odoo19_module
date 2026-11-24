# ZSL Bangladesh VAT Management

Standalone Odoo 19 Community module for Bangladesh VAT workflows. It extends Community Accounting, Sales, Purchase, Inventory, Manufacturing, Point of Sale, Project and Timesheets. It does not require an Enterprise subscription module: recurring service billing is supplied by this module.

## Included flows

- HS/service code, effective-dated VAT/SD/AT/AIT/RD/CD/ATV/VDS rules and Odoo tax mapping.
- VAT identities for company, registered units, products and partners; BIN validation for 11/13 digit formats.
- Declared price and Mushak 4.3 input-output coefficient control.
- Mushak 6.3 tax invoices, 6.4/6.5 challan numbering, 6.6 VDS certificates, and 6.7/6.8 numbering.
- Posted invoice/bill aggregation into Mushak 6.1, 6.2, 6.10 and monthly Mushak 9.1 return with adjustments, VDS, treasury challans, lock and amendment support.
- Manager-controlled return approval/submission, audit chatter/attachments, pre-submission validation, due-date activities and NBR CSV export.
- POS receipt / invoice Mushak-number linkage, recurring service plans, advance/progress time-of-supply fields and project/timesheet billing batches.
- VAT account mapping, VAT-return-to-ledger reconciliation, mixed-supply input tax apportionment, and production valuation/wastage evidence.
- NBR release-compliance checklist, controlled API connector configuration, saved JSON submission payload/response and acknowledgement tracking.
- Odoo-native teal VAT dashboard and navigational groups modelled on the supplied VAT software reference.

## Initial configuration

1. Install **ZSL Bangladesh VAT Management** and give users one of the Bangladesh VAT groups.
2. Complete the company VAT page, create VAT units and create monthly VAT periods.
3. Configure Mushak document series (or use the supplied fallback sequences).
4. Create HS/service codes, tax rules and link each rule to a standard Odoo tax.
5. Configure VAT fields on products and contacts before posting transactions.

## NBR API boundary

The module prepares the approved Mushak 9.1 payload, supports an authenticated HTTP JSON connector, stores the response and acknowledgement, and retains CSV export for manual portal upload. A genuine one-click NBR/iVAS submission cannot be enabled until NBR provides the customer’s production endpoint, payload contract, credentials and enrolment approval. Until then, use **Manual portal submission**, export the CSV/payload, upload it to the NBR portal and enter the acknowledgement before marking the return submitted.

## Automated verification

Run the VAT suite with:

```bash
venv-19/bin/python odoo-bin -c odoo.conf -d nbr_tst -u zsl_vat \
  --test-enable --test-tags /zsl_vat --stop-after-init
```

The suite contains 11 automated test methods, covering core BIN/calendar controls plus recurring service billing, input-tax apportionment, NBR payload preparation, release-compliance evidence and POS/timesheet integration fields.
