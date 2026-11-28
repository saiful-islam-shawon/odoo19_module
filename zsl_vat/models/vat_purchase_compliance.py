from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


INPUT_CREDIT_STATUS = [
    ('creditable', 'Creditable'),
    ('non_creditable', 'Non-creditable'),
    ('partial', 'Partially Creditable'),
]


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    # These are a snapshot of the HS-code import calculation.  They are
    # written when the vendor bill is posted, so a later HS tariff amendment
    # cannot alter an already-issued VAT book.
    vat_import_cd_amount = fields.Monetary(string='Import CD', currency_field='currency_id', copy=False, readonly=True)
    vat_import_rd_amount = fields.Monetary(string='Import RD', currency_field='currency_id', copy=False, readonly=True)
    vat_import_sd_amount = fields.Monetary(string='Import SD', currency_field='currency_id', copy=False, readonly=True)
    vat_import_vat_amount = fields.Monetary(string='Import VAT', currency_field='currency_id', copy=False, readonly=True)
    vat_import_ait_amount = fields.Monetary(string='Import AIT', currency_field='currency_id', copy=False, readonly=True)
    vat_import_at_amount = fields.Monetary(string='Import AT', currency_field='currency_id', copy=False, readonly=True)

    vat_input_credit_status = fields.Selection(
        INPUT_CREDIT_STATUS, string='Input VAT Eligibility', default='creditable',
        help='Only the eligible part is included in the VAT return input-tax rebate.'
    )
    vat_partial_credit_percent = fields.Float(string='Eligible %', default=100.0)
    vat_credit_reason = fields.Char(string='Eligibility Reason')
    vat_credit_legal_reference = fields.Char(string='Credit Legal Reference / SRO')
    vat_is_capital_good = fields.Boolean(related='product_id.product_tmpl_id.vat_is_capital_good', readonly=True)
    vat_capital_credit_treatment = fields.Selection([
        ('full', 'Full Credit'), ('deferred', 'Deferred Credit'), ('non_creditable', 'Non-creditable'),
    ], string='Capital Asset Credit Treatment', default='full')
    vat_deferred_months = fields.Integer(string='Deferred Credit Months', default=1)

    def _uses_hs_tariff_assessment(self):
        """Whether this purchase line carries an import-duty assessment.

        A purchase order can show CD/RD/SD/VAT from its product HS code even
        when the bill was created before the user selected ``Import`` on the
        VAT tab.  Those assessed lines must still carry their SD and VAT into
        the purchase book; otherwise the PO screen and Mushak 6.1 disagree.
        """
        self.ensure_one()
        code = self.product_id.product_tmpl_id.hs_code_id
        return bool(code and any((
            code.cd, code.rd, code.sd, code.vat, code.ait, code.at,
        )))

    def _vat_import_duty_values(self):
        """Return the tariff assessment for one bill line.

        The calculation mirrors the HS-duty preview on the purchase order:
        each configured rate is assessed on the line's basic value.  This
        keeps vendor bill and Mushak 6.1 values identical to the PO.
        """
        self.ensure_one()
        code = self.product_id.product_tmpl_id.hs_code_id
        base = self.price_subtotal if self.display_type == 'product' else 0.0
        cd = base * (code.cd or 0.0)
        rd = base * (code.rd or 0.0)
        return {
            'vat_import_cd_amount': cd,
            'vat_import_rd_amount': rd,
            'vat_import_sd_amount': base * (code.sd or 0.0),
            'vat_import_vat_amount': base * (code.vat or 0.0),
            'vat_import_ait_amount': base * (code.ait or 0.0),
            'vat_import_at_amount': base * (code.at or 0.0),
        }

    @api.onchange('product_id', 'quantity', 'price_unit', 'discount')
    def _onchange_vat_import_duty_values(self):
        for line in self:
            if line.product_id and (
                line.move_id.vat_supply_type == 'import'
                or line._uses_hs_tariff_assessment()
            ):
                line.update(line._vat_import_duty_values())

    @api.onchange('product_id')
    def _onchange_vat_product_credit_policy(self):
        for line in self:
            if line.product_id:
                line.vat_input_credit_status = line.product_id.product_tmpl_id.vat_input_credit
                if line.product_id.product_tmpl_id.vat_is_capital_good:
                    line.vat_capital_credit_treatment = 'full'

    @api.constrains('vat_partial_credit_percent', 'vat_deferred_months', 'vat_capital_credit_treatment')
    def _check_vat_credit_values(self):
        for line in self:
            if not 0 <= line.vat_partial_credit_percent <= 100:
                raise ValidationError(_('Eligible percentage must be between 0 and 100.'))
            if line.vat_capital_credit_treatment == 'deferred' and line.vat_deferred_months < 2:
                raise ValidationError(_('Deferred capital input credit must be spread over at least two months.'))

    def _vat_tax_components(self):
        """Return VAT-input and SD amounts from the taxes of one invoice line."""
        self.ensure_one()
        if self.display_type != 'product' or not self.product_id:
            return 0.0, 0.0
        move = self.move_id
        # Import VAT and SD are customs-assessed values, not ordinary vendor
        # invoice taxes.  Use the posted tariff snapshot; while the bill is
        # still a draft, calculate a live preview from its product HS code.
        if move.vat_supply_type == 'import' or self._uses_hs_tariff_assessment():
            # A non-zero posted snapshot is authoritative.  Old posted bills
            # created before this integration have no snapshot, so calculate
            # from the linked HS code as a backward-compatible fallback.
            has_snapshot = any((
                self.vat_import_cd_amount, self.vat_import_rd_amount,
                self.vat_import_sd_amount, self.vat_import_vat_amount,
                self.vat_import_ait_amount, self.vat_import_at_amount,
            ))
            values = (
                {
                    'vat_import_vat_amount': self.vat_import_vat_amount,
                    'vat_import_sd_amount': self.vat_import_sd_amount,
                }
                if move.state == 'posted' and has_snapshot
                else self._vat_import_duty_values()
            )
            return values['vat_import_vat_amount'], values['vat_import_sd_amount']
        results = self.tax_ids.compute_all(
            self.price_unit * (1 - (self.discount or 0.0) / 100.0), currency=move.currency_id, quantity=self.quantity,
            product=self.product_id, partner=move.partner_id,
        ).get('taxes', [])
        input_tax = sd = 0.0
        product = self.product_id.product_tmpl_id
        for result in results:
            tax = self.env['account.tax'].browse(result['id'])
            tax_date = move.invoice_date or move.date or fields.Date.context_today(self)
            code_domain = []
            if product.vat_hs_code_id:
                code_domain.append(('hs_code_id', '=', product.vat_hs_code_id.id))
            if product.hs_code_id:
                code_domain.append(('zencore_hs_code_id', '=', product.hs_code_id.id))
            if not code_domain:
                continue
            if len(code_domain) == 2:
                code_domain = ['|', *code_domain]
            rules = self.env['vat.tax.rule'].search([
                ('account_tax_id', '=', tax.id),
                ('active', '=', True),
                ('purchase_applicable' if move.move_type.startswith('in_') else 'sale_applicable', '=', True),
                ('date_from', '<=', tax_date),
                '|', ('date_to', '=', False), ('date_to', '>=', tax_date),
                *code_domain,
            ])
            heads = set(rules.mapped('tax_head'))
            # Only explicitly mapped VAT and SD belong in these two figures.
            # Import duties, AIT, AT, VDS, and TDS must not be counted as input VAT.
            if 'vat' in heads:
                input_tax += result['amount']
            elif 'sd' in heads:
                sd += result['amount']
        return input_tax, sd

    def _vat_eligible_input_amount(self):
        self.ensure_one()
        tax_amount, _sd = self._vat_tax_components()
        if self.vat_input_credit_status == 'non_creditable':
            return 0.0
        if self.vat_is_capital_good and self.vat_capital_credit_treatment in ('deferred', 'non_creditable'):
            return 0.0
        if self.vat_input_credit_status == 'partial':
            return tax_amount * self.vat_partial_credit_percent / 100.0
        return tax_amount


