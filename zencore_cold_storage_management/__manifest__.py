# -*- coding: utf-8 -*-
{
    'name': 'Zencore Cold Storage Management',
    'version': '19.0.1.0.0',
    'category': 'GAPL',
    'summary': 'Cold Storage Season Management and Physical Storage Slot Setup',
    'description': """
Zencore Cold Storage Management System
======================================
* Dedicated top-level navigation: Season & Configuration
* Seasonal cycle tracking (draft, open, closed) with bag rates
* Multi-dimensional location configuration (Chamber, Floor, Line, Pocket)
* Central Storage Master Setup registry with activation flags and uniqueness constraints
    """,
    'author': 'Zencore / Antigravity AI',
    'website': 'https://zencore.com',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/cold_storage_menus.xml',
        'views/cold_storage_season_views.xml',
        'views/cold_storage_dimension_views.xml',
        'views/cold_storage_master_setup_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
