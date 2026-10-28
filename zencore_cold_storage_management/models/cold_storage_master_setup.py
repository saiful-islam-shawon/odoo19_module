# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class ColdStorageMasterSetup(models.Model):
    _name = 'cold.storage.master.setup'
    _description = 'Storage Master Setup'
    _order = 'chamber_id, floor_id, line_id, pocket_id'

    name = fields.Char(string='Slot Name', compute='_compute_name', store=True)
    chamber_id = fields.Many2one(
        'cold.storage.chamber',
        string='Chamber',
        required=True,
        ondelete='restrict'
    )
    floor_id = fields.Many2one(
        'cold.storage.floor',
        string='Floor',
        required=True,
        ondelete='restrict'
    )
    line_id = fields.Many2one(
        'cold.storage.line',
        string='Line',
        required=True,
        ondelete='restrict'
    )
    pocket_id = fields.Many2one(
        'cold.storage.pocket',
        string='Pocket',
        required=True,
        ondelete='restrict'
    )
    activate = fields.Boolean(
        string='Activate',
        default=False,
        help="Activation toggle indicating slot operational readiness."
    )

    _unique_storage_slot = models.Constraint(
        'unique (chamber_id, floor_id, line_id, pocket_id)',
        'This Chamber, Floor, Line, and Pocket combination already exists!',
    )

    @api.depends('chamber_id.name', 'floor_id.name', 'line_id.name', 'pocket_id.name')
    def _compute_name(self):
        for record in self:
            parts = [
                record.chamber_id.name or '',
                record.floor_id.name or '',
                record.line_id.name or '',
                record.pocket_id.name or '',
            ]
            valid_parts = [p for p in parts if p]
            record.name = ' / '.join(valid_parts) if valid_parts else _('New Slot')