class AccountMovePurchaseCompliance(models.Model):
    _inherit = 'account.move'

    vat_supplier_document_number = fields.Char(string='Supplier Mushak 6.3 / Challan No.', copy=False)
    vat_supplier_document_date = fields.Date(string='Supplier Mushak / Challan Date', copy=False)
    vat_supplier_document_id = fields.Many2one('ir.attachment', string='Supplier Mushak / Challan Copy', copy=False, ondelete='restrict')
    vat_import_declaration_id = fields.Many2one('vat.import.declaration', string='Import Declaration', copy=False, ondelete='restrict')
    vat_reverse_charge_rate = fields.Float(string='Reverse Charge VAT Rate %')
    vat_reverse_charge_amount = fields.Monetary(compute='_compute_vat_reverse_charge', store=True, currency_field='currency_id')
    vat_reverse_charge_payment_id = fields.Many2one('vat.treasury.payment', string='Reverse-charge Treasury Payment', copy=False, ondelete='restrict')
    vat_is_unregistered_purchase = fields.Boolean(compute='_compute_vat_purchase_flags', store=True)
    vat_is_imported_service = fields.Boolean(compute='_compute_vat_purchase_flags', store=True)
    vat_capital_schedule_ids = fields.One2many('vat.capital.credit.schedule', 'move_id', string='Capital Input Credit Schedules')

    @api.depends('partner_id.vat_registration_status', 'move_type', 'invoice_line_ids.product_id.type')
    def _compute_vat_purchase_flags(self):
        for move in self:
            is_purchase = move.move_type in ('in_invoice', 'in_refund')
            move.vat_is_unregistered_purchase = bool(is_purchase and move.partner_id.vat_registration_status == 'unregistered')
            move.vat_is_imported_service = bool(
                is_purchase and move.partner_id.vat_registration_status == 'foreign'
                and any(line.product_id.type == 'service' for line in move.invoice_line_ids if line.display_type == 'product')
            )

    @api.depends('vat_taxable_amount', 'vat_vds_reverse_charge', 'vat_reverse_charge_rate')
    def _compute_vat_reverse_charge(self):
        for move in self:
            move.vat_reverse_charge_amount = (
                abs(move.vat_taxable_amount) * move.vat_reverse_charge_rate / 100.0
                if move.vat_vds_reverse_charge else 0.0
            )

    @api.onchange('partner_id', 'invoice_line_ids')
    def _onchange_vat_reverse_charge_rate(self):
        for move in self:
            if move.vat_is_unregistered_purchase or move.vat_is_imported_service:
                move.vat_vds_reverse_charge = True
                if not move.vat_reverse_charge_rate:
                    tax_rates = move.invoice_line_ids.mapped('tax_ids').mapped('amount')
                    move.vat_reverse_charge_rate = max(tax_rates) if tax_rates else 0.0

    @api.onchange('vat_supply_type')
    def _onchange_vat_import_duties(self):
        for move in self:
            if move.vat_supply_type == 'import':
                for line in move.invoice_line_ids.filtered(lambda item: item.display_type == 'product' and item.product_id):
                    line.update(line._vat_import_duty_values())

    def _snapshot_vat_import_duties(self):
        for move in self.filtered(lambda item: item.move_type in ('in_invoice', 'in_refund')):
            assessed_lines = move.invoice_line_ids.filtered(
                lambda item: item.display_type == 'product' and item.product_id and (
                    move.vat_supply_type == 'import' or item._uses_hs_tariff_assessment()
                )
            )
            for line in assessed_lines:
                line.write(line._vat_import_duty_values())

    def action_post(self):
        # Freeze the assessed duty values before the parent posting flow
        # computes VAT totals and makes the accounting document immutable.
        self._snapshot_vat_import_duties()
        return super().action_post()

    def _vat_validate_purchase_compliance(self):
        for move in self.filtered(lambda item: item.move_type in ('in_invoice', 'in_refund')):
            taxable_lines = move.invoice_line_ids.filtered(lambda line: line.display_type == 'product' and line.product_id)
            if not taxable_lines:
                continue
            if move.vat_supply_type == 'import' and not (move.vat_import_bill_of_entry and move.vat_import_bill_date):
                raise ValidationError(_('Enter the Bill of Entry number and date before posting an import purchase bill.'))
            if move.partner_id.vat_registration_status == 'registered' and move.vat_supply_type != 'import':
                if not move.partner_id.vat_bin:
                    raise ValidationError(_('A registered supplier must have a VAT BIN before its bill can be posted.'))
                if not move.vat_supplier_document_number or not move.vat_supplier_document_date:
                    raise ValidationError(_('Enter the supplier Mushak 6.3/challan number and date before posting a purchase bill.'))
            for line in taxable_lines:
                product = line.product_id.product_tmpl_id
                if not (product.hs_code_id or product.vat_hs_code_id):
                    raise ValidationError(_('%s has no HS/service code.') % product.display_name)
                if (line.vat_input_credit_status in ('creditable', 'partial')
                        and not move.vat_supplier_document_id
                        and move.partner_id.vat_registration_status == 'registered'
                        and move.vat_supply_type != 'import'):
                    raise ValidationError(_('Attach the supplier Mushak/challan copy before claiming input VAT.'))
            if move.move_type == 'in_refund':
                if not (move.reversed_entry_id or move.vat_original_move_id):
                    raise ValidationError(_('A purchase return/debit note must reference the original purchase bill.'))
                if not move.vat_adjustment_reason:
                    raise ValidationError(_('Enter the reason for the purchase return/debit note.'))
            if (move.vat_is_unregistered_purchase or move.vat_is_imported_service) and move.vat_vds_reverse_charge:
                if move.vat_reverse_charge_rate <= 0:
                    raise ValidationError(_('Set a positive reverse-charge VAT rate for this purchase.'))

    def _vat_create_capital_credit_schedules(self):
        Schedule = self.env['vat.capital.credit.schedule']
        for move in self.filtered(lambda item: item.move_type == 'in_invoice' and item.state == 'posted'):
            for line in move.invoice_line_ids.filtered(lambda item: item.display_type == 'product' and item.vat_is_capital_good and item.vat_capital_credit_treatment == 'deferred'):
                if not Schedule.search_count([('move_line_id', '=', line.id)]):
                    tax_amount, _sd = line._vat_tax_components()
                    credit = tax_amount * (line.vat_partial_credit_percent / 100.0 if line.vat_input_credit_status == 'partial' else 1.0)
                    if credit:
                        Schedule.create({
                            'move_id': move.id, 'move_line_id': line.id, 'company_id': move.company_id.id,
                            'unit_id': move.vat_unit_id.id, 'product_id': line.product_id.id,
                            'total_credit_amount': credit, 'deferred_months': line.vat_deferred_months,
                            'start_date': move.invoice_date or fields.Date.context_today(self),
                            'legal_reference': line.vat_credit_legal_reference,
                        }).action_confirm()


