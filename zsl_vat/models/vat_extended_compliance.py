"""Operational controls for the SRS workflows not covered by core Odoo.

The records in this file intentionally keep VAT evidence separate from the
financial journal entries created by Odoo.  This prevents a VAT working-paper
calculation from posting duplicate accounting entries while still giving the
VAT officer an auditable reconciliation trail.
"""

import json
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class VatAccountMapping(models.Model):
    _name = 'vat.account.mapping'
    _description = 'VAT Accounting Mapping'
    _order = 'company_id, unit_id, tax_head'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    unit_id = fields.Many2one('vat.unit', domain="[('company_id', '=', company_id)]")
    tax_head = fields.Selection([
        ('input_vat', 'Input VAT / Rebate'), ('output_vat', 'Output VAT'),
        ('sd', 'Supplementary Duty'), ('at', 'Advance Tax'),
        ('vds', 'VDS / Withholding'), ('reverse_charge', 'Reverse-charge VAT'),
        ('payable', 'VAT Payable / Receivable'),
    ], required=True)
    account_id = fields.Many2one('account.account', required=True, domain="[('company_ids', 'in', company_id)]")
    journal_id = fields.Many2one('account.journal', domain="[('company_id', '=', company_id), ('type', '=', 'general')]")
    legal_reference = fields.Char()
    active = fields.Boolean(default=True)

    _unique_mapping = models.Constraint(
        'UNIQUE(company_id, unit_id, tax_head)',
        'Only one VAT account mapping is allowed per company, unit and tax head.',
    )


class VatReconciliation(models.Model):
    _name = 'vat.reconciliation'
    _description = 'VAT Return to Ledger Reconciliation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'period_id desc, id desc'

    name = fields.Char(default=lambda self: _('New'), readonly=True, copy=False)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    unit_id = fields.Many2one('vat.unit', domain="[('company_id', '=', company_id)]")
    period_id = fields.Many2one('vat.period', required=True, domain="[('company_id', '=', company_id)]", ondelete='restrict')
    return_id = fields.Many2one('vat.return', domain="[('company_id', '=', company_id)]", ondelete='restrict')
    line_ids = fields.One2many('vat.reconciliation.line', 'reconciliation_id', copy=False)
    state = fields.Selection([('draft', 'Draft'), ('prepared', 'Prepared'), ('reviewed', 'Reviewed')], default='draft', tracking=True)
    difference_amount = fields.Monetary(compute='_compute_totals', store=True, currency_field='currency_id')
    currency_id = fields.Many2one(related='company_id.currency_id')
    note = fields.Text()

    _period_unique = models.Constraint(
        'UNIQUE(company_id, unit_id, period_id)',
        'A VAT reconciliation already exists for this company, unit and period.',
    )

    @api.depends('line_ids.difference')
    def _compute_totals(self):
        for record in self:
            record.difference_amount = sum(record.line_ids.mapped('difference'))

    def action_prepare(self):
        Mapping = self.env['vat.account.mapping']
        for record in self:
            domain = [('company_id', '=', record.company_id.id), ('active', '=', True)]
            if record.unit_id:
                domain += ['|', ('unit_id', '=', record.unit_id.id), ('unit_id', '=', False)]
            mappings = Mapping.search(domain)
            if not mappings:
                raise UserError(_('Configure VAT accounting mappings before preparing a reconciliation.'))
            record.line_ids.unlink()
            values = []
            for mapping in mappings:
                aml_domain = [
                    ('move_id.state', '=', 'posted'), ('account_id', '=', mapping.account_id.id),
                    ('date', '>=', record.period_id.date_start), ('date', '<=', record.period_id.date_end),
                ]
                ledger = sum(self.env['account.move.line'].search(aml_domain).mapped(lambda line: line.debit - line.credit))
                return_amount = 0.0
                if record.return_id:
                    return_amount = {
                        'input_vat': -record.return_id.input_vat,
                        'output_vat': record.return_id.output_vat,
                        'sd': record.return_id.sd_amount,
                        'reverse_charge': record.return_id.reverse_charge_vat,
                        'vds': -record.return_id.vds_suffered,
                        'payable': record.return_id.net_payable - record.return_id.closing_credit,
                    }.get(mapping.tax_head, 0.0)
                values.append((0, 0, {
                    'tax_head': mapping.tax_head, 'account_id': mapping.account_id.id,
                    'ledger_amount': ledger, 'return_amount': return_amount,
                }))
            record.write({'line_ids': values, 'state': 'prepared'})
            record.message_post(body=_('Ledger balances were prepared from posted journal items.'))

    def action_review(self):
        for record in self:
            if record.state != 'prepared':
                raise UserError(_('Prepare the reconciliation before marking it reviewed.'))
            record.state = 'reviewed'


