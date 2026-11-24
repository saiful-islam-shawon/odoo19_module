from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from .mushak_report import mushak_report_action


class StockLandedCost(models.Model):
    _inherit = 'stock.landed.cost'

    vat_unit_id = fields.Many2one('vat.unit', string='VAT Unit', domain="[('company_id', '=', company_id)]")
    vat_import_reference = fields.Char(string='Bill of Entry / Import Reference')
    vat_creditable_tax_line_ids = fields.One2many('vat.import.creditable.tax', 'landed_cost_id', string='Creditable Import Taxes')
    vat_creditable_tax_total = fields.Monetary(compute='_compute_vat_tax_split', currency_field='currency_id')
    vat_cost_bearing_total = fields.Monetary(compute='_compute_vat_tax_split', currency_field='currency_id')

    @api.depends('cost_lines.price_unit', 'cost_lines.vat_duty_type', 'cost_lines.vat_creditable', 'vat_creditable_tax_line_ids.amount')
    def _compute_vat_tax_split(self):
        for cost in self:
            cost.vat_creditable_tax_total = sum(cost.vat_creditable_tax_line_ids.mapped('amount'))
            cost.vat_cost_bearing_total = sum(cost.cost_lines.mapped('price_unit'))

    @api.constrains('cost_lines', 'vat_import_reference')
    def _check_vat_import_costs(self):
        for cost in self:
            if cost.vat_import_reference and not cost.picking_ids:
                raise ValidationError(_('Select imported stock transfers before allocating import costs.'))


class VatImportCreditableTax(models.Model):
    _name = 'vat.import.creditable.tax'
    _description = 'Creditable Import VAT / AT'

    landed_cost_id = fields.Many2one('stock.landed.cost', required=True, ondelete='cascade')
    tax_type = fields.Selection([('vat', 'Import VAT'), ('at', 'Advance Tax (AT)')], required=True)
    amount = fields.Monetary(required=True, currency_field='currency_id')
    bill_of_entry = fields.Char()
    evidence_id = fields.Many2one('ir.attachment', ondelete='restrict')
    currency_id = fields.Many2one(related='landed_cost_id.currency_id')


class StockLandedCostLine(models.Model):
    _inherit = 'stock.landed.cost.lines'

    vat_duty_type = fields.Selection([
        ('freight', 'Freight'), ('insurance', 'Insurance'), ('clearing', 'Clearing Charge'),
        ('cd', 'Customs Duty (CD)'), ('rd', 'Regulatory Duty (RD)'),
        ('sd', 'Supplementary Duty (SD)'), ('vat', 'VAT'), ('at', 'Advance Tax (AT)'),
        ('ait', 'Advance Income Tax (AIT)'), ('other', 'Other'),
    ], string='VAT Cost / Duty Type', required=True, default='other')
    vat_creditable = fields.Boolean(string='Creditable Tax', default=False,
        help='For reporting only. Enter creditable VAT/AT on the separate Creditable Import Taxes tab.')

    @api.onchange('vat_duty_type')
    def _onchange_vat_duty_type(self):
        for line in self:
            if line.vat_duty_type in ('vat', 'at'):
                line.vat_creditable = True
            elif line.vat_duty_type in ('freight', 'insurance', 'clearing', 'cd', 'rd', 'sd', 'ait'):
                line.vat_creditable = False

    @api.constrains('vat_creditable')
    def _check_creditable_landed_cost(self):
        if any(self.mapped('vat_creditable')):
            raise ValidationError(_('Creditable VAT/AT must be recorded on the Creditable Import Taxes tab, not allocated into stock cost.'))


class VatStockOpening(models.Model):
    _name = 'vat.stock.opening'
    _description = 'VAT Stock Opening Balance'
    _order = 'effective_date desc, id desc'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    unit_id = fields.Many2one('vat.unit', required=True, domain="[('company_id', '=', company_id)]")
    product_id = fields.Many2one('product.product', required=True)
    effective_date = fields.Date(required=True, default=fields.Date.context_today)
    vat_uom_id = fields.Many2one(related='product_id.product_tmpl_id.vat_uom_id', readonly=True)
    quantity = fields.Float(required=True)
    value = fields.Monetary(required=True, currency_field='currency_id')
    source_reference = fields.Char(required=True)
    currency_id = fields.Many2one(related='company_id.currency_id')

    _opening_unique = models.Constraint(
        'UNIQUE(company_id, unit_id, product_id, effective_date)',
        'Only one opening balance is allowed per product, unit and effective date.',
    )

    @api.constrains('quantity', 'value')
    def _check_non_negative(self):
        for line in self:
            if line.quantity < 0 or line.value < 0:
                raise ValidationError(_('Opening quantity and value cannot be negative.'))


