# -*- coding: utf-8 -*-
from odoo import models, fields


class ZencoreSeedRetestLine(models.Model):
    _name = 'zencore.seed.retest.line'
    _description = 'Seed Retest Parameter Line'
    _order = 'sequence, id'

    retest_id = fields.Many2one(
        'zencore.seed.retest',
        string='Retest Evaluation',
        required=True,
        ondelete='cascade',
        index=True
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10
    )
    parameter_name = fields.Char(
        string='Test Parameter',
        required=True
    )
    unit = fields.Char(
        string='Unit',
        default='%'
    )
    standard_value = fields.Char(
        string='Standard Benchmark'
    )
    measured_value = fields.Char(
        string='Measured Result'
    )
    result = fields.Selection(
        [
            ('pending', 'Pending'),
            ('pass', 'Pass'),
            ('fail', 'Fail'),
        ],
        string='Result Status',
        default='pending',
        required=True
    )
    remarks = fields.Char(
        string='Remarks'
    )

