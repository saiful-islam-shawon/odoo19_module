# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ColdStorageInwardAllocation(models.Model):
    _name = 'cold.storage.inward.allocation'
    _description = 'Cold Storage Inward Slot Allocation'
    _order = 'id asc'

    inward_id = fields.Many2one(
        'cold.storage.inward',
        string='Inward Lot',
        required=True,
        ondelete='cascade',
        index=True,
        help="Inward deposit lot this allocation belongs to."
    )
    slot_id = fields.Many2one(
        'cold.storage.master.setup',
        string='Storage Slot',
        required=True,
        domain="[('activate', '=', True)]",
        ondelete='restrict',
        help="Physical cold storage slot (Chamber / Floor / Line / Pocket). Only active slots are selectable."
    )
    quantity = fields.Integer(
        string='Allocated Quantity (Bags)',
        required=True,
        default=1,
        help="Quantity in bags placed into this storage slot."
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='inward_id.company_id',
        store=True,
        readonly=True
    )
    chamber_id = fields.Many2one(
        'cold.storage.chamber',
        string='Chamber',
        related='slot_id.chamber_id',
        store=True,
        readonly=True,
        index=True
    )
    floor_id = fields.Many2one(
        'cold.storage.floor',
        string='Floor',
        related='slot_id.floor_id',
        store=True,
        readonly=True,
        index=True
    )
    line_id = fields.Many2one(
        'cold.storage.line',
        string='Line',
        related='slot_id.line_id',
        store=True,
        readonly=True,
        index=True
    )
    pocket_id = fields.Many2one(
        'cold.storage.pocket',
        string='Pocket',
        related='slot_id.pocket_id',
        store=True,
        readonly=True,
        index=True
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        related='inward_id.partner_id',
        store=True,
        readonly=True,
        index=True
    )
    product_name = fields.Char(
        string='Product',
        related='inward_id.product_name',
        store=True,
        readonly=True
    )
    season_id = fields.Many2one(
        'cold.storage.season',
        string='Season',
        related='inward_id.season_id',
        store=True,
        readonly=True,
        index=True
    )

    @api.constrains('quantity')
    def _check_quantity(self):
        for record in self:
            if record.quantity <= 0:
                raise ValidationError(_("Allocated Quantity (Bags) must be greater than zero."))
