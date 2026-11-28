from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from .mushak_report import mushak_report_action


class AccountMove(models.Model):
    _inherit = 'account.move'

    vat_unit_id = fields.Many2one('vat.unit', string='VAT Unit', domain="[('company_id', '=', company_id)]", tracking=True)
    vat_mushak_number = fields.Char(string='Mushak No.', readonly=True, copy=False, index=True, tracking=True)
    vat_document_type = fields.Selection([('63', 'Mushak 6.3 Tax Invoice'), ('67', 'Mushak 6.7 Credit Note'), ('68', 'Mushak 6.8 Debit Note'), ('other', 'Other')], compute='_compute_vat_document_type', store=True)
    vat_qr_payload = fields.Char(string='Mushak QR Payload', readonly=True, copy=False)
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
    vat_cancellation_reason = fields.Text(string='Cancellation Request Reason', copy=False, tracking=True)
    vat_cancellation_state = fields.Selection([
        ('none', 'Not Requested'), ('requested', 'Requested'),
        ('approved', 'Approved'), ('rejected', 'Rejected'),
    ], default='none', copy=False, tracking=True)
    vat_cancellation_approver_id = fields.Many2one('res.users', readonly=True, copy=False)
    vat_cancellation_approval_date = fields.Datetime(readonly=True, copy=False)
    vat_print_count = fields.Integer(default=0, readonly=True, copy=False)
    vat_export_reference = fields.Char(string='Export LC / Bill of Export')
    vat_import_bill_of_entry = fields.Char(string='Bill of Entry No.')
    vat_import_bill_date = fields.Date(string='Bill of Entry Date')
    vat_vds_reverse_charge = fields.Boolean(string='Reverse Charge / VDS Liability')
    vat_input_credit_status = fields.Selection([('creditable', 'Creditable'), ('non_creditable', 'Non-creditable'), ('partial', 'Partial')], default='creditable')
    vat_is_high_value = fields.Boolean(compute='_compute_vat_amounts', store=True)

    _vat_immutable_fields = {
        'name', 'move_type', 'partner_id', 'invoice_date', 'date', 'currency_id',
        'invoice_line_ids', 'vat_unit_id', 'vat_mushak_number', 'vat_document_type',
        'vat_supply_type', 'vat_original_move_id', 'vat_adjustment_reason',
        'vat_vds_rate', 'vat_vds_reverse_charge', 'vat_input_credit_status',
        'vat_export_reference', 'vat_import_bill_of_entry', 'vat_import_bill_date',
        'vat_reverse_charge_rate', 'vat_reverse_charge_payment_id', 'state',
    }

    @api.model_create_multi
    def create(self, vals_list):
        if any({'vat_mushak_number', 'vat_qr_payload'} & set(vals) for vals in vals_list):
            raise UserError(_('Mushak numbers and QR payloads are generated only when a document is posted.'))
        # Sales/purchase documents created from an order do not open the VAT
        # tab, so the user has no opportunity to choose the unit manually.
        # Where the company operates a single VAT unit, make that unambiguous
        # choice automatically.  Multi-unit companies still have to select a
        # unit explicitly.
        VatUnit = self.env['vat.unit']
        for vals in vals_list:
            if vals.get('vat_unit_id'):
                continue
            company_id = vals.get('company_id') or self.env.company.id
            units = VatUnit.search([('company_id', '=', company_id)], limit=2)
            if len(units) == 1:
                vals['vat_unit_id'] = units.id
        return super().create(vals_list)

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

    @api.depends(
        'invoice_line_ids', 'invoice_line_ids.display_type',
        'invoice_line_ids.price_subtotal', 'invoice_line_ids.tax_ids',
        'invoice_line_ids.quantity', 'invoice_line_ids.price_unit',
        'invoice_line_ids.product_id',
        'invoice_line_ids.vat_import_sd_amount', 'invoice_line_ids.vat_import_vat_amount',
        'invoice_line_ids.vat_input_credit_status',
        'invoice_line_ids.vat_partial_credit_percent',
        'invoice_line_ids.vat_capital_credit_treatment',
        'move_type', 'currency_id', 'amount_total',
        'company_id.vat_high_value_threshold',
    )
    def _compute_vat_amounts(self):
        for move in self:
            taxable = output = input_amount = sd = 0.0
            sign = -1 if move.move_type in ('out_refund', 'in_refund') else 1
            for line in move.invoice_line_ids.filtered(lambda l: l.display_type == 'product'):
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
            for line in move.invoice_line_ids.filtered(lambda l: l.display_type == 'product' and l.product_id):
                product = line.product_id.product_tmpl_id
                declaration = self.env['vat.price.declaration'].search([('product_tmpl_id', '=', product.id), ('state', '=', 'approved'), ('effective_date', '<=', move.invoice_date or fields.Date.context_today(self))], order='effective_date desc', limit=1)
                if declaration and line.price_unit < declaration.declared_price and (product.vat_price_policy == 'block' or move.company_id.vat_enforce_declared_price):
                    raise ValidationError(_('Line %s is below its declared price (%s).') % (product.display_name, declaration.declared_price))

    def action_post(self):
        # Covers draft invoices created before the automatic default above was
        # introduced.  It must happen before the Mushak serial is issued.
        for move in self.filtered(lambda item: not item.vat_unit_id):
            units = self.env['vat.unit'].search([
                ('company_id', '=', move.company_id.id),
            ], limit=2)
            if len(units) == 1:
                move.vat_unit_id = units.id
        self._check_vat_period_open()
        self._check_price_declarations()
        self._vat_validate_purchase_compliance()
        result = super().action_post()
        for move in self:
            # Account move lines are finalized while posting.  Explicitly
            # recompute here so stored VAT values cannot retain the temporary
            # values calculated before their display type became ``product``.
            move._compute_vat_amounts()
            move._compute_vat_reverse_charge()
            if move.move_type in ('out_invoice', 'out_refund', 'in_refund') and not move.vat_mushak_number:
                doc_type = move.vat_document_type
                if doc_type in ('63', '67', '68'):
                    move.with_context(vat_issue_number=True).write({
                        'vat_mushak_number': self.env['vat.document.series'].next_number(
                            doc_type, move.company_id, move.vat_unit_id, move.invoice_date or move.date,
                        ),
                    })
            if move.vat_mushak_number and not move.vat_qr_payload:
                move.with_context(vat_issue_number=True).write({'vat_qr_payload': '|'.join((
                    'BIN:%s' % (move.company_id.vat_bin or ''),
                    'MUSHAK:%s' % move.vat_mushak_number,
                    'INVOICE:%s' % move.name,
                    'DATE:%s' % (move.invoice_date or move.date or ''),
                    'TOTAL:%s' % move.amount_total,
                ))})
            if move.vat_vds_rate and move.vat_vds_amount and not move.vat_vds_certificate_ids:
                direction = 'deducted' if move.move_type in ('in_invoice', 'in_refund') else 'suffered'
                self.env['vat.vds.certificate'].sudo().create({'company_id': move.company_id.id, 'unit_id': move.vat_unit_id.id, 'partner_id': move.partner_id.id, 'move_id': move.id, 'direction': direction, 'base_amount': abs(move.vat_taxable_amount), 'rate': move.vat_vds_rate})
        self._vat_create_capital_credit_schedules()
        return result

    def action_print_mushak_63(self):
        self.ensure_one()
        if self.vat_document_type not in ('63', '67', '68'):
            raise UserError(_('Mushak documents are available only for VAT invoices and notes.'))
        if not self.vat_mushak_number:
            raise UserError(_('Only an issued Mushak document can be printed.'))
        is_copy = bool(self.vat_print_count)
        self.write({'vat_print_count': self.vat_print_count + 1})
        self.message_post(body=_('Mushak document printed%s by %s.') % (
            _(' again (COPY)') if is_copy else '', self.env.user.display_name,
        ))
        form_code = '6.%s' % self.vat_document_type[1:]
        # Do not pass ``vat_copy`` through report ``data``.  In Odoo 19, a
        # non-empty ``data`` payload makes the web client use the particular
        # report URL (without ``active_ids``).  The QWeb renderer then receives
        # no invoice in ``docs`` and wkhtmltopdf produces a blank PDF.  Context
        # preserves the flag while keeping the invoice id in the report URL.
        return mushak_report_action(
            self.with_context(vat_copy=is_copy), form_code,
        )

    @staticmethod
    def _format_hs_vat_rate(rate):
        """Format decimal HS VAT ratio (e.g. 0.03 -> '3%'), or '-' if zero."""
        if not rate or rate <= 0:
            return '-'
        formatted = ('%.4f' % (rate * 100.0)).rstrip('0').rstrip('.')
        return f'{formatted}%'

    def _mushak_63_report_data(self):
        """Return precomputed product rows and summary totals for Mushak 6.3."""
        self.ensure_one()
        currency = self.currency_id or self.company_id.currency_id
        round_amt = currency.round if currency else (lambda amount: round(amount, 2))
        rows = []
        total_subtotal = 0.0
        total_sd = 0.0
        total_vat = 0.0
        total_inclusive = 0.0
        product_lines = self.invoice_line_ids.filtered(lambda line: line.display_type == 'product')
        for index, line in enumerate(product_lines, start=1):
            base_amount = line.price_subtotal or 0.0
            sd_amount = line._vat_tax_components()[1] or 0.0
            hs_code = line.product_id.product_tmpl_id.hs_code_id
            vat_rate = hs_code.vat if (hs_code and hs_code.vat and hs_code.vat > 0) else 0.0
            vat_amount = round_amt((base_amount + sd_amount) * vat_rate) if vat_rate else 0.0
            total_inclusive_line = round_amt(base_amount + sd_amount + vat_amount)
            rows.append({
                'sl': index,
                'description': line.product_id.display_name or line.name or '',
                'uom': line.product_uom_id.name or '',
                'quantity': line.quantity,
                'price_unit': line.price_unit,
                'price_subtotal': base_amount,
                'sd_amount': sd_amount,
                'vat_rate_display': self._format_hs_vat_rate(vat_rate),
                'vat_amount': vat_amount,
                'total_inclusive': total_inclusive_line,
            })
            total_subtotal += base_amount
            total_sd += sd_amount
            total_vat += vat_amount
            total_inclusive += total_inclusive_line
        return {
            'rows': rows,
            'totals': {
                'price_subtotal': round_amt(total_subtotal),
                'sd_amount': round_amt(total_sd),
                'vat_amount': round_amt(total_vat),
                'total_inclusive': round_amt(total_inclusive),
            },
        }

    def write(self, vals):
        if ({'vat_mushak_number', 'vat_qr_payload'} & set(vals)
                and not self.env.context.get('vat_issue_number')):
            raise UserError(_('Mushak numbers and QR payloads are assigned only when a document is posted.'))
        if not self.env.context.get('vat_cancellation_approved'):
            protected = self.filtered(lambda move: move.state == 'posted' and move.vat_mushak_number)
            if protected and (
                self._vat_immutable_fields.intersection(vals)
                or ('vat_qr_payload' in vals and protected.filtered('vat_qr_payload'))
            ):
                raise UserError(_('An issued Mushak invoice or note is immutable. Use an approved cancellation or a credit/debit note.'))
        # Allow writes triggered by the parent move when only non-immutable fields are changed.
        if not self._vat_immutable_fields.intersection(vals):
            return super(AccountMove, self.with_context(vat_move_write_approved=True)).write(vals)
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda move: move.vat_mushak_number and move.state in ('posted', 'cancel')):
            raise UserError(_('An issued Mushak invoice or note cannot be deleted.'))
        return super().unlink()

    def button_draft(self):
        if not self.env.context.get('vat_cancellation_approved') and self.filtered(
            lambda move: move.state == 'posted' and move.vat_mushak_number
        ):
            raise UserError(_('An issued Mushak invoice or note cannot be reset to draft. Request an approved cancellation.'))
        return super().button_draft()

    def button_cancel(self):
        if self.env.context.get('vat_cancellation_approved'):
            return super().button_cancel()
        issued = self.filtered(lambda move: move.state == 'posted' and move.vat_mushak_number)
        other_moves = self - issued
        if issued:
            if any(move.vat_cancellation_state == 'requested' for move in issued):
                raise UserError(_('A cancellation request is already awaiting approval.'))
            if any(not (move.vat_cancellation_reason or '').strip() for move in issued):
                raise UserError(_('Enter a cancellation reason before requesting cancellation.'))
            issued.write({'vat_cancellation_state': 'requested'})
            for move in issued:
                move.message_post(body=_('Cancellation requested by %s: %s') % (
                    self.env.user.display_name, move.vat_cancellation_reason,
                ))
        if other_moves:
            return super(AccountMove, other_moves).button_cancel()
        return True

    def action_approve_vat_cancellation(self):
        if not self.env.user.has_group('zsl_vat.group_vat_manager'):
            raise UserError(_('Only a VAT Manager can approve an invoice cancellation.'))
        for move in self:
            if move.state != 'posted' or move.vat_cancellation_state != 'requested':
                raise UserError(_('Only a posted invoice with a pending cancellation request can be approved.'))
            move.with_context(vat_cancellation_approved=True).button_cancel()
            move.with_context(vat_cancellation_approved=True).write({
                'vat_cancellation_state': 'approved',
                'vat_cancellation_approver_id': self.env.user.id,
                'vat_cancellation_approval_date': fields.Datetime.now(),
            })
            move.message_post(body=_('Cancellation approved by %s. Mushak number %s is retained.') % (
                self.env.user.display_name, move.vat_mushak_number,
            ))
        return True


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    # An issued Mushak locks the commercial and tax content of a line.  It
    # must still let Odoo update computed/reconciliation bookkeeping fields:
    # rendering the standard invoice PDF, for example, refreshes ``parent_id``
    # and several dynamic-line cache flags.  Blocking every write here broke
    # printing and could also prevent legitimate payment reconciliation.
    _vat_immutable_line_fields = {
        'account_id', 'amount_currency', 'analytic_distribution', 'balance',
        'credit', 'currency_id', 'date', 'debit', 'discount', 'display_type',
        'group_tax_id', 'name', 'partner_id', 'price_unit', 'product_id',
        'product_uom_id', 'quantity', 'sequence', 'tax_ids', 'tax_line_id',
        'tax_tag_ids',
        # Bangladesh VAT values recorded on the bill line.
        'vat_import_cd_amount', 'vat_import_rd_amount',
        'vat_import_sd_amount', 'vat_import_vat_amount',
        'vat_import_ait_amount', 'vat_import_at_amount',
        'vat_input_credit_status', 'vat_partial_credit_percent',
        'vat_credit_reason', 'vat_credit_legal_reference',
        'vat_capital_credit_treatment', 'vat_deferred_months',
    }

    def write(self, vals):
        changing_issued_content = self._vat_immutable_line_fields.intersection(vals)
        if changing_issued_content and not self.env.context.get('vat_cancellation_approved') and not self.env.context.get('vat_move_write_approved') and self.filtered(
            lambda line: line.move_id.state == 'posted' and line.move_id.vat_mushak_number
        ):
            raise UserError(_('Lines on an issued Mushak invoice or note cannot be edited.'))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda line: line.move_id.vat_mushak_number and line.move_id.state in ('posted', 'cancel')):
            raise UserError(_('Lines on an issued Mushak invoice or note cannot be deleted.'))
        return super().unlink()
