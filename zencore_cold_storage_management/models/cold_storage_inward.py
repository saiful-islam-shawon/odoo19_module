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
    released_quantity = fields.Integer(
        string='Released Quantity',
        compute='_compute_stock_quantities',
        store=True,
        help="Total bags released / delivered to customer."
    )
    remaining_quantity = fields.Integer(
        string='Remaining Quantity',
        compute='_compute_stock_quantities',
        store=True,
        help="Net remaining bags available (Total Deposited - Scrapped - Released)."
    )
    release_ids = fields.One2many(
        'cold.storage.inward.release',
        'inward_id',
        string='Releases',
        help="Product release and delivery history."
    )
    release_count = fields.Integer(
        string='Release Count',
        compute='_compute_release_count',
        help="Number of deliveries / releases."
    )
    invoice_ids = fields.Many2many(
        'account.move',
        compute='_compute_invoice_ids',
        string='Customer Invoices'
    )
    invoice_count = fields.Integer(
        string='Journal / Invoice Count',
        compute='_compute_invoice_ids',
        help="Number of invoices and journal entries."
    )
    release_status = fields.Selection([
        ('unreleased', 'In Storage'),
        ('partial', 'Partially Released'),
        ('full', 'Fully Released'),
    ], string='Release Status', compute='_compute_release_status', store=True)
    due_amount = fields.Float(
        string='Due Amount',
        compute='_compute_due_and_payment_status',
        digits=(16, 2)
    )
    payment_status = fields.Selection([
        ('no_invoice', 'N/A'),
        ('paid', 'Paid'),
        ('partial', 'Partial Due'),
        ('due', 'Unpaid Due'),
    ], string='Payment Status', compute='_compute_due_and_payment_status')

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

    @api.depends('release_ids')
    def _compute_release_count(self):
        for record in self:
            record.release_count = len(record.release_ids)

    @api.depends('release_ids.move_id')
    def _compute_invoice_ids(self):
        for record in self:
            invoices = record.release_ids.mapped('move_id')
            record.invoice_ids = invoices
            record.invoice_count = len(invoices)

    @api.depends('scrap_ids.quantity', 'release_ids.quantity', 'bag_quantity')
    def _compute_stock_quantities(self):
        for record in self:
            scrapped = sum(record.scrap_ids.mapped('quantity'))
            released = sum(record.release_ids.mapped('quantity'))
            record.scrapped_quantity = scrapped
            record.released_quantity = released
            record.remaining_quantity = max(record.bag_quantity - scrapped - released, 0)

    @api.depends('bag_quantity', 'released_quantity', 'remaining_quantity')
    def _compute_release_status(self):
        for record in self:
            if record.bag_quantity > 0 and record.remaining_quantity == 0:
                record.release_status = 'full'
            elif record.released_quantity > 0 and record.remaining_quantity > 0:
                record.release_status = 'partial'
            else:
                record.release_status = 'unreleased'

    @api.depends('release_ids.move_id.payment_state', 'release_ids.move_id.amount_residual', 'release_ids.move_id.amount_total', 'release_ids.move_id.state')
    def _compute_due_and_payment_status(self):
        for record in self:
            invoices = record.release_ids.mapped('move_id').filtered(lambda inv: inv.state == 'posted')
            if not invoices:
                record.due_amount = 0.0
                record.payment_status = 'no_invoice'
            else:
                total_residual = sum(invoices.mapped('amount_residual'))
                total_amount = sum(invoices.mapped('amount_total'))
                record.due_amount = total_residual
                if total_residual <= 0.0:
                    record.payment_status = 'paid'
                elif total_residual >= total_amount:
                    record.payment_status = 'due'
                else:
                    record.payment_status = 'partial'

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

    def action_open_release_wizard(self):
        self.ensure_one()
        if self.remaining_quantity <= 0:
            raise ValidationError(_("No bags remaining in storage to release."))
        return {
            'name': _('Release Product - Lot %s') % (self.name or ''),
            'type': 'ir.actions.act_window',
            'res_model': 'cold.storage.inward.release.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_inward_id': self.id,
            },
        }

    def action_view_releases(self):
        self.ensure_one()
        return {
            'name': _('Releases - Lot %s') % (self.name or ''),
            'type': 'ir.actions.act_window',
            'res_model': 'cold.storage.inward.release',
            'view_mode': 'list,form',
            'domain': [('inward_id', '=', self.id)],
            'context': {
                'default_inward_id': self.id,
                'search_default_inward_id': self.id,
            },
        }

    def action_view_invoices(self):
        self.ensure_one()
        invoices = self.invoice_ids
        action = {
            'name': _('Journal / Invoices - Lot %s') % (self.name or ''),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'domain': [('id', 'in', invoices.ids)],
            'context': {'default_move_type': 'out_invoice'},
        }
        if len(invoices) == 1:
            action['views'] = [(False, 'form')]
            action['res_id'] = invoices.id
        else:
            action['views'] = [(False, 'list'), (False, 'form')]
        return action

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

    @api.constrains('allocation_ids', 'bag_quantity', 'scrap_ids', 'release_ids')
    def _check_allocation_total(self):
        for record in self:
            total_allocated = sum(record.allocation_ids.mapped('quantity'))
            total_scrapped = sum(record.scrap_ids.mapped('quantity'))
            total_released = sum(record.release_ids.mapped('quantity'))
            max_allocatable = record.bag_quantity - total_scrapped - total_released
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
