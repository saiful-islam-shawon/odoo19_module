# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class ZencoreSeedProcessingBatch(models.Model):
    _name = 'zencore.seed.processing.batch'
    _description = 'Seed Processing Batch'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    # Identification & Status
    name = fields.Char(
        string='Batch Reference',
        required=True,
        copy=False,
        readonly=True,
        tracking=True,
        default=lambda self: _('New'),
        help="Unique auto-generated seed processing batch reference (PB/YYYY/00001)."
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('drying', 'Drying'),
            ('grading', 'Grading'),
            ('packing', 'Packing'),
            ('done', 'Done'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
        help="Processing workflow stage: Draft -> Drying -> Grading -> Packing -> Done."
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    date = fields.Date(
        string='Batch Date',
        default=fields.Date.context_today,
        required=True,
        tracking=True,
        help="Date when seed processing batch was created."
    )
    user_id = fields.Many2one(
        'res.users',
        string='Processing In-Charge',
        default=lambda self: self.env.user,
        tracking=True,
        help="Operator or supervisor responsible for this processing batch."
    )
    is_qc_sent = fields.Boolean(
        string='QC Sent',
        default=False,
        copy=False,
        help="Indicates whether output lots have been dispatched to Processed Seed QC."
    )

    # Source Linkage (Strictly 1-to-1 Approved Lab Test)
    lab_test_id = fields.Many2one(
        'zencore.seed.lab.test',
        string='Lab Quality Test',
        required=True,
        tracking=True,
        domain="[('state', '=', 'approved'), ('processing_batch_id', '=', False)]",
        ondelete='restrict',
        help="Source laboratory quality test that has been Approved/Passed."
    )
    receipt_id = fields.Many2one(
        'zencore.seed.receipt',
        string='Source Seed Receipt',
        related='lab_test_id.receipt_id',
        store=True,
        readonly=True,
        help="Physical arrival receipt referenced by the lab test."
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Vendor / Supplier',
        related='lab_test_id.partner_id',
        store=True,
        readonly=True,
        help="Vendor or grower who supplied the raw seed."
    )
    raw_product_id = fields.Many2one(
        'product.product',
        string='Raw Seed Product',
        related='lab_test_id.product_id',
        store=True,
        readonly=True,
        help="Original raw seed crop product being processed."
    )
    variety = fields.Char(
        string='Seed Variety / Class',
        related='lab_test_id.variety',
        store=True,
        readonly=True,
        help="Crop variety or seed class."
    )
    input_weight = fields.Float(
        string='Received Weight (kg)',
        related='lab_test_id.received_weight',
        store=True,
        readonly=True,
        digits=(12, 2),
        help="Raw seed intake net weight in kilograms."
    )
    input_bags = fields.Integer(
        string='Received Bag Count',
        related='lab_test_id.bag_count',
        store=True,
        readonly=True,
        help="Total physical bags received at intake."
    )

    # Drying Stage Parameters
    initial_moisture = fields.Float(
        string='Initial Moisture (%)',
        digits=(5, 2),
        tracking=True,
        help="Moisture content percentage before drying."
    )
    final_moisture = fields.Float(
        string='Final Moisture (%)',
        digits=(5, 2),
        tracking=True,
        help="Target safe moisture percentage achieved after drying."
    )
    drying_method = fields.Selection(
        [
            ('sun', 'Sun Drying (Floor)'),
            ('mechanical', 'Mechanical Dryer'),
        ],
        string='Drying Method',
        default='sun',
        tracking=True,
        help="Method utilized to reduce seed moisture."
    )
    drying_temp = fields.Float(
        string='Drying Temperature (°C)',
        digits=(5, 1),
        help="Temperature applied during mechanical drying."
    )
    drying_start = fields.Datetime(
        string='Drying Start Time',
        help="Timestamp when drying commenced."
    )
    drying_end = fields.Datetime(
        string='Drying End Time',
        help="Timestamp when drying concluded."
    )
    weight_after_drying = fields.Float(
        string='Weight After Drying (kg)',
        digits=(12, 2),
        tracking=True,
        help="Net seed weight measured after the drying cycle."
    )
    moisture_loss = fields.Float(
        string='Moisture Loss (kg)',
        compute='_compute_moisture_loss',
        store=True,
        digits=(12, 2),
        help="Computed weight reduction due to moisture evaporation."
    )

    # Graded Output Products Table
    output_line_ids = fields.One2many(
        'zencore.seed.processing.output.line',
        'batch_id',
        string='Graded Output Lines',
        copy=True
    )

    # Aggregates & Smart Button Metrics
    total_good_weight = fields.Float(
        string='Good Yield (kg)',
        compute='_compute_totals',
        store=True,
        digits=(12, 2),
        help="Aggregate weight of commercial good seed produced."
    )
    total_good_bags = fields.Integer(
        string='Good Yield (Bags)',
        compute='_compute_totals',
        store=True,
        help="Total bags of commercial good seed packed."
    )
    total_waste_weight = fields.Float(
        string='Waste (kg)',
        compute='_compute_totals',
        store=True,
        digits=(12, 2),
        help="Total quantity of discarded dirt, scrap, or rotten seed."
    )
    output_lot_count = fields.Integer(
        string='Produced Lots Count',
        compute='_compute_output_lot_count',
        help="Total number of graded output products/lots generated."
    )

    notes = fields.Text(
        string='Processing Notes',
        help="Internal observations or instructions regarding this batch."
    )

    @api.depends('input_weight', 'weight_after_drying')
    def _compute_moisture_loss(self):
        for batch in self:
            if batch.input_weight and batch.weight_after_drying:
                batch.moisture_loss = max(0.0, batch.input_weight - batch.weight_after_drying)
            else:
                batch.moisture_loss = 0.0

    @api.depends('output_line_ids.quantity', 'output_line_ids.bag_count', 'output_line_ids.category')
    def _compute_totals(self):
        for batch in self:
            good_lines = batch.output_line_ids.filtered(lambda l: l.category in ['good', 'bad', 'by_product'])
            waste_lines = batch.output_line_ids.filtered(lambda l: l.category == 'waste')
            batch.total_good_weight = sum(good_lines.mapped('quantity'))
            batch.total_good_bags = sum(good_lines.mapped('bag_count'))
            batch.total_waste_weight = sum(waste_lines.mapped('quantity'))

    @api.depends('output_line_ids.category')
    def _compute_output_lot_count(self):
        for batch in self:
            batch.output_lot_count = len(batch.output_line_ids.filtered(lambda l: l.category != 'waste'))

    @api.onchange('lab_test_id')
    def _onchange_lab_test_id(self):
        if self.lab_test_id:
            # Check if lab test has moisture parameter line to auto-populate initial moisture
            moisture_line = self.lab_test_id.line_ids.filtered(
                lambda l: 'moisture' in (l.parameter_name or '').lower() or 'আর্দ্রতা' in (l.parameter_name or '')
            )
            if moisture_line and moisture_line[0].measured_value:
                try:
                    self.initial_moisture = float(moisture_line[0].measured_value)
                except ValueError:
                    pass

    @api.constrains('lab_test_id', 'state')
    def _check_lab_test_eligibility(self):
        for batch in self:
            if batch.lab_test_id:
                if batch.lab_test_id.state != 'approved':
                    raise ValidationError(_("Only laboratory tests with status 'Approved / Passed' can be processed!"))
                duplicate = self.search([
                    ('id', '!=', batch.id),
                    ('lab_test_id', '=', batch.lab_test_id.id),
                    ('state', '!=', 'cancelled')
                ], limit=1)
                if duplicate:
                    raise ValidationError(_(
                        "Lab Test '%s' is already assigned to Processing Batch '%s'. "
                        "Each approved lab test can only be processed once."
                    ) % (batch.lab_test_id.name, duplicate.name))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('zencore.seed.processing.batch.seq') or _('New')
            if vals.get('lab_test_id'):
                duplicate = self.search([
                    ('lab_test_id', '=', vals['lab_test_id']),
                    ('state', '!=', 'cancelled')
                ], limit=1)
                if duplicate:
                    lab_test = self.env['zencore.seed.lab.test'].browse(vals['lab_test_id'])
                    raise ValidationError(_(
                        "Lab Test '%s' is already assigned to Processing Batch '%s'. "
                        "Each approved lab test can only be processed once."
                    ) % (lab_test.name, duplicate.name))
        batches = super().create(vals_list)
        for batch in batches:
            if batch.lab_test_id:
                batch.lab_test_id.with_context(bypass_state_lock=True).processing_batch_id = batch.id
        return batches

    def write(self, vals):
        if not self.env.context.get('bypass_state_lock'):
            system_fields = {'message_follower_ids', 'activity_ids', 'message_ids', 'is_qc_sent'}
            for batch in self:
                if batch.state == 'done':
                    restricted_fields = set(vals.keys()) - system_fields
                    if restricted_fields:
                        raise UserError(_("Completed processing batches are locked and cannot be modified!"))
        res = super().write(vals)
        if 'lab_test_id' in vals:
            for batch in self:
                if batch.lab_test_id:
                    batch.lab_test_id.with_context(bypass_state_lock=True).processing_batch_id = batch.id
        return res

    def unlink(self):
        for batch in self:
            if batch.state == 'done' and not self.env.context.get('bypass_state_lock'):
                raise UserError(_("Cannot delete completed processing batch '%s'!") % batch.name)
            if batch.lab_test_id:
                batch.lab_test_id.with_context(bypass_state_lock=True).processing_batch_id = False
        return super().unlink()

    # --- Stage Lifecycle Actions ---

    def action_start_drying(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_("Drying can only be started from Draft state."))
        self.with_context(bypass_state_lock=True).write({
            'state': 'drying',
            'drying_start': self.drying_start or fields.Datetime.now()
        })
        self.message_post(body=_("Seed processing batch moved to <b>Drying</b> stage."))

    def action_proceed_grading(self):
        self.ensure_one()
        if self.state != 'drying':
            raise UserError(_("Grading can only proceed from Drying stage."))
        self.with_context(bypass_state_lock=True).write({
            'state': 'grading',
            'drying_end': self.drying_end or fields.Datetime.now()
        })
        self.message_post(body=_("Seed drying completed. Moved to <b>Grading</b> stage."))

    def action_proceed_packing(self):
        self.ensure_one()
        if self.state != 'grading':
            raise UserError(_("Packing can only proceed from Grading stage."))
        self.with_context(bypass_state_lock=True).write({'state': 'packing'})
        self.message_post(body=_("Seed grading completed. Moved to <b>Packing</b> stage."))

    def action_mark_done(self):
        self.ensure_one()
        if self.state != 'packing':
            raise UserError(_("Only batches in Packing stage can be marked as Done."))
        self.with_context(bypass_state_lock=True).write({'state': 'done'})
        self.message_post(
            body=_("Seed processing batch <b>Completed &amp; Locked</b>. Graded outputs and lots finalized.")
        )

    def action_send_to_qc(self):
        self.ensure_one()
        if self.state != 'done':
            raise UserError(_("Only batches in 'Done' stage can be sent for Quality Check."))
        if self.is_qc_sent:
            raise UserError(_("This processing batch has already been sent for Quality Check."))
        eligible_lines = self.output_line_ids.filtered(lambda l: l.category != 'waste')
        if not eligible_lines:
            raise ValidationError(_("No non-waste graded seed outputs found to send for Quality Check."))

        qc_vals_list = []
        for line in eligible_lines:
            qc_vals_list.append({
                'batch_id': self.id,
                'batch_output_line_id': line.id,
                'product_id': line.product_id.id,
                'lot_name': line.lot_name,
                'lot_id': line.lot_id.id if line.lot_id else False,
                'category': line.category,
                'pack_size': line.pack_size,
                'bag_count': line.bag_count,
                'quantity': line.quantity,
                'company_id': self.company_id.id,
            })
        created_qcs = self.env['zencore.processed.seed.qc'].create(qc_vals_list)
        self.with_context(bypass_state_lock=True).write({'is_qc_sent': True})
        self.message_post(
            body=_("Dispatched %d non-waste seed lots to <b>Processed Seed QC</b> by %s.") % (
                len(created_qcs),
                self.env.user.name
            )
        )
        return {
            'name': _("Processed Seed QC Records (%s)") % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'zencore.processed.seed.qc',
            'view_mode': 'list,form',
            'domain': [('batch_id', '=', self.id)],
            'context': {'default_batch_id': self.id},
        }

    def action_cancel(self):
        self.ensure_one()
        if self.state == 'done':
            raise UserError(_("Completed batches cannot be cancelled."))
        self.with_context(bypass_state_lock=True).write({'state': 'cancelled'})
        if self.lab_test_id:
            self.lab_test_id.with_context(bypass_state_lock=True).processing_batch_id = False
        self.message_post(body=_("Processing batch was cancelled. Associated Lab Test released."))

    # --- Header Smart Button Actions ---

    def action_view_lots(self):
        self.ensure_one()
        return {
            'name': _("Produced Lots (%s)") % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'zencore.seed.processing.output.line',
            'view_mode': 'list,form',
            'domain': [('batch_id', '=', self.id), ('category', '!=', 'waste')],
            'context': {'default_batch_id': self.id},
        }

    def action_view_good_yield(self):
        self.ensure_one()
        return {
            'name': _("Good Yield Products (%s)") % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'zencore.seed.processing.output.line',
            'view_mode': 'list,form',
            'domain': [('batch_id', '=', self.id), ('category', 'in', ['good', 'bad', 'by_product'])],
            'context': {'default_batch_id': self.id, 'default_category': 'good'},
        }

    def action_view_waste(self):
        self.ensure_one()
        return {
            'name': _("Waste & Scrap Products (%s)") % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'zencore.seed.processing.output.line',
            'view_mode': 'list,form',
            'domain': [('batch_id', '=', self.id), ('category', '=', 'waste')],
            'context': {'default_batch_id': self.id, 'default_category': 'waste'},
        }
