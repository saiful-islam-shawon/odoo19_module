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

    @api.constrains('quantity')
    def _check_quantity(self):
        for record in self:
            if record.quantity <= 0:
                raise ValidationError(_("Allocated Quantity (Bags) must be greater than zero."))
