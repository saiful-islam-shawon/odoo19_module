# -*- coding: utf-8 -*-
from odoo import models, fields


class ColdStoragePocket(models.Model):
    _name = 'cold.storage.pocket'
    _description = 'Cold Storage Pocket'
    _order = 'name'

    name = fields.Char(string='Pocket', required=True)

    _name_uniq = models.Constraint(
        'unique (name)',
        'Pocket name must be unique!',
    )