class VatReconciliationLine(models.Model):
    _name = 'vat.reconciliation.line'
    _description = 'VAT Reconciliation Line'

    reconciliation_id = fields.Many2one('vat.reconciliation', required=True, ondelete='cascade')
    # Independent selection: a related-to-one2many field is not valid here.
    tax_head = fields.Selection([
        ('input_vat', 'Input VAT / Rebate'), ('output_vat', 'Output VAT'), ('sd', 'Supplementary Duty'),
        ('at', 'Advance Tax'), ('vds', 'VDS / Withholding'), ('reverse_charge', 'Reverse-charge VAT'), ('payable', 'VAT Payable / Receivable'),
    ], required=True)
    account_id = fields.Many2one('account.account', required=True)
    ledger_amount = fields.Monetary(currency_field='currency_id')
    return_amount = fields.Monetary(currency_field='currency_id')
    difference = fields.Monetary(compute='_compute_difference', store=True, currency_field='currency_id')
    explanation = fields.Char()
    currency_id = fields.Many2one(related='reconciliation_id.company_id.currency_id')

    @api.depends('ledger_amount', 'return_amount')
    def _compute_difference(self):
        for line in self:
            line.difference = line.ledger_amount - line.return_amount


class VatInputApportionment(models.Model):
    _name = 'vat.input.apportionment'
    _description = 'VAT Input Tax Apportionment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'period_id desc, id desc'

    name = fields.Char(default=lambda self: _('New'), readonly=True, copy=False)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    unit_id = fields.Many2one('vat.unit', domain="[('company_id', '=', company_id)]")
    period_id = fields.Many2one('vat.period', required=True, domain="[('company_id', '=', company_id)]", ondelete='restrict')
    method = fields.Selection([('direct', 'Direct attribution'), ('turnover', 'Taxable turnover ratio'), ('custom', 'Approved custom ratio')], default='direct', required=True)
    taxable_turnover = fields.Monetary(currency_field='currency_id')
    exempt_turnover = fields.Monetary(currency_field='currency_id')
    eligible_percent = fields.Float(compute='_compute_eligible_percent', store=True)
    total_common_input = fields.Monetary(compute='_compute_input', store=True, currency_field='currency_id')
    eligible_input = fields.Monetary(compute='_compute_input', store=True, currency_field='currency_id')
    non_creditable_input = fields.Monetary(compute='_compute_input', store=True, currency_field='currency_id')
    approved_percent = fields.Float(string='Approved %')
    legal_reference = fields.Char()
    state = fields.Selection([('draft', 'Draft'), ('calculated', 'Calculated'), ('approved', 'Approved')], default='draft', tracking=True)
    currency_id = fields.Many2one(related='company_id.currency_id')

    _period_unique = models.Constraint('UNIQUE(company_id, unit_id, period_id)', 'Only one apportionment is allowed per company, unit and period.')

    @api.depends('method', 'taxable_turnover', 'exempt_turnover', 'approved_percent')
    def _compute_eligible_percent(self):
        for record in self:
            if record.method == 'turnover':
                total = record.taxable_turnover + record.exempt_turnover
                record.eligible_percent = (record.taxable_turnover / total * 100.0) if total else 0.0
            elif record.method == 'custom':
                record.eligible_percent = record.approved_percent
            else:
                record.eligible_percent = 100.0

    @api.depends('eligible_percent', 'period_id', 'company_id', 'unit_id')
    def _compute_input(self):
        for record in self:
            if not record.period_id:
                record.total_common_input = record.eligible_input = record.non_creditable_input = 0.0
                continue
            domain = [
                ('company_id', '=', record.company_id.id), ('state', '=', 'posted'), ('move_type', '=', 'in_invoice'),
                ('invoice_date', '>=', record.period_id.date_start), ('invoice_date', '<=', record.period_id.date_end),
            ]
            if record.unit_id:
                domain.append(('vat_unit_id', '=', record.unit_id.id))
            common = 0.0
            for move in self.env['account.move'].search(domain):
                for line in move.invoice_line_ids.filtered(lambda item: item.display_type == 'product' and item.vat_input_credit_status != 'non_creditable'):
                    common += line._vat_eligible_input_amount()
            record.total_common_input = common
            record.eligible_input = common * record.eligible_percent / 100.0
            record.non_creditable_input = common - record.eligible_input

    @api.constrains('approved_percent')
    def _check_percent(self):
        for record in self:
            if not 0 <= record.approved_percent <= 100:
                raise ValidationError(_('The approved percentage must be between 0 and 100.'))

    def action_calculate(self):
        for record in self:
            if record.method == 'turnover' and not (record.taxable_turnover + record.exempt_turnover):
                raise ValidationError(_('Enter taxable and/or exempt turnover for turnover-ratio apportionment.'))
            record._compute_input()
            record.state = 'calculated'

    def action_approve(self):
        if not self.env.user.has_group('zsl_vat.group_vat_manager'):
            raise UserError(_('Only a VAT Manager may approve input-tax apportionment.'))
        self.filtered(lambda record: record.state == 'calculated').write({'state': 'approved'})


