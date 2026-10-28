# -*- coding: utf-8 -*-
from odoo import models, fields


class ColdStorageChamber(models.Model):
    _name = 'cold.storage.chamber'
    _description = 'Cold Storage Chamber'
    _order = 'name'

    name = fields.Char(string='Chamber', required=True)

    _name_uniq = models.Constraint(
        'unique (name)',
        'Chamber name must be unique!',
    )
