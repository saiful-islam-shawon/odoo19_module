# -*- coding: utf-8 -*-
from odoo import models, fields


class ColdStorageFloor(models.Model):
    _name = 'cold.storage.floor'
    _description = 'Cold Storage Floor'
    _order = 'name'

    name = fields.Char(string='Floor', required=True)

    _name_uniq = models.Constraint(
        'unique (name)',
        'Floor name must be unique!',
    )
