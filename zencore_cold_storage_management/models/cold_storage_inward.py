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
    allocation_ids = fields.One2many(
        'cold.storage.inward.allocation',
        'inward_id',
        string='Storage Allocations',
        help="Storage slot allocations for this inward lot."
    )
    plotting_ids = fields.One2many(
        'cold.storage.inward.plotting',
        'inward_id',
        string='Plottings',
        help="Internal slot relocation history for this inward lot."
    )
    plotting_count = fields.Integer(
        string='Plotting Count',
        compute='_compute_plotting_count',
        help="Number of times goods were relocated between slots."
    )
    scrap_ids = fields.One2many(
        'cold.storage.inward.scrap',
        'inward_id',
        string='Scraps',
        help="Loss and damage (scrap) history for this inward lot."
    )
    scrap_count = fields.Integer(
        string='Scrap Count',
        compute='_compute_scrap_count',
        help="Number of scrap / damage events for this lot."
    )
    scrapped_quantity = fields.Integer(
        string='Scrapped Quantity',
        compute='_compute_stock_quantities',
        store=True,
        help="Total bags scrapped/damaged across all scrap records for this lot."
    )
    remaining_quantity = fields.Integer(
        string='Remaining Quantity',
        compute='_compute_stock_quantities',
        store=True,
        help="Net remaining bags available (Total Deposited Quantity - Total Scrapped Quantity)."
    )

    _name_uniq = models.Constraint(
        'unique (name)',
        'Lot number must be unique across all records! Two customers cannot have the same lot number.',
    )

    @api.depends('plotting_ids')
    def _compute_plotting_count(self):
        for record in self:
            record.plotting_count = len(record.plotting_ids)

    @api.depends('scrap_ids')
    def _compute_scrap_count(self):
        for record in self:
            record.scrap_count = len(record.scrap_ids)

    @api.depends('scrap_ids.quantity', 'bag_quantity')
    def _compute_stock_quantities(self):
        for record in self:
            scrapped = sum(record.scrap_ids.mapped('quantity'))
            record.scrapped_quantity = scrapped
            record.remaining_quantity = max(record.bag_quantity - scrapped, 0)

    def action_view_plottings(self):
        self.ensure_one()
        return {
            'name': _('Plottings - Lot %s') % (self.name or ''),
            'type': 'ir.actions.act_window',
            'res_model': 'cold.storage.inward.plotting',
            'view_mode': 'list,form',
            'domain': [('inward_id', '=', self.id)],
            'context': {
                'default_inward_id': self.id,
                'search_default_inward_id': self.id,
            },
        }

    def action_view_scraps(self):
        self.ensure_one()
        return {
            'name': _('Scraps - Lot %s') % (self.name or ''),
            'type': 'ir.actions.act_window',
            'res_model': 'cold.storage.inward.scrap',
            'view_mode': 'list,form',
            'domain': [('inward_id', '=', self.id)],
            'context': {
                'default_inward_id': self.id,
                'search_default_inward_id': self.id,
            },
        }

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

    @api.constrains('allocation_ids', 'bag_quantity', 'scrap_ids')
    def _check_allocation_total(self):
        for record in self:
            total_allocated = sum(record.allocation_ids.mapped('quantity'))
            total_scrapped = sum(record.scrap_ids.mapped('quantity'))
            max_allocatable = record.bag_quantity - total_scrapped
            if total_allocated > max_allocatable:
                raise ValidationError(_(
                    "Total allocated quantity (%(allocated)s bosta) cannot exceed remaining available quantity (%(max_qty)s bosta) for Lot '%(lot)s'."
                ) % {
                    'allocated': total_allocated,
                    'max_qty': max_allocatable,
                    'lot': record.name or '',
                })

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('cold.storage.lot') or _('New')
        return super().create(vals_list)
