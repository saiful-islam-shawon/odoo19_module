from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from .mushak_report import mushak_report_action


class ResCompany(models.Model):
    _inherit = 'res.company'

    vat_legal_name = fields.Char(string='VAT Legal Name')
    vat_trade_name = fields.Char(string='VAT Trade Name')
    vat_bin = fields.Char(string='Company VAT BIN')
    vat_legacy_bin = fields.Char(string='Legacy BIN')
    vat_tin = fields.Char(string='TIN')
    vat_circle = fields.Char(string='VAT Circle')
    vat_commissionerate = fields.Char(string='VAT Commissionerate')
    vat_business_nature = fields.Selection([('trading', 'Trading'), ('manufacturing', 'Manufacturing'), ('service', 'Service'), ('mixed', 'Mixed Business')], string='Business Nature')
    vat_registered_address = fields.Text(string='VAT Registered Address')
    vat_registration_date = fields.Date()
    vat_registration_type = fields.Selection([('standard', 'Standard VAT'), ('turnover', 'Turnover Tax'), ('other', 'Other')], default='standard')
    vat_return_due_day = fields.Integer(string='Monthly Return Due Day', default=15,
        help='Day of the following month on which the VAT return is due.')
    vat_holiday_adjustment = fields.Selection([
        ('next_working_day', 'Next Working Day'),
        ('previous_working_day', 'Previous Working Day'),
        ('none', 'No Adjustment'),
    ], string='Holiday Due-date Adjustment', default='next_working_day')
    vat_fiscal_year_start_month = fields.Selection([
        ('1', 'January'), ('2', 'February'), ('3', 'March'), ('4', 'April'),
        ('5', 'May'), ('6', 'June'), ('7', 'July'), ('8', 'August'),
        ('9', 'September'), ('10', 'October'), ('11', 'November'), ('12', 'December'),
    ], string='VAT Fiscal Year Starts', default='7')
    vat_enforce_declared_price = fields.Boolean(string='Block Sales Below Declared Price')
    vat_high_value_threshold = fields.Monetary(string='High-value Threshold', default=200000, currency_field='currency_id')
    vat_late_interest_rate = fields.Float(string='Late Interest Rate %', default=0.0)
    vat_late_fine_rate = fields.Float(string='Late Fine Rate %', default=0.0)

    @api.constrains('vat_bin', 'vat_legacy_bin')
    def _check_company_bin(self):
        for company in self:
            if company.vat_bin and (not company.vat_bin.isdigit() or len(company.vat_bin) != 13):
                raise ValidationError(_('Company VAT BIN must contain exactly 13 digits.'))
            if company.vat_legacy_bin and (not company.vat_legacy_bin.isdigit() or len(company.vat_legacy_bin) != 11):
                raise ValidationError(_('Legacy BIN must contain exactly 11 digits.'))

    @api.constrains('vat_return_due_day')
    def _check_vat_return_due_day(self):
        for company in self:
            if not 1 <= company.vat_return_due_day <= 28:
                raise ValidationError(_('Monthly return due day must be between 1 and 28.'))


class VatVdsCertificate(models.Model):
    _name = 'vat.vds.certificate'
    _description = 'Mushak 6.6 VDS Certificate'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'certificate_date desc, id desc'

    name = fields.Char(required=True, default=lambda self: _('New'), readonly=True, copy=False)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    unit_id = fields.Many2one('vat.unit', domain="[('company_id', '=', company_id)]")
    partner_id = fields.Many2one('res.partner', required=True)
    move_id = fields.Many2one('account.move', string='Source Invoice / Bill', required=True, ondelete='restrict')
    direction = fields.Selection([('deducted', 'Deducted from Supplier'), ('suffered', 'Deducted by Customer')], required=True)
    certificate_date = fields.Date(default=fields.Date.context_today, required=True)
    base_amount = fields.Monetary(required=True, currency_field='currency_id')
    rate = fields.Float(required=True)
    amount = fields.Monetary(compute='_compute_amount', store=True, currency_field='currency_id')
    currency_id = fields.Many2one(related='company_id.currency_id')
    state = fields.Selection([('draft', 'Draft'), ('confirmed', 'Confirmed'), ('deposited', 'Deposited'), ('reconciled', 'Reconciled'), ('cancelled', 'Cancelled')], default='draft', tracking=True)
    treasury_payment_id = fields.Many2one('vat.treasury.payment', string='Treasury Deposit')
    certificate_received = fields.Boolean(string='Certificate Received')
    attachment_ids = fields.Many2many('ir.attachment', string='Certificate / Evidence')

    @api.depends('base_amount', 'rate')
    def _compute_amount(self):
        for record in self:
            record.amount = record.base_amount * record.rate / 100

    def action_confirm(self):
        for record in self:
            if record.name == _('New'):
                record.name = self.env['vat.document.series'].next_number(
                    '66', record.company_id, record.unit_id, record.certificate_date,
                )
            record.state = 'confirmed'

    def action_reconcile(self):
        for record in self:
            if record.direction != 'suffered' or not record.certificate_received:
                raise UserError(_('A received customer certificate is required before reconciling VDS suffered.'))
            record.state = 'reconciled'

    def action_print_mushak_vds(self):
        self.ensure_one()
        return mushak_report_action(self, '6.6')


