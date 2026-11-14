# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    total_demand = fields.Float(
        string='Total Demand',
        compute='_compute_total_demand',
        digits='Product Unit of Measure',
        readonly=True,
        help="Total demand of all stock moves in this picking operation.",
    )

    @api.depends('move_ids.product_uom_qty')
    def _compute_total_demand(self):
        for picking in self:
            picking.total_demand = sum(
                move.product_uom_qty for move in picking.move_ids
            )

