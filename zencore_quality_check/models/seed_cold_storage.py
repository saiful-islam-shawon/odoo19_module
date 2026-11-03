# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class ZencoreSeedColdStorage(models.Model):
    _name = 'zencore.seed.cold.storage'
    _description = 'Seed Cold Storage Preservation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    # Identification & State
    name = fields.Char(
        string='Storage Reference',
        required=True,
        copy=False,
        readonly=True,
        tracking=True,
        default=lambda self: _('New'),
        help="Unique auto-generated cold storage tracking identifier (CS/YYYY/00001)."
    )
    state = fields.Selection(
        [
            ('stored', 'In Cold Storage'),
            ('under_retest', 'Under Retest'),
            ('released', 'Released'),
            ('scrapped', 'Scrapped'),
        ],
        string='Status',
        default='stored',
        required=True,
        tracking=True,
        copy=False,
        help="Storage lifecycle: In Cold Storage -> Under Retest -> Released or Scrapped."
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )

    # Linkages & Seed Logistics
    qc_id = fields.Many2one(
        'zencore.processed.seed.qc',
        string='Processed Seed QC',
        required=True,
        readonly=True,
        tracking=True,
        ondelete='restrict',
        help="Approved processed seed QC certificate record."
    )
    batch_id = fields.Many2one(
        'zencore.seed.processing.batch',
        string='Processing Batch',
        related='qc_id.batch_id',
        store=True,
        readonly=True
    )
    batch_output_line_id = fields.Many2one(
        'zencore.seed.processing.output.line',
        string='Batch Output Line',
        related='qc_id.batch_output_line_id',
        store=True,
        readonly=True
    )
    product_id = fields.Many2one(
        'product.product',
        string='Finished Seed Product',
        required=True,
        readonly=True,
        tracking=True
    )
    lot_name = fields.Char(
        string='Lot Number (Format 1)',
        readonly=True,
        tracking=True
    )
    lot_id = fields.Many2one(
        'stock.lot',
        string='Stock Lot',
        readonly=True
    )
    category = fields.Selection(
        [
            ('good', 'Good / Commercial Seed'),
            ('bad', 'Bad'),
            ('by_product', 'Substandard / By-Product'),
        ],
        string='Grade Category',
        readonly=True
    )
    pack_size = fields.Char(
        string='Pack Size',
        readonly=True
    )
    bag_count = fields.Integer(
        string='Bag Count',
        readonly=True
    )
    quantity = fields.Float(
        string='Net Weight (kg)',
        digits='Stock Weight',
        readonly=True
    )

    # Backward Traceability
    source_lab_test_ref = fields.Char(
        string='Source Lab Test Ref',
        related='qc_id.source_lab_test_ref',
        store=True,
        readonly=True
    )
    source_receipt_ref = fields.Char(
        string='Source Seed Receipt Ref',
        related='qc_id.source_receipt_ref',
        store=True,
        readonly=True
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Vendor / Supplier',
        related='qc_id.partner_id',
        store=True,
        readonly=True
    )
    raw_product_id = fields.Many2one(
        'product.product',
        string='Raw Intake Seed',
        related='qc_id.raw_product_id',
        store=True,
        readonly=True
    )
    variety = fields.Char(
        string='Seed Variety / Class',
        related='qc_id.variety',
        store=True,
        readonly=True
    )

    # Storage Dates & Expiry Validity
    storage_date = fields.Date(
        string='Storage Date',
        default=fields.Date.context_today,
        required=True,
        tracking=True,
        help="Date when seeds were formally stored in the cold facility."
    )
    validity_date = fields.Date(
        string='Validity Date',
        tracking=True,
        help="Expected preservation validity / expiration date."
    )
    validity_status = fields.Selection(
        [
            ('valid', 'Valid / Safe'),
            ('expired', 'Expired / Needs Retest'),
            ('undefined', 'Validity Not Set'),
        ],
        string='Validity Status',
        compute='_compute_validity_status',
        store=True,
        tracking=True
    )
    storage_user_id = fields.Many2one(
        'res.users',
        string='Stored By',
        default=lambda self: self.env.user,
        tracking=True
    )
    released_date = fields.Datetime(
        string='Release Date',
        readonly=True,
        copy=False,
        tracking=True
    )
    released_by_id = fields.Many2one(
        'res.users',
        string='Released By',
        readonly=True,
        copy=False,
        tracking=True
    )
    retest_id = fields.Many2one(
        'zencore.seed.retest',
        string='Active Retest',
        readonly=True,
        copy=False
    )
    notes = fields.Text(
        string='Storage Notes & Chamber Location',
        tracking=True
    )

    @api.depends('validity_date', 'state')
    def _compute_validity_status(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if not rec.validity_date:
                rec.validity_status = 'undefined'
            elif rec.validity_date < today:
                rec.validity_status = 'expired'
            else:
                rec.validity_status = 'valid'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('zencore.seed.cold.storage.seq') or _('New')
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.context.get('bypass_state_lock'):
            system_fields = {'message_follower_ids', 'activity_ids', 'message_ids', 'retest_id'}
            for record in self:
                if record.state in ['released', 'scrapped']:
                    restricted = set(vals.keys()) - system_fields
                    if restricted:
                        raise UserError(_(
                            "Record '%s' is in %s state and cannot be modified."
                        ) % (record.name, record.state.upper()))
        return super().write(vals)

    def unlink(self):
        for record in self:
            if record.state in ['released', 'scrapped'] and not self.env.context.get('bypass_state_lock'):
                raise UserError(_("Cannot delete record '%s' in %s state.") % (record.name, record.state.upper()))
        return super().unlink()

    # --- Actions ---

    def action_release(self):
        self.ensure_one()
        if self.state != 'stored':
            raise UserError(_("Only active stored lots can be released directly."))
        if not self.validity_date:
            raise ValidationError(_("Please set the Validity Date before attempting to release this seed lot."))
        today = fields.Date.context_today(self)
        if self.validity_date < today:
            raise UserError(_(
                "Cannot release directly! The validity date for this seed lot expired on %s. "
                "Please click 'Send for Retest' to verify seed quality before release."
            ) % self.validity_date)

        self.with_context(bypass_state_lock=True).write({
            'state': 'released',
            'released_date': fields.Datetime.now(),
            'released_by_id': self.env.user.id,
        })
        self.message_post(
            body=_("Seed lot released from Cold Storage on %s by %s.") % (
                fields.Date.context_today(self),
                self.env.user.name
            ),
            subtype_xmlid='mail.mt_note'
        )
        return True

    def action_send_for_retest(self):
        self.ensure_one()
        if self.state != 'stored':
            raise UserError(_("Only active stored lots can be sent for Retest."))
        today = fields.Date.context_today(self)
        if self.validity_date and self.validity_date >= today:
            raise UserError(_(
                "This seed lot has not expired yet (Valid until %s). "
                "Retesting is only required after expiration."
            ) % self.validity_date)

        retest = self.env['zencore.seed.retest'].create({
            'storage_id': self.id,
            'product_id': self.product_id.id,
            'lot_name': self.lot_name,
            'lot_id': self.lot_id.id if self.lot_id else False,
            'category': self.category,
            'pack_size': self.pack_size,
            'bag_count': self.bag_count,
            'quantity': self.quantity,
            'storage_date': self.storage_date,
            'validity_date': self.validity_date,
            'company_id': self.company_id.id,
        })
        self.with_context(bypass_state_lock=True).write({
            'state': 'under_retest',
            'retest_id': retest.id,
        })
        self.message_post(
            body=_("Dispatched expired lot to <b>Retest</b> (%s) by %s.") % (retest.name, self.env.user.name),
            subtype_xmlid='mail.mt_note'
        )
        return {
            'name': _("Seed Retest Evaluation"),
            'type': 'ir.actions.act_window',
            'res_model': 'zencore.seed.retest',
            'view_mode': 'form',
            'res_id': retest.id,
        }

