from datetime import date
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from .mushak_report import mushak_report_action


VAT_HEADS = [
    ('vat', 'VAT'), ('sd', 'Supplementary Duty'), ('at', 'Advance Tax'),
    ('ait', 'Advance Income Tax'), ('rd', 'Regulatory Duty'), ('cd', 'Customs Duty'),
    ('atv', 'Advance Trade VAT'), ('vds', 'VAT Deduction at Source'), ('tds', 'TDS'),
]


class VatHsCode(models.Model):
    _name = 'vat.hs.code'
    _description = 'VAT HS / Service Code'
    _order = 'code'
    _rec_name = 'display_name'

    code = fields.Char(required=True, index=True)
    name = fields.Char(required=True)
    code_type = fields.Selection([('goods', 'HS Code / Goods'), ('service', 'Service Code')], required=True, default='goods')
    chapter = fields.Char()
    vat_uom_id = fields.Many2one('uom.uom', string='VAT Unit of Measure')
    active = fields.Boolean(default=True)
    treatment = fields.Selection([('standard', 'Standard'), ('zero', 'Zero Rated'), ('exempt', 'Exempt'), ('export', 'Export'), ('epz', 'EPZ / Bonded')], default='standard', required=True)
    legal_reference = fields.Char(string='SRO / Legal Reference')
    tax_rule_ids = fields.One2many('vat.tax.rule', 'hs_code_id', string='Tax Rules')
    display_name = fields.Char(compute='_compute_display_name')

    _code_type_unique = models.Constraint(
        'UNIQUE(code, code_type)',
        'A code may only be used once for the same code type.',
    )

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for record in self:
            record.display_name = '%s - %s' % (record.code or '', record.name or '')


class VatTaxRule(models.Model):
    _name = 'vat.tax.rule'
    _description = 'VAT Tax Rule'
    _order = 'hs_code_id, date_from desc, sequence, id'

    sequence = fields.Integer(default=10)
    hs_code_id = fields.Many2one('vat.hs.code', required=True, ondelete='cascade')
    name = fields.Char(required=True)
    tax_head = fields.Selection(VAT_HEADS, required=True, default='vat')
    calculation = fields.Selection([('percent', 'Percentage'), ('fixed', 'Fixed per VAT UoM'), ('truncated', 'Truncated Base')], required=True, default='percent')
    rate = fields.Float(string='Rate / Amount', digits='Product Price', required=True)
    truncated_base_percent = fields.Float(string='Taxable Base %', default=100.0)
    price_include_sd = fields.Boolean(string='VAT Base Includes SD', default=False)
    date_from = fields.Date(required=True, default=fields.Date.context_today)
    date_to = fields.Date()
    account_tax_id = fields.Many2one('account.tax', string='Odoo Tax', help='Tax applied to Odoo invoices/bills for this rule.')
    sale_applicable = fields.Boolean(default=True)
    purchase_applicable = fields.Boolean(default=True)
    creditable = fields.Boolean(default=True)
    return_note = fields.Char(string='Mushak 9.1 Note')
    sro_reference = fields.Char(string='SRO / Notification')
    active = fields.Boolean(default=True)

    @api.constrains('date_from', 'date_to', 'rate', 'truncated_base_percent')
    def _check_values(self):
        for record in self:
            if record.date_to and record.date_to < record.date_from:
                raise ValidationError(_('End date cannot be earlier than start date.'))
            if record.rate < 0 or record.truncated_base_percent < 0:
                raise ValidationError(_('Rates cannot be negative.'))


