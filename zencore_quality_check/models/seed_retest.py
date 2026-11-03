# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class ZencoreSeedRetest(models.Model):
    _name = 'zencore.seed.retest'
    _description = 'Seed Retest Evaluation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    # Identification & State
    name = fields.Char(
        string='Retest Reference',
        required=True,
        copy=False,
        readonly=True,
        tracking=True,
        default=lambda self: _('New'),
        help="Unique auto-generated retest tracking identifier (RET/YYYY/00001)."
    )
    state = fields.Selection(
        [
            ('draft', 'Testing in Progress'),
            ('passed', 'Passed / Released'),
            ('failed', 'Failed / Scrapped'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
        help="Retest outcome lifecycle: Testing in Progress -> Passed or Failed."
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )

    # Linked Storage Record
    storage_id = fields.Many2one(
        'zencore.seed.cold.storage',
        string='Cold Storage Origin',
        required=True,
        readonly=True,
        tracking=True,
        ondelete='restrict',
        help="Origin cold storage seed lot being retested."
    )

    # Inherited Logistics (Readonly)
    product_id = fields.Many2one(
        'product.product',
        string='Seed Product',
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
    storage_date = fields.Date(
        string='Storage Date',
        readonly=True
    )
    validity_date = fields.Date(
        string='Expired Validity Date',
        readonly=True
    )

    # Retest Operational Details
    date_retest = fields.Datetime(
        string='Retest Date',
        default=fields.Datetime.now,
        required=True,
        tracking=True
    )
    tested_by_id = fields.Many2one(
        'res.users',
        string='Tested By',
        default=lambda self: self.env.user,
        tracking=True
    )
    evaluated_by_id = fields.Many2one(
        'res.users',
        string='Evaluated By',
        readonly=True,
        copy=False,
        tracking=True
    )
    date_evaluated = fields.Datetime(
        string='Evaluation Date',
        readonly=True,
        copy=False,
        tracking=True
    )
    scrap_reason = fields.Text(
        string='Scrap / Failure Reason',
        readonly=True,
        copy=False,
        tracking=True
    )
    notes = fields.Text(
        string='Retest Notes & Lab Observations',
        tracking=True
    )

    # Parameter lines
    line_ids = fields.One2many(
        'zencore.seed.retest.line',
        'retest_id',
        string='Retest Parameters',
        copy=True
    )

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
                vals['name'] = self.env['ir.sequence'].next_by_code('zencore.seed.retest.seq') or _('New')
            if not vals.get('line_ids'):
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
                if record.state in ['passed', 'failed']:
                    restricted = set(vals.keys()) - system_fields
                    if restricted:
                        raise UserError(_(
                            "Record '%s' is in %s state and cannot be modified."
                        ) % (record.name, record.state.upper()))
        return super().write(vals)

    def unlink(self):
        for record in self:
            if record.state in ['passed', 'failed'] and not self.env.context.get('bypass_state_lock'):
                raise UserError(_("Cannot delete record '%s' in %s state.") % (record.name, record.state.upper()))
        return super().unlink()

    # --- Actions ---

    def action_release(self):
        for record in self:
            if record.state != 'draft':
                raise ValidationError(_("Only draft retests can be approved and released."))
            record.with_context(bypass_state_lock=True).write({
                'state': 'passed',
                'evaluated_by_id': self.env.user.id,
                'date_evaluated': fields.Datetime.now(),
            })
            record.message_post(
                body=_("<b>Retest Passed</b> by %s. Seed quality verified for commercial release.") % self.env.user.name,
                subtype_xmlid='mail.mt_note'
            )
            # Update origin Cold Storage lot
            record.storage_id.with_context(bypass_state_lock=True).write({
                'state': 'released',
                'released_date': fields.Datetime.now(),
                'released_by_id': self.env.user.id,
            })
            record.storage_id.message_post(
                body=_("Seed lot <b>Released from Cold Storage</b> following successful Retest (%s) by %s.") % (
                    record.name,
                    self.env.user.name
                ),
                subtype_xmlid='mail.mt_note'
            )
        return True

    def action_scrap(self):
        self.ensure_one()
        if self.state != 'draft':
            raise ValidationError(_("Only draft retests can be scrapped."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Scrap Expired Seed Lot'),
            'res_model': 'zencore.seed.retest.scrap.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_retest_id': self.id,
            },
        }

