{
    'name': 'Systech Invoice and Money Receipt Reports',
    'version': '19.0.1.0.19',
    'category': 'Accounting/Accounting',
    'summary': 'Narrow customer invoice, credit note, and money receipt layouts',
    'description': """
        This module customizes Accounting reports with:
        - Narrow 150 mm customer invoice and credit note layouts matching the Systech design
        - Previous due and total due values on customer invoices
        - A custom money receipt report
    """,
    'author': 'Anwar Hossain',
    'depends': ['base', 'account', 'account_edi_ubl_cii', 'systech_publications'],
    'data': [
        'security/ir.model.access.csv',
        'views/account_move_views.xml',
        'views/account_payment_views.xml',
        'report/paper_format.xml',
        'report/invoice_report.xml',
        'report/report_payment_receipt.xml',
        'report/report_action.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'pre_init_hook': '_pre_init_hook',
    'license': 'LGPL-3',
}