class VatProductionValuation(models.Model):
    _name = 'vat.production.valuation'
    _description = 'VAT Production Valuation and Wastage'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'production_id desc'

    name = fields.Char(default=lambda self: _('New'), readonly=True, copy=False)
    production_id = fields.Many2one('mrp.production', required=True, ondelete='restrict')
    company_id = fields.Many2one(related='production_id.company_id', store=True)
    unit_id = fields.Many2one('vat.unit', domain="[('company_id', '=', company_id)]")
    material_value = fields.Monetary(compute='_compute_values', store=True, currency_field='currency_id')
    finished_value = fields.Monetary(compute='_compute_values', store=True, currency_field='currency_id')
    wastage_quantity = fields.Float(compute='_compute_values', store=True)
    wastage_value = fields.Monetary(compute='_compute_values', store=True, currency_field='currency_id')
    byproduct_value = fields.Monetary(string='By-product / Scrap Value', currency_field='currency_id')
    variance_value = fields.Monetary(compute='_compute_values', store=True, currency_field='currency_id')
    reason = fields.Text(string='Wastage / Variance Reason')
    state = fields.Selection([('draft', 'Draft'), ('validated', 'Validated')], default='draft', tracking=True)
    currency_id = fields.Many2one(related='company_id.currency_id')

    _production_unique = models.Constraint('UNIQUE(production_id)', 'Only one VAT valuation is allowed per production order.')

    @api.depends('production_id.move_raw_ids.quantity', 'production_id.move_raw_ids.product_uom_qty', 'production_id.move_raw_ids.product_id.standard_price', 'production_id.move_finished_ids.quantity', 'production_id.move_finished_ids.product_uom_qty', 'production_id.move_finished_ids.product_id.standard_price', 'byproduct_value')
    def _compute_values(self):
        for record in self:
            raw = record.production_id.move_raw_ids.filtered(lambda move: move.state != 'cancel')
            finished = record.production_id.move_finished_ids.filtered(lambda move: move.state != 'cancel')
            material_value = sum((move.quantity or move.product_uom_qty) * move.product_id.standard_price for move in raw)
            finished_value = sum((move.quantity or move.product_uom_qty) * move.product_id.standard_price for move in finished)
            expected = sum(move.product_uom_qty for move in raw)
            consumed = sum(move.quantity for move in raw)
            record.material_value = material_value
            record.finished_value = finished_value
            record.wastage_quantity = max(expected - consumed, 0.0)
            record.wastage_value = max(material_value - finished_value - record.byproduct_value, 0.0)
            record.variance_value = material_value - finished_value - record.byproduct_value - record.wastage_value

    def action_validate(self):
        for record in self:
            if record.production_id.state not in ('to_close', 'done'):
                raise UserError(_('Complete the production order before validating its VAT valuation.'))
            if record.wastage_value and not record.reason:
                raise ValidationError(_('Explain the wastage or valuation variance before validation.'))
            record.state = 'validated'


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    vat_unit_id = fields.Many2one('vat.unit', string='VAT Unit', domain="[('company_id', '=', company_id)]")
    vat_valuation_id = fields.One2many('vat.production.valuation', 'production_id', string='VAT Valuation')


