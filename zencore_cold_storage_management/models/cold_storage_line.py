# -*- coding: utf-8 -*-
from odoo import models, fields


class ColdStorageLine(models.Model):
    _name = 'cold.storage.line'
    _description = 'Cold Storage Line'
    _order = 'name'

    name = fields.Char(string='Line', required=True)

    _name_uniq = models.Constraint(
        'unique (name)',
        'Line name must be unique!',
    )
