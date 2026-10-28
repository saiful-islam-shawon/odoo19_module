# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ColdStorageSeason(models.Model):
    _name = 'cold.storage.season'
    _description = 'Cold Storage Season'
    _order = 'date_start desc, name'

    name = fields.Char(string='Season Name', required=True, copy=False)
    date_start = fields.Date(
        string='Start Date',
        required=True,
        default=fields.Date.context_today
    )
    date_end = fields.Date(string='End Date', required=True)
    default_bag_rate = fields.Float(
        string='Default Bag Rate',
        digits=(16, 2),
        default=0.0,
        help="Default storage charge rate per bag for this season."
    )
    team_id = fields.Many2one(
        'cold.storage.team',
        string='Team',
        ondelete='restrict',
        help="Operational team assigned to this season."
    )
    season_manager = fields.Char(string='Season Manager', help="Person managing this season.")
    state = fields.Selection([
        ('draft', 'Draft'),
        ('open', 'Open'),
        ('closed', 'Closed'),
    ], string='Status', default='draft', required=True)

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

    def action_open(self):
        for record in self:
            record.state = 'open'

    def action_close(self):
        for record in self:
            record.state = 'closed'

    def action_reset_draft(self):
        for record in self:
            record.state = 'draft'
