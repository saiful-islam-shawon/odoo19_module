# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ZencoreSeedReceipt(models.Model):
    _name = 'zencore.seed.receipt'
    _description = 'Seed Arrival & Physical Inspection Receipt'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    # Identification & Status
    name = fields.Char(
        string='Receipt Reference',
        required=True,
        copy=False,
        readonly=True,
        tracking=True,
        default=lambda self: _('New'),
        help="Unique auto-generated seed receipt tracking identifier."
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('testing', 'Testing'),
            ('passed', 'Passed'),
            ('rejected', 'Rejected'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
        help="Current workflow state of the seed receipt."
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )

    # Vendor & Seed Arrival Details
    partner_id = fields.Many2one(
        'res.partner',
        string='Vendor / Supplier',
        required=True,
        tracking=True,
        ondelete='restrict',
        help="Supplier, contract farmer, or grower supplying the seed."
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product / Seed',
        required=True,
        tracking=True,
        ondelete='restrict',
        help="Seed crop or commercial seed product."
    )
    variety = fields.Char(
        string='Seed Variety / Class',
        tracking=True,
        help="Specific crop variety or seed class (e.g., BR-28, Hybrid Rice)."
    )
    date_receipt = fields.Datetime(
        string='Receipt Date',
        required=True,
        default=fields.Datetime.now,
        tracking=True,
        help="Arrival date and time at the gate or warehouse."
    )
    challan_no = fields.Char(
        string='Challan Number',
        required=True,
        tracking=True,
        help="Supplier or carrier delivery challan / invoice number."
    )
    challan_date = fields.Date(
        string='Challan Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
        help="Date written on the physical delivery challan."
    )
    vehicle_no = fields.Char(
        string='Vehicle Number',
        tracking=True,
        help="Registration plate number of the transport vehicle (truck, pickup, tractor)."
    )

    # Quantity & Weight Breakdown
    bag_count = fields.Integer(
        string='Bag Count',
        required=True,
        default=1,
        tracking=True,
        help="Total number of physical bags unloaded."
    )
    challan_weight = fields.Float(
        string='Challan Weight (kg)',
        digits='Stock Weight',
        required=True,
        default=0.0,
        tracking=True,
        help="Total weight (in kg) stated on the delivery challan."
    )
    received_weight = fields.Float(
        string='Received Weight (kg)',
        digits='Stock Weight',
        required=True,
        default=0.0,
        tracking=True,
        help="Actual measured net weight (in kg) on the scale/weighbridge."
    )
    shortage_weight = fields.Float(
        string='Shortage / Excess (kg)',
        digits='Stock Weight',
        compute='_compute_shortage_weight',
        store=True,
        tracking=True,
        help="Calculated weight variance: Challan Weight minus Received Weight."
    )

    # Physical Inspection Parameters (Testing State)
    damaged_bag_count = fields.Integer(
        string='Damaged / Torn Bags',
        default=0,
        tracking=True,
        help="Number of damaged, torn, or broken bags observed during gate inspection."
    )
    pest_infestation = fields.Selection(
        [
            ('none', 'No (None Observed)'),
            ('present', 'Yes (Pests/Insects Present)'),
        ],
        string='Insect / Pest Infestation',
        default='none',
        tracking=True,
        help="Observed presence of insects, mould, or infestation."
    )
    moisture_condition = fields.Selection(
        [
            ('normal', 'Normal / Dry'),
            ('wet_damp', 'Wet / Damp'),
        ],
        string='Wet / Moisture Condition',
        default='normal',
        tracking=True,
        help="Visual and tactile observation of seed moisture."
    )
    label_condition = fields.Selection(
        [
            ('good', 'Good / Intact'),
            ('mismatched_damaged', 'Mismatched / Damaged'),
        ],
        string='Bag / Label Condition',
        default='good',
        tracking=True,
        help="Verification of bag labeling and physical bag integrity."
    )
    inspection_notes = fields.Text(
        string='Inspection Remarks',
        tracking=True,
        help="Additional remarks, observations, or gate inspection notes."
    )
    inspected_by_id = fields.Many2one(
        'res.users',
        string='Inspected By',
        tracking=True,
        help="Officer who conducted the physical gate inspection."
    )
    inspection_date = fields.Datetime(
        string='Inspection Date',
        tracking=True,
        help="Date and time when physical inspection was performed."
    )

    # Rejection Audit Details
    rejection_reason = fields.Text(
        string='Rejection Reason',
        readonly=True,
        copy=False,
        tracking=True,
        help="Documented justification for consignment rejection."
    )
    rejected_by_id = fields.Many2one(
        'res.users',
        string='Rejected By',
        readonly=True,
        copy=False,
        tracking=True,
        help="User who confirmed the rejection."
    )
    rejection_date = fields.Datetime(
        string='Rejection Date',
        readonly=True,
        copy=False,
        tracking=True,
        help="Timestamp when the consignment was rejected."
    )

    # Linked Laboratory Tests
    lab_test_ids = fields.One2many(
        'zencore.seed.lab.test',
        'receipt_id',
        string='Lab Tests'
    )
    lab_test_count = fields.Integer(
        string='Lab Test Count',
        compute='_compute_lab_test_count'
    )

    def _compute_lab_test_count(self):
        for rec in self:
            rec.lab_test_count = len(rec.lab_test_ids)

    @api.depends('challan_weight', 'received_weight')
    def _compute_shortage_weight(self):
        for rec in self:
            rec.shortage_weight = (rec.challan_weight or 0.0) - (rec.received_weight or 0.0)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('zencore.seed.receipt.seq') or _('New')
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.context.get('bypass_state_lock'):
            system_fields = {
                'message_follower_ids', 'activity_ids', 'message_ids',
                'message_main_attachment_id', 'access_token', 'website_message_ids'
            }
            for rec in self:
                # Terminal lock: Passed or Rejected records cannot be altered
                if rec.state in ['passed', 'rejected']:
                    restricted_fields = set(vals.keys()) - system_fields
                    if restricted_fields:
                        raise ValidationError(
                            _("Record '%s' is in %s state and cannot be modified.") % (rec.name, rec.state.upper())
                        )
                # Testing lock: Receipt arrival details cannot be altered while in testing
                elif rec.state == 'testing':
                    receipt_fields = {
                        'partner_id', 'product_id', 'variety', 'date_receipt',
                        'challan_no', 'challan_date', 'vehicle_no', 'bag_count',
                        'challan_weight', 'received_weight'
                    }
                    if any(f in vals for f in receipt_fields):
                        raise ValidationError(
                            _("Seed arrival and receipt details cannot be edited while in Testing state.")
                        )
        return super().write(vals)

    def action_send_to_testing(self):
        for rec in self:
            if rec.state != 'draft':
                raise ValidationError(_("Only draft receipts can be sent to testing."))
            rec.with_context(bypass_state_lock=True).write({
                'state': 'testing',
                'inspected_by_id': rec.inspected_by_id.id or self.env.user.id,
                'inspection_date': rec.inspection_date or fields.Datetime.now(),
            })
        return True

    def action_approve(self):
        for rec in self:
            if rec.state != 'testing':
                raise ValidationError(_("Only receipts in Testing state can be approved."))
            rec.with_context(bypass_state_lock=True).write({
                'state': 'passed',
            })
        return True

    def action_reject(self):
        self.ensure_one()
        if self.state not in ['draft', 'testing']:
            raise ValidationError(_("Only Draft or Testing receipts can be rejected."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reject Consignment'),
            'res_model': 'zencore.seed.receipt.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_receipt_id': self.id,
            },
        }

    def action_view_lab_tests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Lab Tests for %s') % self.name,
            'res_model': 'zencore.seed.lab.test',
            'view_mode': 'list,form',
            'domain': [('receipt_id', '=', self.id)],
            'context': {
                'default_receipt_id': self.id,
            },
        }
