# -*- coding: utf-8 -*-
from odoo import models, fields


class ColdStorageTeam(models.Model):
    _name = 'cold.storage.team'
    _description = 'Cold Storage Operational Team'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(string='Team Name', required=True, tracking=True)
    leader_id = fields.Many2one(
        'hr.employee',
        string='Team Leader',
        ondelete='set null',
        tracking=True,
        help="Designated leader of this operational cold storage team."
    )
    member_ids = fields.Many2many(
        'hr.employee',
        'cold_storage_team_hr_employee_rel',
        'team_id',
        'employee_id',
        string='Team Members',
        help="Employees assigned to this operational team."
    )
    active = fields.Boolean(
        string='Active',
        default=True,
        tracking=True,
        help="If unchecked, allows archiving the team without deleting it."
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company
    )

    _name_uniq = models.Constraint(
        'unique (name, company_id)',
        'A team with this name already exists in this company!',
    )
