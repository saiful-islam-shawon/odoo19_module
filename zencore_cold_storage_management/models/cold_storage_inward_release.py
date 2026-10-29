# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class ColdStorageInwardRelease(models.Model):
    _name = 'cold.storage.inward.release'
    _description = 'Cold Storage Inward Product Release (Delivery)'
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Delivery Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
        help="Unique auto-generated delivery reference."
    )
    inward_id = fields.Many2one(
        'cold.storage.inward',
        string='Inward Lot',
        required=True,
        ondelete='cascade',
        index=True,
        help="Inward lot being released."
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        related='inward_id.partner_id',
        store=True,
        readonly=True,
        help="Depositor / Customer receiving the goods."
    )
    date = fields.Date(
        string='Release Date',
        required=True,
        default=fields.Date.context_today,
        help="Date when goods were released from storage."
    )
    receiver_name = fields.Char(
        string='Receiver / Delivered To',
        required=True,
        help="Person who collected the bags (customer, driver, representative)."
    )
    vehicle_no = fields.Char(
        string='Vehicle / Gate Pass No',
        help="Vehicle plate number, transport note, or gate pass reference."
    )
    notes = fields.Text(
        string='Remarks / Notes'
    )
    quantity = fields.Integer(
        string='Total Released Bags',
        required=True,
        default=1,
        help="Total quantity in bags released in this delivery."
    )
    bag_rate = fields.Float(
        string='Bag Rate',
        digits=(16, 2),
        help="Storage charge rate per bag."
    )
    total_amount = fields.Float(
        string='Total Charge',
        digits=(16, 2),
        help="Total storage fee billed for this release."
    )
    payment_mode = fields.Selection([
        ('immediate', 'Immediate Payment (Cash / Bank)'),
        ('credit', 'Pay Later / Credit (Due)'),
    ], string='Payment Mode', required=False)
    journal_id = fields.Many2one(
        'account.journal',
        string='Payment Journal',
        required=False,
        help="Cash or Bank journal where payment was collected."
    )
    move_id = fields.Many2one(
        'account.move',
        string='Customer Invoice',
        readonly=True,
        help="Generated customer invoice and journal entry in Sales Journal."
    )
    line_ids = fields.One2many(
        'cold.storage.inward.release.line',
        'release_id',
        string='Slot Breakdown',
        help="Details of quantities released from individual storage slots."
    )
    user_id = fields.Many2one(
        'res.users',
        string='Responsible',
        default=lambda self: self.env.user,
        readonly=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='inward_id.company_id',
        store=True,
        readonly=True
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('cold.storage.release') or _('New')
        return super().create(vals_list)


class ColdStorageInwardReleaseLine(models.Model):
    _name = 'cold.storage.inward.release.line'
    _description = 'Cold Storage Inward Release Slot Detail'

    release_id = fields.Many2one(
        'cold.storage.inward.release',
        string='Release Order',
        required=True,
        ondelete='cascade',
        index=True
    )
    slot_id = fields.Many2one(
        'cold.storage.master.setup',
        string='Storage Slot',
        required=True
    )
    quantity = fields.Integer(
        string='Released Quantity',
        required=True,
        default=1
    )