class VatServicePlan(models.Model):
    _name = 'vat.service.plan'
    _description = 'Recurring VAT Service Billing Plan'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'next_invoice_date, name'

    name = fields.Char(required=True, default=lambda self: _('New'), copy=False)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    unit_id = fields.Many2one('vat.unit', domain="[('company_id', '=', company_id)]")
    partner_id = fields.Many2one('res.partner', required=True)
    product_id = fields.Many2one('product.product', required=True, domain="[('type', '=', 'service')]")
    quantity = fields.Float(default=1.0, required=True)
    price_unit = fields.Monetary(currency_field='currency_id', required=True)
    recurrence = fields.Selection([('monthly', 'Monthly'), ('quarterly', 'Quarterly'), ('yearly', 'Yearly')], default='monthly', required=True)
    next_invoice_date = fields.Date(required=True, default=fields.Date.context_today)
    start_date = fields.Date(required=True, default=fields.Date.context_today)
    end_date = fields.Date()
    state = fields.Selection([('draft', 'Draft'), ('active', 'Active'), ('closed', 'Closed')], default='draft', tracking=True)
    invoice_ids = fields.One2many('account.move', 'vat_service_plan_id')
    currency_id = fields.Many2one(related='company_id.currency_id')

    @api.onchange('product_id')
    def _onchange_product_id(self):
        for record in self:
            if record.product_id and not record.price_unit:
                record.price_unit = record.product_id.lst_price

    @api.constrains('quantity', 'end_date', 'start_date')
    def _check_values(self):
        for record in self:
            if record.quantity <= 0:
                raise ValidationError(_('Service quantity must be positive.'))
            if record.end_date and record.end_date < record.start_date:
                raise ValidationError(_('The end date cannot precede the start date.'))

    def _next_date(self, current):
        self.ensure_one()
        if self.recurrence == 'quarterly':
            return fields.Date.add(current, months=3)
        if self.recurrence == 'yearly':
            return fields.Date.add(current, years=1)
        return fields.Date.add(current, months=1)

    def action_activate(self):
        self.filtered(lambda plan: plan.state == 'draft').write({'state': 'active'})

    def action_create_invoice(self):
        invoices = self.env['account.move']
        for plan in self:
            if plan.state != 'active':
                raise UserError(_('Only active service plans can create invoices.'))
            if plan.end_date and plan.next_invoice_date > plan.end_date:
                plan.state = 'closed'
                continue
            invoice = self.env['account.move'].create({
                'move_type': 'out_invoice', 'partner_id': plan.partner_id.id, 'invoice_date': plan.next_invoice_date,
                'vat_unit_id': plan.unit_id.id, 'vat_service_plan_id': plan.id, 'vat_supply_stage': 'periodic',
                'vat_time_of_supply_date': plan.next_invoice_date,
                'invoice_line_ids': [(0, 0, {'product_id': plan.product_id.id, 'name': plan.product_id.display_name, 'quantity': plan.quantity, 'price_unit': plan.price_unit})],
            })
            plan.next_invoice_date = plan._next_date(plan.next_invoice_date)
            invoices |= invoice
        return {'type': 'ir.actions.act_window', 'name': _('Generated Service Invoices'), 'res_model': 'account.move', 'view_mode': 'list,form', 'domain': [('id', 'in', invoices.ids)]}


