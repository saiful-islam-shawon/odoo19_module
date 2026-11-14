# -*- coding: utf-8 -*-
{
    'name': 'Khatan Supply Distribution',
    'version': '19.0.1.0.0',
    'category': 'Inventory/Supply Chain',
    'summary': 'Total Quantity & Demand Aggregation on Sales, Purchase, and Stock Picking with Purchase Agent assignment',
    'description': """
Khatan Supply Distribution
===========================

Features:
- Adds 'Total Qty = ' dynamic footer sum in Purchase Order Lines table.
- Adds 'Total Qty = ' dynamic footer sum in Sales Order Lines table.
- Adds 'Total Demand = ' dynamic footer sum in Stock Picking Operations table (Receipts & Delivery Orders).
- Adds 'Total Qty' column with grand total aggregate footer sum in:

  * Requests for Quotation (RFQ) list view
  * Purchase Orders list view
  * Quotations list view
  * Sales Orders list view

- Adds 'Purchase Agent' (Many2one to res.partner) in Purchase Order / RFQ Other Information tab after Fiscal Position.
""",
    'author': 'Antigravity / User',
    'website': 'https://www.example.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'purchase',
        'sale',
        'stock',
        'sale_stock',
    ],
    'data': [
        'views/purchase_order_views.xml',
        'views/sale_order_views.xml',
        'views/stock_picking_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'khatan_supply_distribution/static/src/views/list_renderer.js',
            'khatan_supply_distribution/static/src/views/list_renderer.scss',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
