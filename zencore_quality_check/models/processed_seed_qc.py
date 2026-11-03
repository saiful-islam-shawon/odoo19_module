# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class ZencoreProcessedSeedQc(models.Model):
    _name = 'zencore.processed.seed.qc'
    _description = 'Processed Seed Quality Check'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    # Identification & State
    name = fields.Char(
        string='QC Reference',
        required=True,
        copy=False,
        readonly=True,
        tracking=True,
        default=lambda self: _('New'),
        help="Unique auto-generated processed seed quality test identifier (QC/PS/YYYY/00001)."
    )
    state = fields.Selection(
        [
            ('draft', 'Draft / In Progress'),
            ('approved', 'Approved / Passed'),
            ('rejected', 'Rejected'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
        help="Evaluation lifecycle state: Draft -> Approved or Rejected."
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )

    # Linkage to Processing Batch & Output Line
    batch_id = fields.Many2one(
        'zencore.seed.processing.batch',
        string='Processing Batch',
        required=True,
        readonly=True,
        tracking=True,
        ondelete='restrict',
        help="Processing batch that produced this seed lot."
    )
    batch_output_line_id = fields.Many2one(
        'zencore.seed.processing.output.line',
        string='Processing Output Line',
        readonly=True,
        ondelete='restrict',
        help="Specific graded output line from the batch."
    )

    # Output Product & Lot Details
    product_id = fields.Many2one(
        'product.product',
        string='Finished Seed Product',
        required=True,
        readonly=True,
        tracking=True,
        help="Graded finished product being quality tested."
    )
    lot_name = fields.Char(
        string='Lot Number (Format 1)',
        readonly=True,
        tracking=True,
        help="Assigned Format 1 lot serial number."
    )
    lot_id = fields.Many2one(
        'stock.lot',
        string='Stock Lot',
        readonly=True,
        help="Linked native inventory stock lot record."
    )
    category = fields.Selection(
        [
            ('good', 'Good / Commercial Seed'),
            ('bad', 'Bad'),
            ('by_product', 'Substandard / By-Product'),
        ],
        string='Output Category',
        readonly=True,
        help="Graded product classification."
    )
    pack_size = fields.Char(
        string='Pack Size',
        readonly=True,
        help="Commercial bag packing size."
    )
    bag_count = fields.Integer(
        string='Bag Count',
        readonly=True,
        help="Total bags produced for this lot."
    )
    quantity = fields.Float(
        string='Net Weight (kg)',
        digits='Stock Weight',
        readonly=True,
        help="Total produced weight in kilograms."
    )

    # Backward Traceability
    lab_test_id = fields.Many2one(
        'zencore.seed.lab.test',
        string='Source Lab Test',
        related='batch_id.lab_test_id',
        store=True,
        readonly=True,
        help="Approved raw seed lab test."
    )
    receipt_id = fields.Many2one(
        'zencore.seed.receipt',
        string='Source Seed Receipt',
        related='batch_id.receipt_id',
        store=True,
        readonly=True,
        help="Source seed arrival receipt."
    )
    source_lab_test_ref = fields.Char(
        string='Source Lab Test Ref',
        related='batch_id.lab_test_id.name',
        store=True,
        readonly=True
    )
    source_receipt_ref = fields.Char(
        string='Source Seed Receipt Ref',
        related='batch_id.receipt_id.name',
        store=True,
        readonly=True
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Vendor / Supplier',
        related='batch_id.partner_id',
        store=True,
        readonly=True
    )
    raw_product_id = fields.Many2one(
        'product.product',
        string='Raw Intake Seed',
        related='batch_id.raw_product_id',
        store=True,
        readonly=True
    )
    variety = fields.Char(
        string='Seed Variety / Class',
        related='batch_id.variety',
        store=True,
        readonly=True
    )

    # QC Logistics & Audit
    date_qc = fields.Datetime(
        string='QC Test Date',
        required=True,
        default=fields.Datetime.now,
        tracking=True,
        help="Date and time when post-processing QC was conducted."
    )
    tested_by_id = fields.Many2one(
        'res.users',
        string='Tested By',
        default=lambda self: self.env.user,
        tracking=True,
        help="QC Officer / Technician who performed the quality test."
    )
    approved_by_id = fields.Many2one(
        'res.users',
        string='Approved By',
        readonly=True,
        copy=False,
        tracking=True,
        help="User who approved this processed seed lot."
    )
    date_approved = fields.Datetime(
        string='Approval Date',
        readonly=True,
        copy=False,
        tracking=True
    )
    rejected_by_id = fields.Many2one(
        'res.users',
        string='Rejected By',
        readonly=True,
        copy=False,
        tracking=True,
        help="User who rejected this processed seed lot."
    )
    date_rejected = fields.Datetime(
        string='Rejection Date',
        readonly=True,
        copy=False,
        tracking=True
    )
    rejection_reason = fields.Text(
        string='Rejection Reason',
        readonly=True,
        copy=False,
        tracking=True,
        help="Reason provided when rejecting this seed lot."
    )
    notes = fields.Text(
        string='QC Notes & Observations',
        tracking=True,
        help="General scientific remarks or supervisor notes."
    )

    # Relational Lines
    line_ids = fields.One2many(
        'zencore.processed.seed.qc.line',
        'qc_id',
        string='Test Parameters',
        copy=True
    )

    # Standard default parameter lines template
    DEFAULT_PARAMETERS = [
        ('Moisture Content', '%', 'Max 12%'),
        ('Germination Rate', '%', 'Min 85%'),
        ('Physical Purity', '%', 'Min 98%'),
        ('Genetic Purity', '%', 'Min 99%'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('zencore.processed.seed.qc.seq') or _('New')
            if not vals.get('line_ids'):
                # Preload default standard parameters
                default_lines = []
                seq = 10
                for param, unit, std in self.DEFAULT_PARAMETERS:
                    default_lines.append((0, 0, {
                        'sequence': seq,
                        'parameter_name': param,
                        'unit': unit,
                        'standard_value': std,
                        'result': 'pending',
                    }))
                    seq += 10
                vals['line_ids'] = default_lines
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.context.get('bypass_state_lock'):
            system_fields = {'message_follower_ids', 'activity_ids', 'message_ids'}
            for record in self:
                if record.state in ['approved', 'rejected']:
                    restricted_fields = set(vals.keys()) - system_fields
                    if restricted_fields:
                        raise UserError(_(
                            "Record '%s' is in %s state and cannot be modified."
                        ) % (record.name, record.state.upper()))
        return super().write(vals)

    def unlink(self):
        for record in self:
            if record.state in ['approved', 'rejected'] and not self.env.context.get('bypass_state_lock'):
                raise UserError(_("Cannot delete record '%s' in %s state.") % (record.name, record.state.upper()))
        return super().unlink()

    # --- Actions ---

    def action_approve(self):
        for record in self:
            if record.state != 'draft':
                raise ValidationError(_("Only draft QC tests can be approved."))
            record.with_context(bypass_state_lock=True).write({
                'state': 'approved',
                'approved_by_id': self.env.user.id,
                'date_approved': fields.Datetime.now(),
            })
            record.message_post(
                body=_("<b>Quality Check Approved / Passed</b> by %s.") % self.env.user.name,
                subtype_xmlid='mail.mt_note'
            )
        return True

    def action_reject(self):
        self.ensure_one()
        if self.state != 'draft':
            raise ValidationError(_("Only draft QC tests can be rejected."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reject Processed Seed QC'),
            'res_model': 'zencore.processed.seed.qc.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_qc_id': self.id,
            },
        }

    def action_return_to_draft(self):
        for record in self:
            if record.state == 'draft':
                continue
            previous_state = record.state.upper()
            record.with_context(bypass_state_lock=True).write({
                'state': 'draft',
                'approved_by_id': False,
                'date_approved': False,
                'rejected_by_id': False,
                'date_rejected': False,
                'rejection_reason': False,
            })
            record.message_post(
                body=_("<b>Quality Check Reset to Draft</b> from %s by %s.") % (previous_state, self.env.user.name),
                subtype_xmlid='mail.mt_note'
            )
        return True
