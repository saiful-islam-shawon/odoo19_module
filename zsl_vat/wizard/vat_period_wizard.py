from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class VatPeriodGenerateWizard(models.TransientModel):
    _name = 'vat.period.generate.wizard'
    _description = 'Generate Monthly VAT Fiscal Periods'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    unit_id = fields.Many2one('vat.unit', string='VAT Unit', domain="[('company_id', '=', company_id)]")
    year = fields.Integer(required=True, default=lambda self: fields.Date.context_today(self).year)
    due_day = fields.Integer(required=True, default=lambda self: self.env.company.vat_return_due_day or 15)

    @api.onchange('company_id')
    def _onchange_company_id(self):
        if self.company_id:
            self.due_day = self.company_id.vat_return_due_day or 15

    def action_generate(self):
        self.ensure_one()
        if not 1 <= self.due_day <= 28:
            raise ValidationError(_('Due day must be between 1 and 28.'))
        if self.year < 2000 or self.year > 2100:
            raise ValidationError(_('Enter a valid fiscal calendar year.'))
        self.env['vat.period'].create_monthly_periods(
            self.company_id, self.year, self.unit_id, self.due_day,
        )
        return {
            'type': 'ir.actions.act_window',
            'name': _('VAT Periods'),
            'res_model': 'vat.period',
            'view_mode': 'list,form',
            'domain': [
                ('company_id', '=', self.company_id.id),
                ('unit_id', '=', self.unit_id.id if self.unit_id else False),
                ('date_start', '>=', date(self.year, 1, 1)),
                ('date_start', '<=', date(self.year, 12, 31)),
            ],
        }
