from odoo import api, fields, models


class ZencoreHSCode(models.Model):
    """VAT extensions to the customer-supplied Zencore HS-code master."""
    _inherit = 'zencore.hs.code'

    code_type = fields.Selection([
        ('goods', 'HS Code / Goods'),
        ('service', 'Service Code'),
    ], required=True, default='goods')
    vat_uom_id = fields.Many2one('uom.uom', string='Legal / VAT UoM')
    treatment = fields.Selection([
        ('standard', 'Standard'), ('zero', 'Zero Rated'), ('exempt', 'Exempt'),
        ('export', 'Export'), ('epz', 'EPZ / Bonded'),
    ], default='standard', required=True)
    vds_rate = fields.Float(string='Default VDS Rate %')
    tax_rule_ids = fields.One2many('vat.tax.rule', 'zencore_hs_code_id', string='VAT Duty Rules')


class VatTaxRule(models.Model):
    _inherit = 'vat.tax.rule'

    zencore_hs_code_id = fields.Many2one('zencore.hs.code', string='Zencore HS / Service Code', ondelete='cascade', index=True)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.onchange('hs_code_id')
    def _onchange_zencore_hs_code_id_vat(self):
        for product in self:
            code = product.hs_code_id
            if not code:
                continue
            product.vat_uom_id = code.vat_uom_id or product.uom_id
            product.vat_special_treatment = code.treatment
            product.vat_vds_rate = code.vds_rate
            today = fields.Date.context_today(product)
            rules = code.tax_rule_ids.filtered(
                lambda rule: rule.active and rule.date_from <= today and
                (not rule.date_to or rule.date_to >= today) and rule.account_tax_id
            )
            product.taxes_id = [(6, 0, rules.filtered('sale_applicable').mapped('account_tax_id').ids)]
            product.supplier_taxes_id = [(6, 0, rules.filtered('purchase_applicable').mapped('account_tax_id').ids)]