class VatTreasuryPayment(models.Model):
    _name = 'vat.treasury.payment'
    _description = 'VAT Treasury Challan / Payment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'payment_date desc, id desc'

    name = fields.Char(required=True, default=lambda self: _('New'), copy=False)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    unit_id = fields.Many2one('vat.unit', domain="[('company_id', '=', company_id)]")
    return_id = fields.Many2one('vat.return', ondelete='set null')
    payment_date = fields.Date(required=True, default=fields.Date.context_today)
    challan_number = fields.Char(required=True)
    bank = fields.Char()
    economic_code = fields.Char()
    payment_type = fields.Selection([('vat', 'VAT'), ('sd', 'Supplementary Duty'), ('vds', 'VDS'), ('interest', 'Interest'), ('fine', 'Fine'), ('other', 'Other')], default='vat', required=True)
    amount = fields.Monetary(required=True, currency_field='currency_id')
    currency_id = fields.Many2one(related='company_id.currency_id')
    vds_certificate_ids = fields.One2many('vat.vds.certificate', 'treasury_payment_id')
    attachment_ids = fields.Many2many('ir.attachment', string='Challan Copy')
    state = fields.Selection([('draft', 'Draft'), ('confirmed', 'Confirmed')], default='draft', tracking=True)

    _challan_company_unique = models.Constraint(
        'UNIQUE(company_id, challan_number)',
        'Challan number must be unique per company.',
    )

    def action_confirm(self):
        for payment in self:
            if payment.amount <= 0:
                raise ValidationError(_('Treasury payment amount must be greater than zero.'))
            if not payment.challan_number or not payment.challan_number.strip():
                raise ValidationError(_('A treasury challan reference is required.'))
            if payment.return_id and payment.return_id.company_id != payment.company_id:
                raise ValidationError(_('The treasury payment and VAT return must belong to the same company.'))
            payment.state = 'confirmed'
            payment.vds_certificate_ids.filtered(lambda c: c.direction == 'deducted').write({'state': 'deposited'})

    def action_print_treasury_challan(self):
        self.ensure_one()
        return mushak_report_action(self, 'tr6')


