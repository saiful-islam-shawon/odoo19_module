# -*- coding: utf-8 -*-
from odoo import models, fields


class ZencoreSeedLabTestLine(models.Model):
    _name = 'zencore.seed.lab.test.line'
    _description = 'Seed Laboratory Test Line'
    _order = 'sequence, id'

    test_id = fields.Many2one(
        'zencore.seed.lab.test',
        string='Lab Test',
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
        required=True,
        help="Name of the scientific or physical test parameter (e.g., Moisture, Germination, Purity)."
    )
    unit = fields.Char(
        string='Unit',
        default='%',
        help="Unit of measure (%, count, mm, g, etc.)."
    )
    standard_value = fields.Char(
        string='Standard Target / Range',
        help="Approved quality benchmark or acceptable tolerance (e.g., Max 12%, Min 85%)."
    )
    measured_value = fields.Char(
        string='Measured Result',
        help="Observed or instrument-measured test value (entered once test is performed)."
    )
    result = fields.Selection(
        [
            ('pending', 'Pending'),
            ('pass', 'Pass'),
            ('fail', 'Fail'),
        ],
        string='Result Status',
        default='pending',
        required=True,
        help="Evaluation outcome for this specific parameter."
    )
    remarks = fields.Char(
        string='Remarks',
        help="Specific observations or equipment calibration notes."
    )