class VatUnit(models.Model):
    _name = 'vat.unit'
    _description = 'VAT Registered Unit'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    unit_type = fields.Selection([('head_office', 'Head Office'), ('factory', 'Factory'), ('warehouse', 'Warehouse / Depot'), ('sales', 'Sales Centre'), ('branch', 'Branch')], required=True, default='head_office')
    registration_scope = fields.Selection([
        ('separate_bin', 'Separately VAT Registered (own BIN)'),
        ('sub_location', 'Sub-location under Company BIN'),
    ], string='VAT Registration', required=True, default='separate_bin', tracking=True)
    bin = fields.Char(string='Unit BIN', tracking=True)
    legacy_bin = fields.Char(string='Legacy Unit BIN', tracking=True)
    address = fields.Text(string='VAT Registered / Sub-location Address', required=True)
    warehouse_ids = fields.Many2many('stock.warehouse', string='Warehouses')
    user_ids = fields.Many2many('res.users', string='Allowed Users')
    business_type_ids = fields.Many2many('vat.business.type', string='Business Types')
    active = fields.Boolean(default=True)

    _code_company_unique = models.Constraint(
        'UNIQUE(code, company_id)',
        'Unit code must be unique per company.',
    )

    @api.constrains('bin', 'legacy_bin', 'registration_scope')
    def _check_bin(self):
        for record in self:
            if record.registration_scope == 'separate_bin' and (not record.bin or not record.bin.isdigit() or len(record.bin) != 13):
                raise ValidationError(_('A separately VAT-registered unit must have its own 13-digit BIN.'))
            if record.bin and (not record.bin.isdigit() or len(record.bin) != 13):
                raise ValidationError(_('Unit BIN must contain exactly 13 digits.'))
            if record.legacy_bin and (not record.legacy_bin.isdigit() or len(record.legacy_bin) != 11):
                raise ValidationError(_('Legacy unit BIN must contain exactly 11 digits.'))


class VatBusinessType(models.Model):
    _name = 'vat.business.type'
    _description = 'VAT Business Type'

    name = fields.Char(required=True)
    code = fields.Selection([('trading', 'Trading'), ('manufacturing', 'Manufacturing'), ('service', 'Service')], required=True)
    active = fields.Boolean(default=True)
    _business_type_code_unique = models.Constraint(
        'UNIQUE(code)',
        'Business type must be unique.',
    )