class VatReturn(models.Model):
    _name = 'vat.return'
    _description = 'Mushak 9.1 VAT Return'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'period_id desc, id desc'

    name = fields.Char(required=True, default=lambda self: _('New'), readonly=True, copy=False)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    unit_id = fields.Many2one('vat.unit', domain="[('company_id', '=', company_id)]")
    period_id = fields.Many2one('vat.period', required=True, domain="[('company_id', '=', company_id), ('unit_id', '=', unit_id)]", ondelete='restrict')
    return_type = fields.Selection([('main', 'Main'), ('late', 'Late'), ('amended', 'Amended'), ('additional', 'Additional')], default='main', required=True)
    parent_return_id = fields.Many2one('vat.return', string='Amends', ondelete='restrict')
    state = fields.Selection([('draft', 'Draft'), ('review', 'Under Review'), ('approved', 'Approved'), ('submitted', 'Submitted'), ('cancelled', 'Cancelled')], default='draft', required=True, tracking=True)
    line_ids = fields.One2many('vat.return.line', 'return_id', string='Return Lines', copy=True)
    adjustment_ids = fields.One2many('vat.adjustment', 'return_id', string='Adjustments')
    output_vat = fields.Monetary(compute='_compute_amounts', currency_field='currency_id')
    input_vat = fields.Monetary(compute='_compute_amounts', currency_field='currency_id')
    sd_amount = fields.Monetary(compute='_compute_amounts', currency_field='currency_id')
    adjustments_amount = fields.Monetary(compute='_compute_amounts', currency_field='currency_id')
    vds_suffered = fields.Monetary(compute='_compute_vds_suffered', currency_field='currency_id')
    reverse_charge_vat = fields.Monetary(compute='_compute_amounts', currency_field='currency_id')
    opening_balance = fields.Monetary(currency_field='currency_id')
    late_interest = fields.Monetary(currency_field='currency_id')
    late_fine = fields.Monetary(currency_field='currency_id')
    net_payable = fields.Monetary(compute='_compute_amounts', currency_field='currency_id')
    closing_credit = fields.Monetary(compute='_compute_amounts', currency_field='currency_id')
    currency_id = fields.Many2one(related='company_id.currency_id')
    nbr_acknowledgement = fields.Char(string='NBR Acknowledgement No.')
    nbr_submission_date = fields.Date()
    validation_note = fields.Text(readonly=True)
    treasury_payment_ids = fields.One2many('vat.treasury.payment', 'return_id')
    attachment_ids = fields.Many2many('ir.attachment', string='Supporting Documents')

    _return_period_type_unique = models.Constraint(
        'UNIQUE(company_id, unit_id, period_id, return_type)',
        'A return already exists for this period, unit and return type.',
    )

    @api.depends('company_id', 'unit_id', 'period_id')
    def _compute_vds_suffered(self):
        for record in self:
            if not record.period_id:
                record.vds_suffered = 0.0
                continue
            domain = [
                ('company_id', '=', record.company_id.id),
                ('direction', '=', 'suffered'),
                ('state', '=', 'reconciled'),
                ('certificate_date', '>=', record.period_id.date_start),
                ('certificate_date', '<=', record.period_id.date_end),
            ]
            if record.unit_id:
                domain.append(('unit_id', '=', record.unit_id.id))
            record.vds_suffered = sum(self.env['vat.vds.certificate'].search(domain).mapped('amount'))

    @api.depends('line_ids.output_vat', 'line_ids.input_vat', 'line_ids.sd_amount', 'line_ids.reverse_charge_vat', 'adjustment_ids.signed_amount', 'vds_suffered', 'opening_balance', 'late_interest', 'late_fine')
    def _compute_amounts(self):
        for record in self:
            record.output_vat = sum(record.line_ids.mapped('output_vat'))
            record.input_vat = sum(record.line_ids.mapped('input_vat'))
            record.sd_amount = sum(record.line_ids.mapped('sd_amount'))
            record.reverse_charge_vat = sum(record.line_ids.mapped('reverse_charge_vat'))
            record.adjustments_amount = sum(record.adjustment_ids.mapped('signed_amount'))
            due = record.output_vat + record.sd_amount + record.reverse_charge_vat - record.input_vat + record.adjustments_amount - record.vds_suffered - record.opening_balance + record.late_interest + record.late_fine
            record.net_payable = max(due, 0)
            record.closing_credit = max(-due, 0)

    def _period_moves(self):
        self.ensure_one()
        domain = [('company_id', '=', self.company_id.id), ('state', '=', 'posted'), ('invoice_date', '>=', self.period_id.date_start), ('invoice_date', '<=', self.period_id.date_end), ('move_type', 'in', ('out_invoice', 'out_refund', 'in_invoice', 'in_refund'))]
        if self.unit_id:
            domain.append(('vat_unit_id', '=', self.unit_id.id))
        return self.env['account.move'].search(domain)

    def action_generate(self):
        for record in self:
            if record.state not in ('draft', 'review'):
                raise UserError(_('Only a draft or reviewed return can be regenerated.'))
            moves = record._period_moves()
            record.line_ids.unlink()
            values = []
            for move in moves:
                values.append((0, 0, {'move_id': move.id, 'document_date': move.invoice_date, 'partner_id': move.partner_id.id, 'base_amount': move.vat_taxable_amount, 'output_vat': move.vat_output_amount, 'input_vat': move.vat_input_amount, 'sd_amount': move.vat_sd_amount, 'reverse_charge_vat': move.vat_reverse_charge_amount, 'supply_type': move.vat_supply_type, 'mushak_number': move.vat_mushak_number}))
            scheduled_credits = self.env['vat.capital.credit.schedule.line'].search([
                ('schedule_id.company_id', '=', record.company_id.id),
                ('schedule_id.unit_id', '=', record.unit_id.id), ('state', '=', 'pending'),
                ('scheduled_date', '>=', record.period_id.date_start), ('scheduled_date', '<=', record.period_id.date_end),
            ])
            for credit in scheduled_credits:
                values.append((0, 0, {
                    'move_id': credit.schedule_id.move_id.id, 'document_date': credit.scheduled_date,
                    'partner_id': credit.schedule_id.move_id.partner_id.id,
                    'mushak_number': credit.schedule_id.move_id.vat_supplier_document_number,
                    'input_vat': credit.amount, 'supply_type': 'import' if credit.schedule_id.move_id.vat_supply_type == 'import' else 'taxable',
                    'capital_credit_line_id': credit.id,
                }))
            record.write({'line_ids': values})
            record._compute_late_charges()
            record.message_post(body=_('Return regenerated from %s posted documents.') % len(moves))

    def _compute_late_charges(self):
        for record in self:
            if record.return_type == 'late' and record.period_id.due_date:
                base = max(record.output_vat + record.sd_amount - record.input_vat, 0)
                record.late_interest = base * record.company_id.vat_late_interest_rate / 100
                record.late_fine = base * record.company_id.vat_late_fine_rate / 100

    def action_validate(self):
        for record in self:
            issues = []
            for move in record._period_moves():
                if move.move_type.startswith('out_') and not move.vat_mushak_number:
                    issues.append(_('%s: missing Mushak number') % move.display_name)
                for line in move.invoice_line_ids.filtered(lambda l: not l.display_type):
                    if line.product_id and not line.product_id.product_tmpl_id.vat_hs_code_id:
                        issues.append(_('%s: %s has no HS / service code') % (move.display_name, line.product_id.display_name))
                if move.partner_id.vat_registration_status == 'registered' and not move.partner_id.vat_bin:
                    issues.append(_('%s: registered partner has no BIN') % move.display_name)
                if move.vat_vds_reverse_charge and not move.vat_reverse_charge_payment_id:
                    issues.append(_('%s: reverse-charge payment evidence is not linked') % move.display_name)
            unmatched = self.env['vat.vds.certificate'].search_count([('company_id', '=', record.company_id.id), ('direction', '=', 'suffered'), ('state', 'in', ('draft', 'confirmed'))])
            if unmatched:
                issues.append(_('%s VDS-suffered certificate(s) remain unmatched') % unmatched)
            record.validation_note = '\n'.join(issues) or _('Validation passed.')
            if issues:
                raise UserError(_('Pre-submission validation found issues:\n%s') % record.validation_note)
            record.state = 'review'

    def action_approve(self):
        if not self.env.user.has_group('zsl_vat.group_vat_manager'):
            raise UserError(_('Only a VAT Manager can approve a return.'))
        for record in self:
            if record.state != 'review':
                raise UserError(_('Only reviewed VAT returns can be approved.'))
            if record.period_id.company_id != record.company_id:
                raise ValidationError(_('The VAT period must belong to the same company as the return.'))
            if record.unit_id and record.period_id.unit_id != record.unit_id:
                raise ValidationError(_('The VAT period and return must have the same VAT unit.'))
        approved = self
        approved.write({'state': 'approved'})
        for record in approved:
            record.line_ids.mapped('capital_credit_line_id').write({'state': 'claimed', 'return_id': record.id})

    def action_submit(self):
        if not self.env.user.has_group('zsl_vat.group_vat_manager'):
            raise UserError(_('Only a VAT Manager can record an official VAT return submission.'))
        for record in self:
            if record.state != 'approved':
                raise UserError(_('Only an approved return can be submitted.'))
            if not record.nbr_acknowledgement or not record.nbr_acknowledgement.strip():
                raise UserError(_('Enter the official NBR acknowledgement number before marking this return as submitted. Exporting a CSV does not submit a return to NBR.'))
            if record.name == _('New'):
                record.name = self.env['vat.document.series'].next_number(
                    '91', record.company_id, record.unit_id, record.period_id.date_end,
                )
            record.write({'state': 'submitted', 'nbr_submission_date': fields.Date.context_today(self)})
            record.period_id.action_lock()

    def action_export_nbr(self):
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(_('Approve the return before preparing an NBR export.'))
        if self.company_id.vat_registration_type == 'turnover':
            raise UserError(_('Mushak 9.2 requires a separate turnover-tax calculation and official form. This VAT 9.1 export cannot be used for 9.2.'))
        return {'type': 'ir.actions.act_url', 'url': '/web/content?model=vat.return&id=%s&field=nbr_export_file&filename_field=nbr_export_filename&download=true' % self.id, 'target': 'self'}

    def action_print_mushak_return(self):
        self.ensure_one()
        form_code = '9.2' if self.company_id.vat_registration_type == 'turnover' else '9.1'
        return mushak_report_action(self, form_code)

    nbr_export_file = fields.Binary(compute='_compute_nbr_export', string='NBR Export', attachment=True)
    nbr_export_filename = fields.Char(compute='_compute_nbr_export')

    def _compute_nbr_export(self):
        import base64
        import csv
        import io
        for record in self:
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['mushak_9_1', record.name, record.period_id.date_start, record.period_id.date_end, 'output_vat', record.output_vat, 'input_vat', record.input_vat, 'sd', record.sd_amount, 'net_payable', record.net_payable])
            writer.writerow(['document', 'date', 'partner', 'base', 'output_vat', 'input_vat', 'sd', 'supply_type'])
            for line in record.line_ids:
                writer.writerow([line.mushak_number, line.document_date, line.partner_id.name, line.base_amount, line.output_vat, line.input_vat, line.sd_amount, line.supply_type])
            record.nbr_export_file = base64.b64encode(output.getvalue().encode())
            record.nbr_export_filename = 'Mushak_9_1_%s.csv' % (record.period_id.date_start or 'draft')

    @api.model
    def get_dashboard_data(self):
        """Operational VAT cockpit, derived only from posted Odoo records."""
        today = fields.Date.context_today(self)
        period = self.env['vat.period'].search([('company_id', '=', self.env.company.id), ('date_start', '<=', today), ('date_end', '>=', today)], limit=1)
        if not period:
            period = self.env['vat.period'].search([('company_id', '=', self.env.company.id), ('state', '=', 'open')], order='date_start', limit=1)
        returns = self.search([('company_id', '=', self.env.company.id), ('period_id', '=', period.id)], limit=1) if period else self.browse()
        company_domain = [('company_id', '=', self.env.company.id)]
        Move = self.env['account.move']
        Treasury = self.env['vat.treasury.payment']
        period_domain = company_domain + [('state', '=', 'posted')]
        if period:
            period_domain += [('invoice_date', '>=', period.date_start), ('invoice_date', '<=', period.date_end)]
        sales = Move.search(period_domain + [('move_type', '=', 'out_invoice')])
        purchases = Move.search(period_domain + [('move_type', '=', 'in_invoice')])
        last_sale = Move.search(company_domain + [('state', '=', 'posted'), ('move_type', '=', 'out_invoice')], order='invoice_date desc, id desc', limit=1)
        last_purchase = Move.search(company_domain + [('state', '=', 'posted'), ('move_type', '=', 'in_invoice')], order='invoice_date desc, id desc', limit=1)
        last_payment = Treasury.search(company_domain + [('state', '=', 'confirmed')], order='payment_date desc, id desc', limit=1)
        pending_vds = self.env['vat.vds.certificate'].search_count(company_domain + [('state', 'in', ('draft', 'confirmed'))])
        due_days = (period.due_date - today).days if period and period.due_date else None
        trend = []
        first_month = today.replace(day=1) - relativedelta(months=5)
        for index in range(6):
            month_start = first_month + relativedelta(months=index)
            month_end = month_start + relativedelta(months=1, days=-1)
            month_moves = Move.search(company_domain + [('state', '=', 'posted'), ('invoice_date', '>=', month_start), ('invoice_date', '<=', month_end), ('move_type', 'in', ('out_invoice', 'out_refund', 'in_invoice', 'in_refund'))])
            month_vat = sum(month_moves.mapped('vat_output_amount')) - sum(month_moves.mapped('vat_input_amount'))
            month_paid = sum(Treasury.search(company_domain + [('state', '=', 'confirmed'), ('payment_date', '>=', month_start), ('payment_date', '<=', month_end)]).mapped('amount'))
            trend.append({'label': month_start.strftime('%b'), 'vat': month_vat, 'payment': month_paid})
        maximum = max([abs(point['vat']) for point in trend] + [point['payment'] for point in trend] + [1])
        for point in trend:
            point['vat_height'] = round(abs(point['vat']) * 100 / maximum)
            point['payment_height'] = round(point['payment'] * 100 / maximum)
        return {
            'period': period.name if period else _('No VAT period configured'),
            'vat_balance': returns.net_payable if returns else 0.0,
            'vds_balance': sum(self.env['vat.vds.certificate'].search([('company_id', '=', self.env.company.id), ('direction', '=', 'deducted'), ('state', 'in', ('confirmed', 'deposited'))]).mapped('amount')),
            'pending_vds': pending_vds,
            'due_date': str(period.due_date) if period and period.due_date else False,
            'due_days': due_days,
            'return_state': returns.state if returns else 'not prepared',
            'last_sale': last_sale.vat_mushak_number or last_sale.name or '—',
            'last_sale_date': str(last_sale.invoice_date) if last_sale else False,
            'last_purchase': last_purchase.name or '—',
            'last_purchase_date': str(last_purchase.invoice_date) if last_purchase else False,
            'last_paid_date': str(last_payment.payment_date) if last_payment else False,
            'total_sale': sum(sales.mapped('amount_total')),
            'total_purchase': sum(purchases.mapped('amount_total')),
            'sales_count': len(sales),
            'purchase_count': len(purchases),
            'trend': trend,
        }


