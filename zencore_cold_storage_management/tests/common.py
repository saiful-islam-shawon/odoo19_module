# -*- coding: utf-8 -*-


def setup_test_accounting(env, partner=None):
    """Ensure minimal Chart of Accounts and Journals exist for tests on fresh DBs (e.g. Odoo.sh).

    Idempotent: uses existing accounts and journals if already configured.
    """
    company = env.company
    Account = env['account.account']
    Journal = env['account.journal']

    # 1. Income Account
    income_acc = Account.search([
        ('company_ids', 'in', company.id),
        ('account_type', '=', 'income'),
    ], limit=1)
    if not income_acc:
        income_acc = Account.create({
            'name': 'Cold Storage Service Income Test',
            'code': '400999',
            'account_type': 'income',
            'company_ids': [(4, company.id)],
        })

    # 2. Receivable Account
    receivable_acc = Account.search([
        ('company_ids', 'in', company.id),
        ('account_type', '=', 'asset_receivable'),
    ], limit=1)
    if not receivable_acc:
        receivable_acc = Account.create({
            'name': 'Cold Storage Debtors Test',
            'code': '120999',
            'account_type': 'asset_receivable',
            'company_ids': [(4, company.id)],
        })

    # 3. Cash / Liquidity Account
    cash_acc = Account.search([
        ('company_ids', 'in', company.id),
        ('account_type', '=', 'asset_cash'),
    ], limit=1)
    if not cash_acc:
        cash_acc = Account.create({
            'name': 'Cold Storage Cash Test',
            'code': '101999',
            'account_type': 'asset_cash',
            'company_ids': [(4, company.id)],
        })

    # 4. Sales Journal
    sale_journal = Journal.search([
        ('company_id', '=', company.id),
        ('type', '=', 'sale'),
    ], limit=1)
    if not sale_journal:
        sale_journal = Journal.create({
            'name': 'Customer Invoices Test',
            'code': 'INV_T',
            'type': 'sale',
            'company_id': company.id,
            'default_account_id': income_acc.id,
        })
    elif not sale_journal.default_account_id:
        sale_journal.default_account_id = income_acc.id

    # 5. Cash / Bank Journal & Outstanding Account
    cash_journal = Journal.search([
        ('company_id', '=', company.id),
        ('type', 'in', ['cash', 'bank']),
    ], limit=1)
    if not cash_journal:
        cash_journal = Journal.create({
            'name': 'Cash Test',
            'code': 'CSH_T',
            'type': 'cash',
            'company_id': company.id,
            'default_account_id': cash_acc.id,
        })
    elif not cash_journal.default_account_id:
        cash_journal.default_account_id = cash_acc.id

    # Set transfer_account_id on company if unset (needed by Odoo payment outstanding account resolution)
    if not company.transfer_account_id:
        company.transfer_account_id = cash_acc.id

    # Ensure payment method lines point to cash_acc if unset
    for line in cash_journal.inbound_payment_method_line_ids:
        if not line.payment_account_id:
            line.payment_account_id = cash_acc.id

    for line in cash_journal.outbound_payment_method_line_ids:
        if not line.payment_account_id:
            line.payment_account_id = cash_acc.id

    # 6. Partner Receivable
    if partner and not partner.property_account_receivable_id:
        partner.property_account_receivable_id = receivable_acc.id

    return {
        'income_acc': income_acc,
        'receivable_acc': receivable_acc,
        'cash_acc': cash_acc,
        'sale_journal': sale_journal,
        'cash_journal': cash_journal,
    }