class VatImportDeclaration(models.Model):
    _name = 'vat.import.declaration'
    _description = 'VAT Import / Bill of Entry'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'bill_of_entry_date desc, id desc'

    name = fields.Char(required=True, default=lambda self: _('New'), readonly=True, copy=False)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    unit_id = fields.Many2one('vat.unit', required=True, domain="[('company_id', '=', company_id)]")
    purchase_order_id = fields.Many2one('purchase.order', string='Purchase Order', ondelete='restrict')
    vendor_bill_id = fields.Many2one('account.move', string='Vendor Bill', domain="[('move_type', '=', 'in_invoice'), ('company_id', '=', company_id)]", ondelete='restrict')
    landed_cost_id = fields.Many2one('stock.landed.cost', string='Landed Cost', domain="[('company_id', '=', company_id)]", ondelete='restrict')
    bill_of_entry_number = fields.Char(required=True, copy=False)
    bill_of_entry_date = fields.Date(required=True)
    assessable_value = fields.Monetary(required=True, currency_field='currency_id')
    cd_amount = fields.Monetary(string='CD', currency_field='currency_id')
    rd_amount = fields.Monetary(string='RD', currency_field='currency_id')
    sd_amount = fields.Monetary(string='SD', currency_field='currency_id')
    vat_amount = fields.Monetary(string='Import VAT', currency_field='currency_id')
    at_amount = fields.Monetary(string='Advance Tax (AT)', currency_field='currency_id')
    ait_amount = fields.Monetary(string='AIT', currency_field='currency_id')
    customs_payment_reference = fields.Char(string='Customs Payment / Challan Reference')
    customs_evidence_id = fields.Many2one('ir.attachment', string='Bill of Entry / Customs Evidence', ondelete='restrict')
    state = fields.Selection([('draft', 'Draft'), ('confirmed', 'Confirmed'), ('cancelled', 'Cancelled')], default='draft', tracking=True)
    currency_id = fields.Many2one(related='company_id.currency_id')

    _bill_of_entry_unique = models.Constraint(
        'UNIQUE(company_id, bill_of_entry_number)',
        'Bill of Entry number must be unique per company.',
    )

    @api.constrains('assessable_value', 'cd_amount', 'rd_amount', 'sd_amount', 'vat_amount', 'at_amount', 'ait_amount')
    def _check_import_amounts(self):
        for record in self:
            if any(amount < 0 for amount in (record.assessable_value, record.cd_amount, record.rd_amount, record.sd_amount, record.vat_amount, record.at_amount, record.ait_amount)):
                raise ValidationError(_('Import assessable value and customs duties cannot be negative.'))

    def action_confirm(self):
        for record in self:
            if not record.customs_evidence_id:
                raise UserError(_('Attach the Bill of Entry/customs evidence before confirmation.'))
            if not (record.purchase_order_id or record.vendor_bill_id or record.landed_cost_id):
                raise UserError(_('Link the import to a purchase order, vendor bill, or landed cost.'))
            if record.vendor_bill_id:
                record.vendor_bill_id.write({
                    'vat_supply_type': 'import', 'vat_import_bill_of_entry': record.bill_of_entry_number,
                    'vat_import_bill_date': record.bill_of_entry_date,
                })
            if record.landed_cost_id:
                record.landed_cost_id.write({'vat_import_reference': record.bill_of_entry_number, 'vat_unit_id': record.unit_id.id})
                existing_types = record.landed_cost_id.vat_creditable_tax_line_ids.mapped('tax_type')
                values = []
                if record.vat_amount and 'vat' not in existing_types:
                    values.append((0, 0, {'tax_type': 'vat', 'amount': record.vat_amount, 'bill_of_entry': record.bill_of_entry_number, 'evidence_id': record.customs_evidence_id.id}))
                if record.at_amount and 'at' not in existing_types:
                    values.append((0, 0, {'tax_type': 'at', 'amount': record.at_amount, 'bill_of_entry': record.bill_of_entry_number, 'evidence_id': record.customs_evidence_id.id}))
                if values:
                    record.landed_cost_id.write({'vat_creditable_tax_line_ids': values})
            record.name = record.name if record.name != _('New') else self.env['ir.sequence'].next_by_code('zsl_vat.import_declaration') or _('New')
            record.state = 'confirmed'