class VatStockRegister(models.Model):
    _name = 'vat.stock.register'
    _description = 'VAT Stock Register'
    _order = 'period_id desc, id desc'

    name = fields.Char(compute='_compute_name', store=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    unit_id = fields.Many2one('vat.unit', required=True, domain="[('company_id', '=', company_id)]")
    period_id = fields.Many2one('vat.period', required=True, domain="[('company_id', '=', company_id), ('unit_id', '=', unit_id)]")
    line_ids = fields.One2many('vat.stock.register.line', 'register_id', copy=False)
    state = fields.Selection([('draft', 'Draft'), ('generated', 'Generated'), ('locked', 'Locked')], default='draft', required=True)

    _register_period_unique = models.Constraint(
        'UNIQUE(company_id, unit_id, period_id)',
        'A VAT stock register already exists for this unit and period.',
    )

    @api.depends('unit_id', 'period_id')
    def _compute_name(self):
        for record in self:
            record.name = '%s — %s' % (record.unit_id.display_name or '', record.period_id.display_name or '')

    def action_generate(self):
        Move = self.env['stock.move']
        for register in self:
            if register.state == 'locked':
                raise UserError(_('A locked VAT stock register cannot be regenerated.'))
            register.line_ids.unlink()
            domain = [
                ('state', '=', 'done'), ('picking_id.vat_unit_id', '=', register.unit_id.id),
                ('date', '>=', register.period_id.date_start), ('date', '<=', register.period_id.date_end),
            ]
            moves = Move.search(domain)
            products = moves.product_id | self.env['vat.stock.opening'].search([
                ('company_id', '=', register.company_id.id), ('unit_id', '=', register.unit_id.id),
                ('effective_date', '<=', register.period_id.date_start),
            ]).product_id
            for product in products:
                opening = self.env['vat.stock.opening'].search([
                    ('company_id', '=', register.company_id.id), ('unit_id', '=', register.unit_id.id),
                    ('product_id', '=', product.id), ('effective_date', '<=', register.period_id.date_start),
                ], order='effective_date desc', limit=1)
                product_moves = moves.filtered(lambda move: move.product_id == product)
                incoming = product_moves.filtered(lambda move: move.location_dest_id.usage == 'internal' and move.location_id.usage != 'internal')
                outgoing = product_moves.filtered(lambda move: move.location_id.usage == 'internal' and move.location_dest_id.usage != 'internal')
                transfer_in = product_moves.filtered(lambda move: move.location_dest_id.usage == 'internal' and move.location_id.usage == 'internal' and move.picking_id.picking_type_id.code == 'internal')
                adjustments = self.env['vat.stock.adjustment'].search([
                    ('company_id', '=', register.company_id.id), ('unit_id', '=', register.unit_id.id),
                    ('product_id', '=', product.id), ('state', '=', 'posted'),
                    ('adjustment_date', '>=', register.period_id.date_start), ('adjustment_date', '<=', register.period_id.date_end),
                ])
                register.line_ids.create({
                    'register_id': register.id, 'product_id': product.id,
                    'opening_qty': opening.quantity if opening else 0, 'opening_value': opening.value if opening else 0,
                    'purchase_qty': sum(incoming.mapped('quantity')), 'transfer_in_qty': sum(transfer_in.mapped('quantity')),
                    'sale_qty': sum(outgoing.mapped('quantity')), 'adjustment_qty': -sum(adjustments.mapped('quantity')),
                })
            register.state = 'generated'

    def action_lock(self):
        self.write({'state': 'locked'})

    def action_print_stock_register(self):
        self.ensure_one()
        if self.state == 'draft':
            raise UserError(_('Generate the stock register before printing it.'))
        return mushak_report_action(self, '6.2.1')


class VatStockRegisterLine(models.Model):
    _name = 'vat.stock.register.line'
    _description = 'VAT Stock Register Line'

    register_id = fields.Many2one('vat.stock.register', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', required=True)
    vat_uom_id = fields.Many2one(related='product_id.product_tmpl_id.vat_uom_id', readonly=True)
    opening_qty = fields.Float()
    opening_value = fields.Monetary(currency_field='currency_id')
    purchase_qty = fields.Float()
    transfer_in_qty = fields.Float()
    sale_qty = fields.Float()
    adjustment_qty = fields.Float()
    closing_qty = fields.Float(compute='_compute_closing', store=True)
    currency_id = fields.Many2one(related='register_id.company_id.currency_id')

    @api.depends('opening_qty', 'purchase_qty', 'transfer_in_qty', 'sale_qty', 'adjustment_qty')
    def _compute_closing(self):
        for line in self:
            line.closing_qty = line.opening_qty + line.purchase_qty + line.transfer_in_qty - line.sale_qty + line.adjustment_qty


class VatStockAdjustment(models.Model):
    _name = 'vat.stock.adjustment'
    _description = 'VAT Stock Damage / Destruction Adjustment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'adjustment_date desc, id desc'

    name = fields.Char(required=True, default=lambda self: _('New'), readonly=True, copy=False)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    unit_id = fields.Many2one('vat.unit', required=True, domain="[('company_id', '=', company_id)]")
    product_id = fields.Many2one('product.product', required=True)
    adjustment_type = fields.Selection([('damage', 'Damage'), ('destruction', 'Destruction'), ('shortage', 'Shortage'), ('sample', 'Sample Issue')], required=True)
    adjustment_date = fields.Date(default=fields.Date.context_today, required=True)
    quantity = fields.Float(required=True)
    reason = fields.Text(required=True)
    scrap_id = fields.Many2one('stock.scrap', string='Stock Scrap', readonly=True, ondelete='restrict')
    input_vat_reversal = fields.Monetary(string='Input VAT Reversal', currency_field='currency_id')
    vat_return_id = fields.Many2one('vat.return', string='Mushak 9.1 Return', domain="[('company_id', '=', company_id), ('unit_id', '=', unit_id)]")
    vat_adjustment_id = fields.Many2one('vat.adjustment', string='Generated VAT Adjustment', readonly=True, ondelete='restrict')
    evidence_ids = fields.Many2many('ir.attachment', string='Evidence')
    state = fields.Selection([('draft', 'Draft'), ('approved', 'Approved'), ('posted', 'Posted'), ('rejected', 'Rejected')], default='draft', tracking=True)
    approver_id = fields.Many2one('res.users', readonly=True)
    currency_id = fields.Many2one(related='company_id.currency_id')

    @api.constrains('quantity', 'input_vat_reversal')
    def _check_amounts(self):
        for record in self:
            if record.quantity <= 0 or record.input_vat_reversal < 0:
                raise ValidationError(_('Quantity must be positive and input VAT reversal cannot be negative.'))

    def action_approve(self):
        if not self.env.user.has_group('zsl_vat.group_vat_manager'):
            raise UserError(_('Only a VAT Manager can approve stock damage or destruction.'))
        for record in self:
            if not record.evidence_ids:
                raise UserError(_('Attach evidence before approving a VAT stock adjustment.'))
            record.write({'state': 'approved', 'approver_id': self.env.user.id})

    def action_post(self):
        for record in self:
            if record.state != 'approved':
                raise UserError(_('Only an approved stock adjustment can be posted.'))
            scrap = self.env['stock.scrap'].create({
                'product_id': record.product_id.id, 'scrap_qty': record.quantity,
                'company_id': record.company_id.id, 'origin': record.name,
            })
            scrap.action_validate()
            vat_adjustment = self.env['vat.adjustment']
            if record.input_vat_reversal:
                if not record.vat_return_id:
                    raise UserError(_('Select the Mushak 9.1 return that will carry the input VAT reversal.'))
                vat_adjustment = self.env['vat.adjustment'].create({
                    'return_id': record.vat_return_id.id, 'name': record.name if record.name != _('New') else _('Stock adjustment'),
                    'adjustment_type': 'increase', 'amount': record.input_vat_reversal,
                    'return_note': _('Input VAT reversal for %s') % record.adjustment_type,
                    'reason': record.reason, 'attachment_ids': [(6, 0, record.evidence_ids.ids)], 'state': 'approved',
                })
            record.write({'name': record.name if record.name != _('New') else self.env['ir.sequence'].next_by_code('zsl_vat.stock_adjustment') or _('New'), 'scrap_id': scrap.id, 'vat_adjustment_id': vat_adjustment.id, 'state': 'posted'})

    def action_print_mushak_44(self):
        self.ensure_one()
        if self.adjustment_type not in ('damage', 'destruction'):
            raise UserError(_('Mushak 4.4 is only for damage or destruction records.'))
        return mushak_report_action(self, '4.4')

    def action_print_mushak_45(self):
        self.ensure_one()
        if self.adjustment_type not in ('shortage', 'sample'):
            raise UserError(_('Mushak 4.5 is only for shortage or sample adjustment records.'))
        return mushak_report_action(self, '4.5')
