# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ColdStorageInward(models.Model):
    _name = 'cold.storage.inward'
    _description = 'Cold Storage Inward & Lot'
    _order = 'id desc'

    name = fields.Char(
        string='Lot Number',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
        help="Unique auto-generated lot tracking identifier."
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        required=True,
        ondelete='restrict',
        help="Customer or depositor of the goods."
    )
    date_start = fields.Date(
        string='Start Date',
        required=True,
        default=fields.Date.context_today,
        help="Storage period start date."
    )
    date_end = fields.Date(
        string='End Date',
        required=True,
        help="Expected storage period expiration date."
    )
    product_name = fields.Char(
        string='Product Name',
        required=True,
        help="Manual description of the stored product (e.g., Potato, Seed Potato)."
    )
    bag_quantity = fields.Integer(
        string='Product Quantity (Bosta)',
        required=True,
        default=1,
        help="Quantity in bags / bosta."
    )
    lot_number = fields.Char(
        string='Lot Tracking Reference',
        compute='_compute_lot_number',
        store=True,
        copy=False,
        help="Alias for primary lot number."
    )
    season_id = fields.Many2one(
        'cold.storage.season',
        string='Season',
        required=True,
        ondelete='restrict',
        help="Operational season applicable to this inward deposit."
    )
    bag_rate = fields.Float(
        string='Bag Rate',
        digits=(16, 2),
        default=0.0,
        help="Storage charge rate per bag (auto-filled from Season, manually overridable)."
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company
    )

    _name_uniq = models.Constraint(
        'unique (name)',
        'Lot number must be unique across all records! Two customers cannot have the same lot number.',
    )

    @api.depends('name')
    def _compute_lot_number(self):
        for record in self:
            record.lot_number = record.name

    @api.onchange('season_id')
    def _onchange_season_id(self):
        if self.season_id:
            self.bag_rate = self.season_id.default_bag_rate

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for record in self:
            if record.date_start and record.date_end and record.date_end < record.date_start:
                raise ValidationError(_("End Date cannot be earlier than Start Date for Lot '%s'.") % (record.name or ''))

    @api.constrains('bag_quantity')
    def _check_quantity(self):
        for record in self:
            if record.bag_quantity <= 0:
                raise ValidationError(_("Product Quantity (Bosta) must be greater than zero."))

    @api.constrains('bag_rate')
    def _check_bag_rate(self):
        for record in self:
            if record.bag_rate < 0.0:
                raise ValidationError(_("Bag Rate cannot be negative."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('cold.storage.lot') or _('New')
        return super().create(vals_list)