class VatReturnLine(models.Model):
    _name = 'vat.return.line'
    _description = 'Mushak 9.1 Return Source Line'
    _order = 'document_date, id'

    return_id = fields.Many2one('vat.return', required=True, ondelete='cascade')
    move_id = fields.Many2one('account.move', required=True, ondelete='restrict')
    document_date = fields.Date()
    partner_id = fields.Many2one('res.partner')
    mushak_number = fields.Char()
    supply_type = fields.Selection([('taxable', 'Taxable'), ('zero', 'Zero Rated'), ('exempt', 'Exempt'), ('export', 'Export'), ('import', 'Import')], default='taxable')
    base_amount = fields.Monetary(currency_field='currency_id')
    output_vat = fields.Monetary(currency_field='currency_id')
    input_vat = fields.Monetary(currency_field='currency_id')
    sd_amount = fields.Monetary(currency_field='currency_id')
    reverse_charge_vat = fields.Monetary(currency_field='currency_id')
    capital_credit_line_id = fields.Many2one('vat.capital.credit.schedule.line', readonly=True, ondelete='restrict')
    currency_id = fields.Many2one(related='return_id.currency_id')


class VatAdjustment(models.Model):
    _name = 'vat.adjustment'
    _description = 'VAT Return Adjustment'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    return_id = fields.Many2one('vat.return', required=True, ondelete='cascade')
    name = fields.Char(required=True)
    adjustment_type = fields.Selection([('increase', 'Increasing Adjustment'), ('decrease', 'Decreasing Adjustment')], required=True)
    amount = fields.Monetary(required=True, currency_field='currency_id')
    signed_amount = fields.Monetary(compute='_compute_signed_amount', store=True, currency_field='currency_id')
    return_note = fields.Char(string='Mushak 9.1 Note')
    reason = fields.Text(required=True)
    move_id = fields.Many2one('account.move')
    attachment_ids = fields.Many2many('ir.attachment', string='Evidence')
    state = fields.Selection([('draft', 'Draft'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='draft')
    currency_id = fields.Many2one(related='return_id.currency_id')

    @api.depends('amount', 'adjustment_type', 'state')
    def _compute_signed_amount(self):
        for record in self:
            record.signed_amount = record.amount * (1 if record.adjustment_type == 'increase' else -1) if record.state == 'approved' else 0

    def action_approve(self):
        if not self.env.user.has_group('zsl_vat.group_vat_officer'):
            raise UserError(_('A VAT Officer must approve adjustments.'))
        self.write({'state': 'approved'})
