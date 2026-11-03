# -*- coding: utf-8 -*-
from odoo import models, fields


class ZencoreProcessedSeedQcLine(models.Model):
    _name = 'zencore.processed.seed.qc.line'
    _description = 'Processed Seed QC Parameter Line'
    _order = 'sequence, id'

    qc_id = fields.Many2one(
        'zencore.processed.seed.qc',
        string='Processed Seed QC',
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
        help="Name of the quality parameter (e.g., Moisture, Germination, Purity)."
    )
    unit = fields.Char(
        string='Unit',
        default='%',
        help="Unit of measure (%, count, mm, g, etc.)."
    )
    standard_value = fields.Char(
        string='Standard Target / Benchmark',
        help="Approved quality standard or acceptable benchmark."
    )
    measured_value = fields.Char(
        string='Measured Result',
        help="Laboratory measured test result."
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

