# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ZencoreSeedColdStorageScrap(models.Model):
    _name = 'zencore.seed.cold.storage.scrap'
    _description = 'Cold Storage Isolated Seed Scrap'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    # Identification
    name = fields.Char(
        string='Scrap Reference',
        required=True,
        copy=False,
        readonly=True,
        tracking=True,
        default=lambda self: _('New'),
        help="Unique auto-generated scrap record tracking identifier (SCRAP/YYYY/00001)."
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )

    # Origin Linkages
    storage_id = fields.Many2one(
        'zencore.seed.cold.storage',
        string='Cold Storage Origin',
        readonly=True,
        tracking=True,
        ondelete='restrict'
    )
    retest_id = fields.Many2one(
        'zencore.seed.retest',
        string='Retest Origin',
        readonly=True,
        tracking=True,
        ondelete='restrict'
    )

    # Scrapped Product & Lot Logistics
    product_id = fields.Many2one(
        'product.product',
        string='Seed Product',
        required=True,
        readonly=True,
        tracking=True
    )
    lot_name = fields.Char(
        string='Lot Number (Format 1)',
        readonly=True,
        tracking=True
    )
    lot_id = fields.Many2one(
        'stock.lot',
        string='Stock Lot',
        readonly=True
    )
    category = fields.Selection(
        [
            ('good', 'Good / Commercial Seed'),
            ('bad', 'Bad'),
            ('by_product', 'Substandard / By-Product'),
        ],
        string='Grade Category',
        readonly=True
    )
    pack_size = fields.Char(
        string='Pack Size',
        readonly=True
    )
    bag_count = fields.Integer(
        string='Bag Count',
        readonly=True
    )
    quantity = fields.Float(
        string='Scrapped Weight (kg)',
        digits='Stock Weight',
        readonly=True,
        help="Net weight in kilograms condemned and discarded."
    )

    # Dates & Scrap Justification
    storage_date = fields.Date(
        string='Original Storage Date',
        readonly=True
    )
    validity_date = fields.Date(
        string='Expiration Date',
        readonly=True
    )
    scrap_date = fields.Datetime(
        string='Scrap Date',
        default=fields.Datetime.now,
        readonly=True,
        tracking=True
    )
    scrapped_by_id = fields.Many2one(
        'res.users',
        string='Scrapped By',
        default=lambda self: self.env.user,
        readonly=True,
        tracking=True
    )
    scrap_reason = fields.Text(
        string='Scrap Reason / Defect Justification',
        required=True,
        readonly=True,
        tracking=True,
        help="Detailed scientific justification why this cold-stored seed was scrapped."
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('zencore.seed.cold.storage.scrap.seq') or _('New')
        return super().create(vals_list)

    def write(self, vals):
        system_fields = {'message_follower_ids', 'activity_ids', 'message_ids'}
        if set(vals.keys()) - system_fields:
            raise UserError(_("Scrap records are permanent historical audit archives and cannot be modified."))
        return super().write(vals)

    def unlink(self):
        raise UserError(_("Scrap audit records cannot be deleted."))

