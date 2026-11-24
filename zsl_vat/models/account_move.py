from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from .mushak_report import mushak_report_action


class AccountMove(models.Model):
    _inherit = 'account.move'

    vat_unit_id = fields.Many2one('vat.unit', string='VAT Unit', domain="[('company_id', '=', company_id)]", tracking=True)
    vat_mushak_number = fields.Char(string='Mushak No.', readonly=True, copy=False, index=True, tracking=True)
    vat_document_type = fields.Selection([('63', 'Mushak 6.3 Tax Invoice'), ('67', 'Mushak 6.7 Credit Note'), ('68', 'Mushak 6.8 Debit Note'), ('other', 'Other')], compute='_compute_vat_document_type', store=True)
    vat_supply_type = fields.Selection([('taxable', 'Taxable'), ('zero', 'Zero Rated'), ('exempt', 'Exempt'), ('export', 'Export'), ('import', 'Import')], default='taxable', required=True)
    vat_taxable_amount = fields.Monetary(compute='_compute_vat_amounts', store=True, currency_field='currency_id')
    vat_output_amount = fields.Monetary(compute='_compute_vat_amounts', store=True, currency_field='currency_id')
    vat_input_amount = fields.Monetary(compute='_compute_vat_amounts', store=True, currency_field='currency_id')
    vat_sd_amount = fields.Monetary(compute='_compute_vat_amounts', store=True, currency_field='currency_id')
    vat_vds_rate = fields.Float(string='VDS Rate %')
    vat_vds_amount = fields.Monetary(compute='_compute_vds_amount', store=True, currency_field='currency_id')
    vat_vds_certificate_ids = fields.One2many('vat.vds.certificate', 'move_id', string='VDS Certificates')
    vat_original_move_id = fields.Many2one('account.move', string='Original Tax Invoice', ondelete='restrict')
    vat_adjustment_reason = fields.Text(string='VAT Adjustment / Cancellation Reason')
    vat_export_reference = fields.Char(string='Export LC / Bill of Export')
    vat_import_bill_of_entry = fields.Char(string='Bill of Entry No.')
    vat_import_bill_date = fields.Date(string='Bill of Entry Date')
    vat_vds_reverse_charge = fields.Boolean(string='Reverse Charge / VDS Liability')
    vat_input_credit_status = fields.Selection([('creditable', 'Creditable'), ('non_creditable', 'Non-creditable'), ('partial', 'Partial')], default='creditable')
    vat_is_high_value = fields.Boolean(compute='_compute_vat_amounts', store=True)

    @api.depends('move_type', 'reversed_entry_id')
    def _compute_vat_document_type(self):
        for move in self:
            if move.move_type == 'out_invoice':
                move.vat_document_type = '63'
            elif move.move_type == 'out_refund':
                move.vat_document_type = '67'
            elif move.move_type == 'in_refund':
                move.vat_document_type = '68'
            else:
                move.vat_document_type = 'other'

    @api.depends('invoice_line_ids.price_subtotal', 'invoice_line_ids.tax_ids', 'invoice_line_ids.quantity', 'invoice_line_ids.price_unit', 'invoice_line_ids.vat_input_credit_status', 'invoice_line_ids.vat_partial_credit_percent', 'invoice_line_ids.vat_capital_credit_treatment', 'move_type', 'currency_id', 'company_id')
    def _compute_vat_amounts(self):
        for move in self:
            taxable = output = input_amount = sd = 0.0
            sign = -1 if move.move_type in ('out_refund', 'in_refund') else 1
            for line in move.invoice_line_ids.filtered(lambda l: not l.display_type):
                taxable += line.price_subtotal * sign
                line_tax, line_sd = line._vat_tax_components()
                sd += line_sd * sign
                if move.move_type.startswith('out_'):
                    output += line_tax * sign
                else:
                    input_amount += line._vat_eligible_input_amount() * sign
            move.vat_taxable_amount = taxable
            move.vat_output_amount = output
            move.vat_input_amount = input_amount
            move.vat_sd_amount = sd
            move.vat_is_high_value = abs(move.amount_total) > move.company_id.vat_high_value_threshold

    @api.depends('vat_taxable_amount', 'vat_vds_rate')
    def _compute_vds_amount(self):
        for move in self:
            move.vat_vds_amount = move.vat_taxable_amount * move.vat_vds_rate / 100

    @api.onchange('partner_id')
    def _onchange_vat_partner(self):
        if self.partner_id:
            self.vat_vds_rate = self.partner_id.vat_vds_rate
            if self.move_type in ('in_invoice', 'in_refund') and self.partner_id.vat_registration_status == 'unregistered':
                self.vat_vds_reverse_charge = True

    @api.onchange('invoice_line_ids')
    def _onchange_vat_lines(self):
        rates = self.invoice_line_ids.mapped('product_id.product_tmpl_id.vat_vds_rate')
        if rates and not self.vat_vds_rate:
            self.vat_vds_rate = max(rates)

    def _check_vat_period_open(self):
        Period = self.env['vat.period']
        for move in self:
            move_date = move.invoice_date or move.date
            if not move_date:
                continue
            domain = [('company_id', '=', move.company_id.id), ('date_start', '<=', move_date), ('date_end', '>=', move_date), ('state', '=', 'locked')]
            if move.vat_unit_id:
                domain.append(('unit_id', '=', move.vat_unit_id.id))
            if Period.search_count(domain):
                raise UserError(_('The VAT period for %s is locked. Reopen it through a VAT Manager before posting.') % move_date)

    def _check_price_declarations(self):
        for move in self.filtered(lambda m: m.move_type == 'out_invoice'):
            for line in move.invoice_line_ids.filtered(lambda l: l.product_id and not l.display_type):
                product = line.product_id.product_tmpl_id
                declaration = self.env['vat.price.declaration'].search([('product_tmpl_id', '=', product.id), ('state', '=', 'approved'), ('effective_date', '<=', move.invoice_date or fields.Date.context_today(self))], order='effective_date desc', limit=1)
                if declaration and line.price_unit < declaration.declared_price and (product.vat_price_policy == 'block' or move.company_id.vat_enforce_declared_price):
                    raise ValidationError(_('Line %s is below its declared price (%s).') % (product.display_name, declaration.declared_price))

    def action_post(self):
        self._check_vat_period_open()
        self._check_price_declarations()
        self._vat_validate_purchase_compliance()
        result = super().action_post()
        for move in self:
            if move.move_type in ('out_invoice', 'out_refund', 'in_refund') and not move.vat_mushak_number:
                doc_type = move.vat_document_type
                if doc_type in ('63', '67', '68'):
                    move.vat_mushak_number = self.env['vat.document.series'].next_number(
                        doc_type, move.company_id, move.vat_unit_id, move.invoice_date or move.date,
                    )
            if move.vat_vds_rate and move.vat_vds_amount and not move.vat_vds_certificate_ids:
                direction = 'deducted' if move.move_type in ('in_invoice', 'in_refund') else 'suffered'
                self.env['vat.vds.certificate'].sudo().create({'company_id': move.company_id.id, 'unit_id': move.vat_unit_id.id, 'partner_id': move.partner_id.id, 'move_id': move.id, 'direction': direction, 'base_amount': abs(move.vat_taxable_amount), 'rate': move.vat_vds_rate})
        self._vat_create_capital_credit_schedules()
        return result

    def action_print_mushak_63(self):
        self.ensure_one()
        if self.vat_document_type not in ('63', '67', '68'):
            raise UserError(_('Mushak documents are available only for VAT invoices and notes.'))
        return mushak_report_action(self, self.vat_document_type)