class VatCapitalCreditSchedule(models.Model):
    _name = 'vat.capital.credit.schedule'
    _description = 'Capital Asset Input VAT Credit Schedule'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'start_date desc, id desc'

    name = fields.Char(required=True, default=lambda self: _('New'), readonly=True, copy=False)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    unit_id = fields.Many2one('vat.unit', domain="[('company_id', '=', company_id)]")
    move_id = fields.Many2one('account.move', required=True, ondelete='restrict')
    move_line_id = fields.Many2one('account.move.line', required=True, ondelete='restrict')
    product_id = fields.Many2one('product.product', required=True, ondelete='restrict')
    total_credit_amount = fields.Monetary(required=True, currency_field='currency_id')
    deferred_months = fields.Integer(required=True, default=2)
    start_date = fields.Date(required=True)
    legal_reference = fields.Char()
    line_ids = fields.One2many('vat.capital.credit.schedule.line', 'schedule_id', copy=False)
    state = fields.Selection([('draft', 'Draft'), ('confirmed', 'Confirmed'), ('cancelled', 'Cancelled')], default='draft', tracking=True)
    currency_id = fields.Many2one(related='company_id.currency_id')

    _capital_schedule_line_unique = models.Constraint('UNIQUE(move_line_id)', 'Only one capital input credit schedule is allowed for an invoice line.')

    def action_confirm(self):
        for schedule in self:
            if schedule.deferred_months < 2 or schedule.total_credit_amount <= 0:
                raise UserError(_('A deferred credit schedule needs a positive amount and at least two months.'))
            if not schedule.line_ids:
                amount = round(schedule.total_credit_amount / schedule.deferred_months, 2)
                remaining = schedule.total_credit_amount
                lines = []
                for index in range(schedule.deferred_months):
                    installment = remaining if index == schedule.deferred_months - 1 else amount
                    lines.append((0, 0, {'scheduled_date': schedule.start_date + relativedelta(months=index), 'amount': installment}))
                    remaining -= installment
                schedule.write({'line_ids': lines})
            schedule.write({
                'name': schedule.name if schedule.name != _('New') else self.env['ir.sequence'].next_by_code('zsl_vat.capital_credit') or _('New'),
                'state': 'confirmed',
            })


class VatCapitalCreditScheduleLine(models.Model):
    _name = 'vat.capital.credit.schedule.line'
    _description = 'Capital Asset Input VAT Credit Installment'
    _order = 'scheduled_date, id'

    schedule_id = fields.Many2one('vat.capital.credit.schedule', required=True, ondelete='cascade')
    scheduled_date = fields.Date(required=True)
    amount = fields.Monetary(required=True, currency_field='currency_id')
    return_id = fields.Many2one('vat.return', readonly=True, ondelete='restrict')
    state = fields.Selection([('pending', 'Pending'), ('claimed', 'Claimed'), ('cancelled', 'Cancelled')], default='pending', required=True)
    currency_id = fields.Many2one(related='schedule_id.currency_id')

