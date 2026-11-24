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
        if self.display_type or not self.product_id:
            return 0.0, 0.0
        move = self.move_id
        results = self.tax_ids.compute_all(
            self.price_unit, currency=move.currency_id, quantity=self.quantity,
            product=self.product_id, partner=move.partner_id,
        ).get('taxes', [])
        input_tax = sd = 0.0
        product = self.product_id.product_tmpl_id
        for result in results:
            tax = self.env['account.tax'].browse(result['id'])
            rules = self.env['vat.tax.rule'].search([
                ('account_tax_id', '=', tax.id),
                ('date_from', '<=', move.invoice_date or fields.Date.context_today(self)),
                '|', ('date_to', '=', False), ('date_to', '>=', move.invoice_date or fields.Date.context_today(self)),
                '|', ('hs_code_id', '=', product.vat_hs_code_id.id),
                ('zencore_hs_code_id', '=', product.hs_code_id.id),
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
                and any(line.product_id.type == 'service' for line in move.invoice_line_ids if not line.display_type)
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

    def _vat_validate_purchase_compliance(self):
        for move in self.filtered(lambda item: item.move_type in ('in_invoice', 'in_refund')):
            taxable_lines = move.invoice_line_ids.filtered(lambda line: not line.display_type and line.product_id)
            if not taxable_lines:
                continue
            if move.partner_id.vat_registration_status == 'registered':
                if not move.partner_id.vat_bin:
                    raise ValidationError(_('A registered supplier must have a VAT BIN before its bill can be posted.'))
                if not move.vat_supplier_document_number or not move.vat_supplier_document_date:
                    raise ValidationError(_('Enter the supplier Mushak 6.3/challan number and date before posting a purchase bill.'))
            for line in taxable_lines:
                product = line.product_id.product_tmpl_id
                if not (product.hs_code_id or product.vat_hs_code_id):
                    raise ValidationError(_('%s has no HS/service code.') % product.display_name)
                if line.vat_input_credit_status in ('creditable', 'partial') and not move.vat_supplier_document_id and move.partner_id.vat_registration_status == 'registered':
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
            for line in move.invoice_line_ids.filtered(lambda item: not item.display_type and item.vat_is_capital_good and item.vat_capital_credit_treatment == 'deferred'):
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