class VatHoliday(models.Model):
    _name = 'vat.holiday'
    _description = 'VAT Return Calendar Holiday'
    _order = 'date desc, name'

    name = fields.Char(required=True)
    date = fields.Date(required=True, index=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    active = fields.Boolean(default=True)

    _holiday_company_date_unique = models.Constraint(
        'UNIQUE(company_id, date)',
        'Only one VAT calendar holiday is allowed per company and date.',
    )


class VatPeriod(models.Model):
    _name = 'vat.period'
    _description = 'VAT Fiscal Period'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc'

    name = fields.Char(compute='_compute_name', store=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    unit_id = fields.Many2one('vat.unit', domain="[('company_id', '=', company_id)]")
    date_start = fields.Date(required=True, index=True)
    date_end = fields.Date(required=True, index=True)
    due_base_date = fields.Date(string='Statutory Due Date', readonly=True)
    due_date = fields.Date(required=True, help='Statutory due date after the configured holiday adjustment.')
    state = fields.Selection([('open', 'Open'), ('locked', 'Locked')], default='open', required=True, tracking=True)
    lock_reason = fields.Char(readonly=True)

    _period_company_unit_unique = models.Constraint(
        'UNIQUE(company_id, unit_id, date_start, date_end)',
        'This period already exists for this company/unit.',
    )

    @api.depends('date_start', 'date_end')
    def _compute_name(self):
        for record in self:
            record.name = '%s to %s' % (record.date_start or '', record.date_end or '')

    @api.constrains('date_start', 'date_end', 'due_date')
    def _check_dates(self):
        for record in self:
            if record.date_end < record.date_start:
                raise ValidationError(_('Period end must not precede the start.'))
            expected_end = record.date_start + relativedelta(months=1, days=-1)
            if record.date_start.day != 1 or record.date_end != expected_end:
                raise ValidationError(_('VAT fiscal periods must cover one complete calendar month.'))
            if record.due_date < record.date_end:
                raise ValidationError(_('Return due date cannot be before the end of the VAT period.'))

    @api.model
    def _get_base_due_date(self, company, date_end):
        due_day = company.vat_return_due_day or 15
        return date_end + relativedelta(months=1, day=due_day)

    @api.model
    def _get_adjusted_due_date(self, company, base_due_date):
        """Move a statutory due date around weekends and configured VAT holidays."""
        policy = company.vat_holiday_adjustment or 'next_working_day'
        if policy == 'none':
            return base_due_date
        direction = 1 if policy == 'next_working_day' else -1
        candidate = base_due_date
        Holiday = self.env['vat.holiday'].sudo()
        while candidate.weekday() >= 5 or Holiday.search_count([
            ('company_id', '=', company.id), ('date', '=', candidate), ('active', '=', True),
        ]):
            candidate += relativedelta(days=direction)
        return candidate

    @api.onchange('company_id', 'date_start', 'date_end')
    def _onchange_period_dates(self):
        for record in self:
            if record.company_id and record.date_end:
                base_due_date = record._get_base_due_date(record.company_id, record.date_end)
                record.due_base_date = base_due_date
                record.due_date = record._get_adjusted_due_date(record.company_id, base_due_date)

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for vals in vals_list:
            values = dict(vals)
            company = self.env['res.company'].browse(values.get('company_id')) or self.env.company
            date_end = fields.Date.to_date(values.get('date_end')) if values.get('date_end') else False
            if date_end:
                base_due_date = self._get_base_due_date(company, date_end)
                values.setdefault('due_base_date', base_due_date)
                values.setdefault('due_date', self._get_adjusted_due_date(company, base_due_date))
            prepared.append(values)
        return super().create(prepared)

    def write(self, vals):
        if {'company_id', 'date_start', 'date_end'} & set(vals) and 'due_date' not in vals:
            for record in self:
                values = dict(vals)
                company = self.env['res.company'].browse(values.get('company_id')) or record.company_id
                date_end = fields.Date.to_date(values.get('date_end')) if values.get('date_end') else record.date_end
                base_due_date = self._get_base_due_date(company, date_end)
                values.update({
                    'due_base_date': base_due_date,
                    'due_date': self._get_adjusted_due_date(company, base_due_date),
                })
                super(VatPeriod, record).write(values)
            return True
        return super().write(vals)

    @api.model
    def create_monthly_periods(self, company, year, unit=False, due_day=False):
        due_day = due_day or company.vat_return_due_day or 15
        start = date(year, 1, 1)
        for month in range(12):
            period_start = start + relativedelta(months=month)
            period_end = period_start + relativedelta(months=1, days=-1)
            base_due_date = period_end + relativedelta(months=1, day=due_day)
            due = self._get_adjusted_due_date(company, base_due_date)
            self.get_or_create_period(company, period_start, period_end, due, unit, base_due_date)

    @api.model
    def get_or_create_period(self, company, date_start, date_end, due_date, unit=False, due_base_date=False):
        domain = [('company_id', '=', company.id), ('unit_id', '=', unit.id if unit else False), ('date_start', '=', date_start), ('date_end', '=', date_end)]
        return self.search(domain, limit=1) or self.create({
            'company_id': company.id,
            'unit_id': unit.id if unit else False,
            'date_start': date_start,
            'date_end': date_end,
            'due_base_date': due_base_date or due_date,
            'due_date': due_date,
        })

    def action_recalculate_due_date(self):
        for record in self:
            base_due_date = record._get_base_due_date(record.company_id, record.date_end)
            record.write({
                'due_base_date': base_due_date,
                'due_date': record._get_adjusted_due_date(record.company_id, base_due_date),
            })

    def action_lock(self):
        self.write({'state': 'locked', 'lock_reason': _('Locked by VAT return submission')})

    def action_reopen(self):
        if not self.env.user.has_group('zsl_vat.group_vat_manager'):
            raise UserError(_('Only a VAT Manager can reopen a period.'))
        self.write({'state': 'open', 'lock_reason': False})

    @api.model
    def _cron_send_due_alerts(self):
        """Create one review activity per manager for returns due in the next 7 days."""
        today = fields.Date.context_today(self)
        limit = today + relativedelta(days=7)
        periods = self.search([('state', '=', 'open'), ('due_date', '>=', today), ('due_date', '<=', limit)])
        managers = self.env.ref('zsl_vat.group_vat_manager').users
        activity_type = self.env.ref('zsl_vat.mail_activity_type_vat_review')
        for period in periods:
            existing = self.env['mail.activity'].search_count([('res_model', '=', 'vat.period'), ('res_id', '=', period.id), ('activity_type_id', '=', activity_type.id), ('date_deadline', '=', period.due_date)])
            if not existing:
                for user in managers.filtered(lambda u: period.company_id in u.company_ids):
                    period.activity_schedule(activity_type.id, user_id=user.id, date_deadline=period.due_date, summary=_('VAT return due: %s') % period.name)


class VatDocumentSeries(models.Model):
    _name = 'vat.document.series'
    _description = 'Mushak Document Series'
    _order = 'company_id, unit_id, document_type'

    name = fields.Char(required=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    unit_id = fields.Many2one('vat.unit', domain="[('company_id', '=', company_id)]")
    document_type = fields.Selection([('63', 'Mushak 6.3 Tax Invoice'), ('64', 'Mushak 6.4 Contract Manufacturing'), ('65', 'Mushak 6.5 Transfer Challan'), ('66', 'Mushak 6.6 VDS Certificate'), ('67', 'Mushak 6.7 Credit Note'), ('68', 'Mushak 6.8 Debit Note'), ('91', 'Mushak 9.1 VAT Return')], required=True)
    sequence_id = fields.Many2one('ir.sequence', ondelete='restrict', readonly=True,
        help='Created automatically. One no-gap fiscal-year sequence is kept for this document type and VAT unit.')
    active = fields.Boolean(default=True)
    _series_unique = models.Constraint(
        'UNIQUE(company_id, unit_id, document_type)',
        'Only one series is allowed per company, unit and document type.',
    )

    @api.model
    def _sequence_prefix(self, document_type, unit=False):
        document_number = document_type[:1] + '.' + document_type[1:]
        unit_code = unit.code if unit else 'COMPANY'
        return '%s/%s/FY%%(range_year)s/' % (document_number, unit_code)

    @api.model
    def _create_sequence(self, document_type, company, unit=False):
        document_number = document_type[:1] + '.' + document_type[1:]
        unit_label = unit.code if unit else _('Company')
        return self.env['ir.sequence'].sudo().create({
            'name': _('Mushak %s — %s') % (document_number, unit_label),
            'code': 'zsl_vat.mushak_%s.%s.%s' % (document_type, company.id, unit.id if unit else 'company'),
            'prefix': self._sequence_prefix(document_type, unit),
            'padding': 6,
            'implementation': 'no_gap',
            'use_date_range': True,
            'company_id': company.id,
        })

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for vals in vals_list:
            values = dict(vals)
            company = self.env['res.company'].browse(values.get('company_id')) or self.env.company
            unit = self.env['vat.unit'].browse(values.get('unit_id'))
            if not values.get('sequence_id'):
                values['sequence_id'] = self._create_sequence(values['document_type'], company, unit).id
            prepared.append(values)
        return super().create(prepared)

    @api.model
    def _ensure_fiscal_date_range(self, sequence, company, sequence_date):
        sequence_date = fields.Date.to_date(sequence_date) or fields.Date.context_today(self)
        fiscal_start_month = int(company.vat_fiscal_year_start_month or '7')
        fiscal_start_year = sequence_date.year if sequence_date.month >= fiscal_start_month else sequence_date.year - 1
        fiscal_start = date(fiscal_start_year, fiscal_start_month, 1)
        fiscal_end = fiscal_start + relativedelta(years=1, days=-1)
        date_range = self.env['ir.sequence.date_range'].sudo().search([
            ('sequence_id', '=', sequence.id), ('date_from', '<=', sequence_date), ('date_to', '>=', sequence_date),
        ], limit=1)
        if not date_range:
            self.env['ir.sequence.date_range'].sudo().create({
                'sequence_id': sequence.id,
                'date_from': fiscal_start,
                'date_to': fiscal_end,
                'number_next': 1,
            })

    @api.model
    def _get_or_create_series(self, document_type, company, unit=False):
        domain = [
            ('company_id', '=', company.id),
            ('unit_id', '=', unit.id if unit else False),
            ('document_type', '=', document_type),
            ('active', '=', True),
        ]
        series = self.search(domain, limit=1)
        if not series:
            series = self.sudo().create({
                'name': _('Mushak %s — %s') % (document_type[:1] + '.' + document_type[1:], unit.code if unit else _('Company')),
                'company_id': company.id,
                'unit_id': unit.id if unit else False,
                'document_type': document_type,
            })
        return series

    @api.model
    def next_number(self, document_type, company, unit=False, sequence_date=False):
        series = self._get_or_create_series(document_type, company, unit)
        sequence = series.sequence_id.sudo()
        expected_prefix = self._sequence_prefix(document_type, unit)
        # Legacy configuration is normalised before it can issue a number: this
        # prevents duplicate serials when a new fiscal year begins.
        if not sequence.use_date_range or sequence.prefix != expected_prefix:
            sequence.write({'use_date_range': True, 'prefix': expected_prefix, 'implementation': 'no_gap'})
        self._ensure_fiscal_date_range(sequence, company, sequence_date or fields.Date.context_today(self))
        return sequence.next_by_id(sequence_date=sequence_date or fields.Date.context_today(self))


class VatPriceDeclaration(models.Model):
    _name = 'vat.price.declaration'
    _description = 'Mushak 4.3 Price Declaration'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'effective_date desc, id desc'

    name = fields.Char(required=True, default=lambda self: _('New'))
    product_tmpl_id = fields.Many2one('product.template', required=True, ondelete='restrict')
    unit_id = fields.Many2one('vat.unit')
    effective_date = fields.Date(required=True, default=fields.Date.context_today)
    declared_price = fields.Monetary(required=True, tracking=True)
    currency_id = fields.Many2one(related='product_tmpl_id.currency_id')
    state = fields.Selection([('draft', 'Draft'), ('approved', 'Approved'), ('superseded', 'Superseded')], default='draft', tracking=True)
    approval_reference = fields.Char()
    attachment_ids = fields.Many2many('ir.attachment', string='Supporting Documents')

    def action_approve(self):
        if not self.env.user.has_group('zsl_vat.group_vat_officer'):
            raise UserError(_('A VAT Officer must approve a price declaration.'))
        for record in self:
            record.search([('product_tmpl_id', '=', record.product_tmpl_id.id), ('unit_id', '=', record.unit_id.id), ('state', '=', 'approved'), ('id', '!=', record.id)]).write({'state': 'superseded'})
            record.state = 'approved'


class VatIoCoefficient(models.Model):
    _name = 'vat.io.coefficient'
    _description = 'Mushak 4.3 Input-Output Coefficient'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'effective_date desc, id desc'

    name = fields.Char(required=True, default=lambda self: _('New'))
    product_tmpl_id = fields.Many2one('product.template', required=True)
    bom_id = fields.Many2one('mrp.bom', domain="[('product_tmpl_id', '=', product_tmpl_id)]")
    effective_date = fields.Date(required=True, default=fields.Date.context_today)
    output_qty = fields.Float(default=1.0, required=True)
    wastage_percent = fields.Float(default=0.0)
    value_addition = fields.Monetary(currency_field='currency_id')
    currency_id = fields.Many2one(related='product_tmpl_id.currency_id')
    line_ids = fields.One2many('vat.io.coefficient.line', 'coefficient_id', string='Inputs')
    material_cost = fields.Monetary(compute='_compute_totals', currency_field='currency_id')
    declared_price = fields.Monetary(compute='_compute_totals', currency_field='currency_id')
    state = fields.Selection([('draft', 'Draft'), ('approved', 'Approved'), ('superseded', 'Superseded')], default='draft', tracking=True)

    @api.depends('line_ids.subtotal', 'value_addition')
    def _compute_totals(self):
        for record in self:
            record.material_cost = sum(record.line_ids.mapped('subtotal'))
            record.declared_price = record.material_cost + record.value_addition

    def action_load_bom(self):
        for record in self:
            if not record.bom_id:
                raise UserError(_('Select a bill of materials first.'))
            record.line_ids = [(5, 0, 0)] + [(0, 0, {'product_id': line.product_id.id, 'quantity': line.product_qty, 'uom_id': line.product_uom_id.id, 'unit_cost': line.product_id.standard_price}) for line in record.bom_id.bom_line_ids]

    def action_approve(self):
        if not self.env.user.has_group('zsl_vat.group_vat_officer'):
            raise UserError(_('A VAT Officer must approve a coefficient.'))
        for record in self:
            record.search([('product_tmpl_id', '=', record.product_tmpl_id.id), ('state', '=', 'approved'), ('id', '!=', record.id)]).write({'state': 'superseded'})
            record.state = 'approved'

    def action_print_mushak_43(self):
        self.ensure_one()
        return mushak_report_action(self, '4.3')


class VatIoCoefficientLine(models.Model):
    _name = 'vat.io.coefficient.line'
    _description = 'Input-Output Coefficient Line'

    coefficient_id = fields.Many2one('vat.io.coefficient', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', required=True)
    quantity = fields.Float(required=True, default=1.0)
    uom_id = fields.Many2one('uom.uom', required=True)
    unit_cost = fields.Monetary(required=True, currency_field='currency_id')
    currency_id = fields.Many2one(related='coefficient_id.currency_id')
    subtotal = fields.Monetary(compute='_compute_subtotal', store=True, currency_field='currency_id')

    @api.depends('quantity', 'unit_cost')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.unit_cost
