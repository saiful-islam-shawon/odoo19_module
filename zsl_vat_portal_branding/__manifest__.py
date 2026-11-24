{
    'name': 'ZSL VAT Dedicated Login & Workspace',
    'summary': 'Zencore-branded sign-in and VAT-only app menu for dedicated users',
    'version': '19.0.1.0.2',
    'category': 'Accounting/Localizations',
    'author': 'Zencore Solutions Ltd.',
    'license': 'LGPL-3',
    'depends': ['web', 'zsl_vat'],
    'data': [
        'security/vat_dedicated_group.xml',
        'views/login_templates.xml',
        'views/vat_workspace_menus.xml',
        'data/vat_workspace_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'zsl_vat_portal_branding/static/src/js/home_menu_compat.js',
            'zsl_vat_portal_branding/static/src/xml/vat_workspace.xml',
            'zsl_vat_portal_branding/static/src/scss/vat_workspace.scss',
        ],
    },
    'installable': True,
    'application': False,
}