class AccountMoveVatService(models.Model):
    _inherit = 'account.move'

    vat_service_plan_id = fields.Many2one('vat.service.plan', copy=False, ondelete='set null')
    vat_timesheet_billing_id = fields.Many2one('vat.timesheet.billing', copy=False, ondelete='set null')
    vat_supply_stage = fields.Selection([('standard', 'Standard'), ('advance', 'Advance'), ('progress', 'Progress / Milestone'), ('periodic', 'Periodic Service'), ('final', 'Final Settlement')], default='standard')
    vat_time_of_supply_date = fields.Date(string='VAT Time of Supply', default=fields.Date.context_today)
    vat_service_evidence_ids = fields.Many2many('ir.attachment', string='Service Evidence / Acceptance')


class VatTimesheetBilling(models.Model):
    _name = 'vat.timesheet.billing'
    _description = 'VAT Timesheet Billing Batch'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'work_date_to desc, id desc'

    name = fields.Char(default=lambda self: _('New'), readonly=True, copy=False)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    unit_id = fields.Many2one('vat.unit', domain="[('company_id', '=', company_id)]")
    partner_id = fields.Many2one('res.partner', required=True)
    product_id = fields.Many2one('product.product', required=True, domain="[('type', '=', 'service')]")
    price_per_hour = fields.Monetary(currency_field='currency_id', required=True)
    work_date_from = fields.Date(required=True)
    work_date_to = fields.Date(required=True)
    timesheet_ids = fields.Many2many('account.analytic.line', string='Timesheets', domain="[('vat_timesheet_billing_id', '=', False)]")
    total_hours = fields.Float(compute='_compute_totals', store=True)
    amount = fields.Monetary(compute='_compute_totals', store=True, currency_field='currency_id')
    invoice_id = fields.Many2one('account.move', readonly=True, copy=False)
    state = fields.Selection([('draft', 'Draft'), ('invoiced', 'Invoiced'), ('cancelled', 'Cancelled')], default='draft', tracking=True)
    currency_id = fields.Many2one(related='company_id.currency_id')

    @api.depends('timesheet_ids.unit_amount', 'price_per_hour')
    def _compute_totals(self):
        for record in self:
            record.total_hours = sum(record.timesheet_ids.mapped('unit_amount'))
            record.amount = record.total_hours * record.price_per_hour

    @api.constrains('work_date_from', 'work_date_to', 'price_per_hour')
    def _check_dates(self):
        for record in self:
            if record.work_date_to < record.work_date_from:
                raise ValidationError(_('The work end date cannot be earlier than the start date.'))
            if record.price_per_hour < 0:
                raise ValidationError(_('The hourly price cannot be negative.'))

    def action_create_invoice(self):
        for record in self:
            if record.state != 'draft' or not record.timesheet_ids:
                raise UserError(_('Select uninvoiced timesheets before creating the service invoice.'))
            outside = record.timesheet_ids.filtered(lambda line: line.date < record.work_date_from or line.date > record.work_date_to)
            if outside:
                raise ValidationError(_('Every selected timesheet must fall inside the billing period.'))
            invoice = self.env['account.move'].create({
                'move_type': 'out_invoice', 'partner_id': record.partner_id.id, 'invoice_date': record.work_date_to,
                'vat_unit_id': record.unit_id.id, 'vat_timesheet_billing_id': record.id,
                'vat_supply_stage': 'progress', 'vat_time_of_supply_date': record.work_date_to,
                'invoice_line_ids': [(0, 0, {'product_id': record.product_id.id, 'name': _('%s — timesheet service') % record.product_id.display_name, 'quantity': record.total_hours, 'price_unit': record.price_per_hour})],
            })
            record.timesheet_ids.write({'vat_timesheet_billing_id': record.id})
            record.write({'invoice_id': invoice.id, 'state': 'invoiced'})
            return {'type': 'ir.actions.act_window', 'res_model': 'account.move', 'view_mode': 'form', 'res_id': invoice.id}


class AccountAnalyticLineVat(models.Model):
    _inherit = 'account.analytic.line'

    vat_timesheet_billing_id = fields.Many2one('vat.timesheet.billing', string='VAT Billing Batch', copy=False, readonly=True)


