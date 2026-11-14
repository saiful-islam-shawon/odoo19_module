# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    total_qty = fields.Float(
        string='Total Qty',
        compute='_compute_total_qty',
        store=True,
        digits='Product Unit of Measure',
        readonly=True,
        help="Total quantity of all product lines in this purchase order.",
    )
    purchase_agent_id = fields.Many2one(
        'res.partner',
        string='Purchase Agent',
        tracking=True,
        help="Contact person acting as the purchase agent for this order.",
    )

    @api.depends('order_line.product_qty', 'order_line.display_type')
    def _compute_total_qty(self):
        for order in self:
            order.total_qty = sum(
                line.product_qty for line in order.order_line if not line.display_type
            )

