{
    'name': 'Zencore Accounting Filter',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'In-report product category filter and customized single partner ledger layout',
    'description': """
        This module customizes Odoo 19 Enterprise Partner Ledger:
        - When a single partner is selected, transforms the view into an adaptive layout with columns:
          Customer Name, Number, Date, Debit, Credit, Balance
        - Provides in-report Date, Customer Name, and Category filter selectors above the table
        - Filters invoice lines by product category and matches reconciled payments proportionally
        - Preserves default multi-partner Partner Ledger behavior when no single partner is selected
    """,
    'author': 'Zencore',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'account',
        'account_reports',
        'product',
        'systech_publications',
    ],
    'data': [
        'views/report_partner_ledger_pdf.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'zencore_accounting_filter/static/src/components/partner_ledger/header.xml',
            'zencore_accounting_filter/static/src/components/partner_ledger/header.js',
            'zencore_accounting_filter/static/src/components/partner_ledger/partner_ledger.scss',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}