class PosConfigVat(models.Model):
    _inherit = 'pos.config'

    vat_unit_id = fields.Many2one('vat.unit', string='VAT Unit', domain="[('company_id', '=', company_id)]")


class PosOrderVat(models.Model):
    _inherit = 'pos.order'

    vat_unit_id = fields.Many2one('vat.unit', string='VAT Unit', related='config_id.vat_unit_id', store=True, readonly=True)
    vat_mushak_number = fields.Char(string='Mushak 6.3 Number', readonly=True, copy=False, index=True)
    vat_invoice_id = fields.Many2one('account.move', string='VAT Invoice', readonly=True, copy=False)

    def action_pos_order_paid(self):
        result = super().action_pos_order_paid()
        for order in self:
            if not order.vat_mushak_number:
                order.vat_mushak_number = self.env['vat.document.series'].next_number(
                    '63', order.company_id, order.vat_unit_id, fields.Date.to_date(order.date_order),
                )
        return result

    def _generate_pos_order_invoice(self):
        invoices = super()._generate_pos_order_invoice()
        # Odoo returns a single invoice for a single POS order.  Keep the link
        # only for the corresponding order record(s), without re-posting it.
        for order in self:
            if not order.vat_mushak_number:
                order.vat_mushak_number = self.env['vat.document.series'].next_number('63', order.company_id, order.vat_unit_id, fields.Date.to_date(order.date_order))
            if invoices and not order.vat_invoice_id:
                order.vat_invoice_id = invoices.id
                if not invoices.vat_mushak_number:
                    invoices.vat_mushak_number = order.vat_mushak_number
        return invoices


class VatNbrConnector(models.Model):
    _name = 'vat.nbr.connector'
    _description = 'NBR Return Submission Connector'

    name = fields.Char(required=True, default='NBR VAT Return API')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    transport = fields.Selection([('manual', 'Manual portal submission'), ('http_json', 'HTTP JSON API')], default='manual', required=True)
    endpoint_url = fields.Char(string='Official API Endpoint')
    api_token = fields.Char(groups='zsl_vat.group_vat_manager')
    enabled = fields.Boolean(default=False)
    last_tested_on = fields.Datetime(readonly=True)
    last_test_result = fields.Text(readonly=True)

    _company_unique = models.Constraint('UNIQUE(company_id)', 'Only one NBR connector is allowed per company.')

    def _validate_api(self):
        self.ensure_one()
        if not self.enabled or self.transport != 'http_json':
            raise UserError(_('Enable an HTTP JSON NBR connector before using API submission.'))
        if not self.endpoint_url or not self.api_token:
            raise UserError(_('The official API endpoint and token are required for NBR submission.'))

    def action_test_connection(self):
        for connector in self:
            connector._validate_api()
            request = Request(connector.endpoint_url, data=b'{"operation":"health_check"}', headers={'Content-Type': 'application/json', 'Authorization': 'Bearer %s' % connector.api_token}, method='POST')
            try:
                with urlopen(request, timeout=15) as response:
                    connector.write({'last_tested_on': fields.Datetime.now(), 'last_test_result': _('Connection succeeded (HTTP %s).') % response.status})
            except (HTTPError, URLError, TimeoutError) as error:
                connector.write({'last_tested_on': fields.Datetime.now(), 'last_test_result': _('Connection failed: %s') % error})
                raise UserError(_('NBR connection failed: %s') % error)


