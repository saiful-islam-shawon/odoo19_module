# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ZencoreSeedLabTest(models.Model):
    _name = 'zencore.seed.lab.test'
    _description = 'Seed Laboratory Quality Test'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    # Identification & State
    name = fields.Char(
        string='Test Reference',
        required=True,
        copy=False,
        readonly=True,
        tracking=True,
        default=lambda self: _('New'),
        help="Unique auto-generated lab test tracking identifier."
    )
    state = fields.Selection(
        [
            ('draft', 'Draft / In Progress'),
            ('to_verify', 'To Verify'),
            ('to_approve', 'To Approve'),
            ('approved', 'Approved / Passed'),
            ('rejected', 'Rejected'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
        help="3-tier evaluation lifecycle state of the laboratory test."
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )

    # Linkage to Seed Arrival Receipt
    receipt_id = fields.Many2one(
        'zencore.seed.receipt',
        string='Seed Receipt',
        required=True,
        domain="[('state', '=', 'passed')]",
        tracking=True,
        ondelete='restrict',
        help="Seed physical arrival receipt that has passed initial gate inspection."
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Vendor / Supplier',
        related='receipt_id.partner_id',
        store=True,
        readonly=True,
        help="Supplier or grower linked to the seed arrival receipt."
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product / Seed',
        related='receipt_id.product_id',
        store=True,
        readonly=True,
        help="Seed crop product being tested."
    )
    variety = fields.Char(
        string='Seed Variety / Class',
        related='receipt_id.variety',
        store=True,
        readonly=True,
        help="Crop variety or seed class from receipt."
    )
    challan_no = fields.Char(
        string='Challan Number',
        related='receipt_id.challan_no',
        store=True,
        readonly=True
    )
    date_receipt = fields.Datetime(
        string='Receipt Date',
        related='receipt_id.date_receipt',
        store=True,
        readonly=True
    )
    received_weight = fields.Float(
        string='Received Weight (kg)',
        related='receipt_id.received_weight',
        store=True,
        readonly=True,
        digits='Stock Weight'
    )
    bag_count = fields.Integer(
        string='Bag Count',
        related='receipt_id.bag_count',
        store=True,
        readonly=True
    )

    # Test Logistics
    date_test = fields.Datetime(
        string='Test Date',
        required=True,
        default=fields.Datetime.now,
        tracking=True,
        help="Date and time when laboratory testing commenced."
    )
    sample_id = fields.Char(
        string='Sample Reference / ID',
        tracking=True,
        help="Laboratory physical sample bottle or bag tracking code."
    )
    line_ids = fields.One2many(
        'zencore.seed.lab.test.line',
        'test_id',
        string='Test Parameters',
        copy=True
    )
    overall_notes = fields.Text(
        string='Laboratory Notes',
        tracking=True,
        help="General scientific remarks, calibration records, or summary observations."
    )

    # Audit & Segregation of Duties Signatures
    submitted_by_id = fields.Many2one(
        'res.users',
        string='Submitted By',
        readonly=True,
        copy=False,
        tracking=True,
        help="Technician who concluded testing and submitted for verification."
    )
    date_submitted = fields.Datetime(
        string='Submission Date',
        readonly=True,
        copy=False,
        tracking=True
    )
    verified_by_id = fields.Many2one(
        'res.users',
        string='Verified By',
        readonly=True,
        copy=False,
        tracking=True,
        help="QC Manager / Checker who verified the testing metrics."
    )
    date_verified = fields.Datetime(
        string='Verification Date',
        readonly=True,
        copy=False,
        tracking=True
    )
    approved_by_id = fields.Many2one(
        'res.users',
        string='Approved By',
        readonly=True,
        copy=False,
        tracking=True,
        help="Executive Approver / GM who authorized final acceptance."
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
        help="Official who rejected the laboratory test."
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
        help="Detailed justification for laboratory test rejection."
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'line_ids' in fields_list and not res.get('line_ids'):
            res['line_ids'] = [
                (0, 0, {'sequence': 10, 'parameter_name': 'Moisture', 'unit': '%', 'standard_value': 'Max 12.0%', 'result': 'pending'}),
                (0, 0, {'sequence': 20, 'parameter_name': 'Physical Purity', 'unit': '%', 'standard_value': 'Min 98.0%', 'result': 'pending'}),
                (0, 0, {'sequence': 30, 'parameter_name': 'Germination', 'unit': '%', 'standard_value': 'Min 80.0%', 'result': 'pending'}),
                (0, 0, {'sequence': 40, 'parameter_name': 'Genetic Purity', 'unit': '%', 'standard_value': 'Min 95.0%', 'result': 'pending'}),
                (0, 0, {'sequence': 50, 'parameter_name': 'Inert Matter', 'unit': '%', 'standard_value': 'Max 2.0%', 'result': 'pending'}),
                (0, 0, {'sequence': 60, 'parameter_name': 'Other Crop Seed', 'unit': '%', 'standard_value': 'Nil / 0%', 'result': 'pending'}),
            ]
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('zencore.seed.lab.test.seq') or _('New')
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.context.get('bypass_state_lock'):
            system_fields = {
                'message_follower_ids', 'activity_ids', 'message_ids',
                'message_main_attachment_id', 'access_token', 'website_message_ids'
            }
            for rec in self:
                # Terminal lock: Approved or Rejected records cannot be altered
                if rec.state in ['approved', 'rejected']:
                    restricted_fields = set(vals.keys()) - system_fields
                    if restricted_fields:
                        raise ValidationError(
                            _("Lab Test record '%s' is in %s state and cannot be modified.") % (rec.name, rec.state.upper())
                        )
                # Verification / Approval lock: Test lines and receipt linkage locked
                elif rec.state in ['to_verify', 'to_approve']:
                    locked_fields = {'receipt_id', 'line_ids', 'date_test', 'sample_id'}
                    if any(f in vals for f in locked_fields):
                        raise ValidationError(
                            _("Lab test parameters and receipt linkage cannot be altered while under review (%s).") % rec.state.upper()
                        )
        return super().write(vals)

    def action_submit(self):
        if not self.env.user.has_group('zencore_quality_check.group_zencore_quality_technician'):
            raise ValidationError(_("Access Denied: Only users with 'QC Technician' rights can submit lab tests."))
        for rec in self:
            if rec.state != 'draft':
                raise ValidationError(_("Only draft tests can be submitted for verification."))
            if not rec.line_ids:
                raise ValidationError(_("Please record at least one test parameter line before submitting."))
            rec.with_context(bypass_state_lock=True).write({
                'state': 'to_verify',
                'submitted_by_id': self.env.user.id,
                'date_submitted': fields.Datetime.now(),
            })
        return True

    def action_verify(self):
        if not self.env.user.has_group('zencore_quality_check.group_zencore_quality_checker'):
            raise ValidationError(_("Access Denied: Only users with 'QC Checker' rights can verify lab tests."))
        for rec in self:
            if rec.state != 'to_verify':
                raise ValidationError(_("Only tests in 'To Verify' state can be verified."))
            rec.with_context(bypass_state_lock=True).write({
                'state': 'to_approve',
                'verified_by_id': self.env.user.id,
                'date_verified': fields.Datetime.now(),
            })
        return True

    def action_return_to_draft(self):
        if not (self.env.user.has_group('zencore_quality_check.group_zencore_quality_checker') or
                self.env.user.has_group('zencore_quality_check.group_zencore_quality_approver')):
            raise ValidationError(_("Access Denied: Only QC Checkers or Approvers can return tests to draft."))
        for rec in self:
            if rec.state not in ['to_verify', 'to_approve']:
                raise ValidationError(_("Only tests under review can be returned to draft."))
            previous_state = rec.state
            rec.with_context(bypass_state_lock=True).write({
                'state': 'draft',
            })
            rec.message_post(
                body=_("<b>Test Returned to Draft</b><br/>Stage: from %s to Draft for re-testing/correction by %s.") % (
                    previous_state.upper(),
                    self.env.user.name
                ),
                subtype_xmlid='mail.mt_note'
            )
        return True

    def action_approve(self):
        if not self.env.user.has_group('zencore_quality_check.group_zencore_quality_approver'):
            raise ValidationError(_("Access Denied: Only users with 'QC Approver' rights can approve lab tests."))
        for rec in self:
            if rec.state != 'to_approve':
                raise ValidationError(_("Only verified tests in 'To Approve' state can be approved."))
            rec.with_context(bypass_state_lock=True).write({
                'state': 'approved',
                'approved_by_id': self.env.user.id,
                'date_approved': fields.Datetime.now(),
            })
        return True

    def action_reject(self):
        self.ensure_one()
        if not (self.env.user.has_group('zencore_quality_check.group_zencore_quality_checker') or
                self.env.user.has_group('zencore_quality_check.group_zencore_quality_approver')):
            raise ValidationError(_("Access Denied: Only QC Checkers or Approvers can reject a lab test."))
        if self.state not in ['to_verify', 'to_approve']:
            raise ValidationError(_("Only tests in 'To Verify' or 'To Approve' state can be rejected."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reject Lab Test'),
            'res_model': 'zencore.seed.lab.test.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_test_id': self.id,
            },
        }
