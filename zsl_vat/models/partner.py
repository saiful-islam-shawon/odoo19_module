from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    vat_registration_status = fields.Selection([('registered', 'VAT Registered'), ('unregistered', 'Unregistered'), ('turnover', 'Turnover Taxpayer'), ('foreign', 'Foreign / Non-resident')], default='registered', string='VAT Registration Status')
    vat_bin = fields.Char(string='VAT BIN', index=True)
    vat_legacy_bin = fields.Char(string='Legacy BIN')
    vat_nid = fields.Char(string='NID')
    vat_tin = fields.Char(string='TIN')
    vat_partner_category = fields.Selection([('supplier', 'Supplier'), ('customer', 'Customer'), ('both', 'Both'), ('government', 'Government / VDS Entity')], default='both')
    vat_vds_withholding_entity = fields.Boolean(string='VDS Withholding Entity')
    vat_vds_applicable_supplier = fields.Boolean(string='VDS Applies on Supplier')
    vat_vds_rate = fields.Float(string='Default VDS Rate %')

    @api.constrains('vat_bin', 'vat_legacy_bin')
    def _check_vat_bins(self):
        for partner in self:
            for value, label in ((partner.vat_bin, _('VAT BIN')), (partner.vat_legacy_bin, _('Legacy BIN'))):
                if value and (not value.isdigit() or len(value) not in (11, 13)):
                    raise ValidationError(_('%s must contain exactly 11 or 13 digits.', label))
            if partner.vat_bin:
                duplicate = self.with_context(active_test=False).search([('vat_bin', '=', partner.vat_bin), ('id', '!=', partner.id)], limit=1)
                if duplicate:
                    raise ValidationError(_('VAT BIN %s is already assigned to %s.', partner.vat_bin, duplicate.display_name))