class VatReturnNbr(models.Model):
    _inherit = 'vat.return'

    nbr_connector_id = fields.Many2one('vat.nbr.connector', string='NBR Connector', domain="[('company_id', '=', company_id)]")
    nbr_submission_mode = fields.Selection([('manual', 'Manual evidence'), ('api', 'API submission')], default='manual')
    nbr_submission_payload = fields.Text(readonly=True, copy=False)
    nbr_submission_response = fields.Text(readonly=True, copy=False)
    nbr_submission_status = fields.Selection([('not_sent', 'Not Sent'), ('prepared', 'Prepared'), ('accepted', 'Accepted'), ('failed', 'Failed')], default='not_sent', readonly=True, copy=False)

    def action_prepare_nbr_payload(self):
        for record in self:
            if record.state != 'approved':
                raise UserError(_('Approve the return before preparing an NBR submission payload.'))
            payload = {
                'form': 'Mushak 9.1', 'company_bin': record.company_id.vat_bin,
                'unit_bin': record.unit_id.bin if record.unit_id else record.company_id.vat_bin,
                'period_from': str(record.period_id.date_start), 'period_to': str(record.period_id.date_end),
                'output_vat': record.output_vat, 'input_vat': record.input_vat,
                'supplementary_duty': record.sd_amount, 'reverse_charge_vat': record.reverse_charge_vat,
                'net_payable': record.net_payable,
                'documents': [{'number': line.mushak_number, 'date': str(line.document_date), 'base': line.base_amount, 'output_vat': line.output_vat, 'input_vat': line.input_vat} for line in record.line_ids],
            }
            record.write({'nbr_submission_payload': json.dumps(payload, indent=2, default=str), 'nbr_submission_status': 'prepared'})

    def action_submit_nbr_api(self):
        for record in self:
            if record.nbr_submission_mode != 'api':
                raise UserError(_('Select API submission mode to submit through the configured NBR connector.'))
            if not record.nbr_submission_payload:
                record.action_prepare_nbr_payload()
            connector = record.nbr_connector_id
            if not connector:
                raise UserError(_('Select the company NBR connector first.'))
            connector._validate_api()
            request = Request(connector.endpoint_url, data=record.nbr_submission_payload.encode(), headers={'Content-Type': 'application/json', 'Authorization': 'Bearer %s' % connector.api_token}, method='POST')
            try:
                with urlopen(request, timeout=30) as response:
                    body = response.read().decode('utf-8')
                    data = json.loads(body) if body else {}
                    acknowledgement = data.get('acknowledgement') or data.get('reference')
                    if not acknowledgement:
                        raise UserError(_('The NBR API response has no acknowledgement/reference number.'))
                    record.write({'nbr_submission_response': body, 'nbr_acknowledgement': acknowledgement, 'nbr_submission_status': 'accepted'})
            except (HTTPError, URLError, TimeoutError, ValueError, UserError) as error:
                record.write({'nbr_submission_response': str(error), 'nbr_submission_status': 'failed'})
                raise UserError(_('NBR API submission failed: %s') % error)


class VatComplianceChecklist(models.Model):
    _name = 'vat.compliance.checklist'
    _description = 'NBR VAT Compliance Checklist'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'review_date desc, id desc'

    name = fields.Char(default=lambda self: _('New'), readonly=True, copy=False)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    review_date = fields.Date(required=True, default=fields.Date.context_today)
    scope = fields.Selection([('implementation', 'Implementation'), ('monthly_return', 'Monthly Return'), ('release', 'Release / Change')], default='implementation', required=True)
    line_ids = fields.One2many('vat.compliance.checklist.line', 'checklist_id')
    state = fields.Selection([('draft', 'Draft'), ('passed', 'Passed'), ('failed', 'Failed')], default='draft', tracking=True)
    attachment_ids = fields.Many2many('ir.attachment', string='Evidence')
    conclusion = fields.Text()

    def action_evaluate(self):
        for record in self:
            incomplete = record.line_ids.filtered(lambda line: line.status in ('not_tested', 'failed') or not line.evidence_note)
            record.state = 'failed' if incomplete else 'passed'
            record.conclusion = _('All checklist controls passed.') if not incomplete else _('%s control(s) require evidence or remediation.') % len(incomplete)


class VatComplianceChecklistLine(models.Model):
    _name = 'vat.compliance.checklist.line'
    _description = 'NBR VAT Compliance Checklist Line'

    checklist_id = fields.Many2one('vat.compliance.checklist', required=True, ondelete='cascade')
    requirement_code = fields.Char(required=True)
    requirement = fields.Char(required=True)
    status = fields.Selection([('not_tested', 'Not Tested'), ('passed', 'Passed'), ('failed', 'Failed'), ('not_applicable', 'Not Applicable')], default='not_tested', required=True)
    evidence_note = fields.Text()
    owner_id = fields.Many2one('res.users', default=lambda self: self.env.user)
    due_date = fields.Date()
