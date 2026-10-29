# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ColdStorageSeason(models.Model):
    _name = 'cold.storage.season'
    _description = 'Cold Storage Season'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc, name'

    name = fields.Char(string='Season Name', required=True, copy=False, tracking=True)
    date_start = fields.Date(
        string='Start Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True
    )
    date_end = fields.Date(string='End Date', required=True, tracking=True)
    default_bag_rate = fields.Float(
        string='Default Bag Rate',
        digits=(16, 2),
        default=0.0,
        tracking=True,
        help="Default storage charge rate per bag for this season."
    )
    team_id = fields.Many2one(
        'cold.storage.team',
        string='Team',
        ondelete='restrict',
        tracking=True,
        help="Operational team assigned to this season."
    )
    season_manager = fields.Char(string='Season Manager', tracking=True, help="Person managing this season.")
    state = fields.Selection([
        ('draft', 'Draft'),
        ('open', 'Open'),
        ('closed', 'Closed'),
    ], string='Status', default='draft', required=True, tracking=True)
    inward_ids = fields.One2many(
        'cold.storage.inward',
        'season_id',
        string='Inward Lots',
        readonly=True
    )
    total_inward_count = fields.Integer(
        string='Total Inward Lots',
        compute='_compute_inward_kpis'
    )
    total_received_bags = fields.Integer(
        string='Total Received Bags',
        compute='_compute_inward_kpis'
    )
    total_released_bags = fields.Integer(
        string='Total Released Bags',
        compute='_compute_inward_kpis'
    )
    total_remaining_bags = fields.Integer(
        string='Total Remaining Bags',
        compute='_compute_inward_kpis'
    )
    total_due_amount = fields.Float(
        string='Total Due Amount',
        digits=(16, 2),
        compute='_compute_inward_kpis'
    )

    @api.onchange('team_id')
    def _onchange_team_id(self):
        if self.team_id and self.team_id.leader_id:
            self.season_manager = self.team_id.leader_id.name

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for record in self:
            if record.date_start and record.date_end and record.date_end < record.date_start:
                raise ValidationError(_("End Date cannot be earlier than Start Date for season '%s'.") % record.name)

    @api.constrains('default_bag_rate')
    def _check_bag_rate(self):
        for record in self:
            if record.default_bag_rate < 0.0:
                raise ValidationError(_("Default Bag Rate cannot be negative."))

    @api.depends(
        'inward_ids',
        'inward_ids.bag_quantity',
        'inward_ids.released_quantity',
        'inward_ids.remaining_quantity',
        'inward_ids.due_amount'
    )
    def _compute_inward_kpis(self):
        for record in self:
            record.total_inward_count = len(record.inward_ids)
            record.total_received_bags = sum(record.inward_ids.mapped('bag_quantity'))
            record.total_released_bags = sum(record.inward_ids.mapped('released_quantity'))
            record.total_remaining_bags = sum(record.inward_ids.mapped('remaining_quantity'))
            record.total_due_amount = sum(record.inward_ids.mapped('due_amount'))

    def action_open(self):
        for record in self:
            record.state = 'open'

    def action_close(self):
        for record in self:
            unreleased_inwards = record.inward_ids.filtered(lambda inv: inv.remaining_quantity > 0)
            if unreleased_inwards:
                lot_details = ", ".join([f"{inv.name} ({inv.remaining_quantity} bags)" for inv in unreleased_inwards])
                total_unreleased = sum(unreleased_inwards.mapped('remaining_quantity'))
                raise ValidationError(_(
                    "Cannot close Season '%(season)s' because there are still %(qty)s unreleased bag(s) in storage across %(count)s lot(s):\n%(lots)s\n\nAll goods must be fully released before closing the season."
                ) % {
                    'season': record.name,
                    'qty': total_unreleased,
                    'count': len(unreleased_inwards),
                    'lots': lot_details,
                })
            record.state = 'closed'

    def action_reset_draft(self):
        for record in self:
            record.state = 'draft'
