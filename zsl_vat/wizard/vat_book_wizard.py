from odoo import fields, models
from odoo.addons.zsl_vat.models.mushak_report import mushak_report_action


class VatBookWizard(models.TransientModel):
    _name = 'vat.book.wizard'
    _description = 'VAT Book Print Wizard'

    period_id = fields.Many2one('vat.period', required=True, default=lambda self: self.env['vat.period'].search([('company_id', '=', self.env.company.id), ('state', '=', 'open')], order='date_start desc', limit=1))
    unit_id = fields.Many2one('vat.unit', domain="[('company_id', '=', company_id)]")
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    book_type = fields.Selection([('purchase', 'Purchase Book (Mushak 6.1)'), ('sales', 'Sales Book (Mushak 6.2)'), ('high_value', 'High-Value Transactions (Mushak 6.10)')], required=True, default='sales')

    def _moves(self):
        self.ensure_one()
        domain = [('company_id', '=', self.company_id.id), ('state', '=', 'posted'), ('invoice_date', '>=', self.period_id.date_start), ('invoice_date', '<=', self.period_id.date_end)]
        move_types = (
            ('in_invoice', 'in_refund') if self.book_type == 'purchase'
            else ('in_invoice', 'in_refund', 'out_invoice', 'out_refund') if self.book_type == 'high_value'
            else ('out_invoice', 'out_refund')
        )
        domain.append(('move_type', 'in', move_types))
        if self.unit_id:
            domain.append(('vat_unit_id', '=', self.unit_id.id))
        moves = self.env['account.move'].search(domain, order='invoice_date, name')
        return moves.filtered('vat_is_high_value') if self.book_type == 'high_value' else moves

    def action_print(self):
        self.ensure_one()
        form_code = {'purchase': '6.1', 'sales': '6.2', 'high_value': '6.10'}[self.book_type]
        return mushak_report_action(self, form_code)
