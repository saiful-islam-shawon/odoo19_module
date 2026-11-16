# -*- coding: utf-8 -*-
from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    total_qty = fields.Float(
        string='Total Qty',
        compute='_compute_total_qty',
        store=True,
        digits='Product Unit of Measure',
        readonly=True,
        help="Total quantity of all product lines in this sales order.",
    )

    @api.depends('order_line.product_uom_qty', 'order_line.display_type')
    def _compute_total_qty(self):
        for order in self:
            order.total_qty = sum(
                line.product_uom_qty for line in order.order_line if not line.display_type
            )
