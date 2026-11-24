from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    vat_hs_code_id = fields.Many2one('vat.hs.code', string='HS / Service Code', tracking=True)
    vat_uom_id = fields.Many2one('uom.uom', string='VAT UoM')
    vat_uom_factor = fields.Float(string='Operational → VAT UoM Factor', default=1.0, help='Number of VAT units represented by one operational unit.')
    vat_special_treatment = fields.Selection([('standard', 'Standard'), ('zero', 'Zero Rated'), ('exempt', 'Exempt'), ('export', 'Export'), ('epz', 'EPZ / Bonded')], default='standard')
    vat_declared_price = fields.Monetary(compute='_compute_vat_declaration', currency_field='currency_id')
    vat_declaration_id = fields.Many2one('vat.price.declaration', compute='_compute_vat_declaration')
    vat_price_policy = fields.Selection([('none', 'No Control'), ('warn', 'Warn'), ('block', 'Block')], default='warn', string='Price Declaration Policy')
    vat_vds_rate = fields.Float(string='VDS Rate %')
    vat_input_credit = fields.Selection([('creditable', 'Creditable'), ('non_creditable', 'Non-creditable'), ('partial', 'Partially Creditable')], default='creditable')
    vat_is_capital_good = fields.Boolean(string='Capital Good')
    vat_traceability_required = fields.Boolean(
        string='VAT Batch / Serial Traceability Required',
        help='Require a lot/batch or serial number on stock moves before the VAT delivery can be validated.',
    )

    @api.depends('vat_hs_code_id', 'vat_hs_code_id.tax_rule_ids', 'vat_hs_code_id.tax_rule_ids.date_from', 'vat_hs_code_id.tax_rule_ids.date_to')
    def _compute_vat_declaration(self):
        Declaration = self.env['vat.price.declaration']
        today = fields.Date.context_today(self)
        for product in self:
            declaration = Declaration.search([('product_tmpl_id', '=', product.id), ('state', '=', 'approved'), ('effective_date', '<=', today)], order='effective_date desc, id desc', limit=1)
            product.vat_declaration_id = declaration
            product.vat_declared_price = declaration.declared_price

    @api.onchange('vat_hs_code_id')
    def _onchange_vat_hs_code_id(self):
        if not self.vat_hs_code_id:
            return
        self.vat_uom_id = self.vat_hs_code_id.vat_uom_id or self.uom_id
        self.vat_special_treatment = self.vat_hs_code_id.treatment
        today = fields.Date.context_today(self)
        rules = self.vat_hs_code_id.tax_rule_ids.filtered(lambda r: r.active and r.date_from <= today and (not r.date_to or r.date_to >= today) and r.account_tax_id)
        self.taxes_id = [(6, 0, rules.filtered('sale_applicable').mapped('account_tax_id').ids)]
        self.supplier_taxes_id = [(6, 0, rules.filtered('purchase_applicable').mapped('account_tax_id').ids)]

    @api.constrains('vat_uom_factor')
    def _check_vat_uom_factor(self):
        for product in self:
            if product.vat_uom_factor <= 0:
                raise ValidationError(_('VAT UoM conversion factor must be greater than zero.'))
