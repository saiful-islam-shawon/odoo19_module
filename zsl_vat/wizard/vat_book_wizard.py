from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.addons.zsl_vat.models.mushak_report import mushak_report_action
from odoo.addons.zsl_vat.models.official_mushak_pdf import official_mushak_action


class VatBookWizard(models.TransientModel):
    _name = 'vat.book.wizard'
    _description = 'VAT Book Print Wizard'

    date_mode = fields.Selection(
        [('period', 'Period (Date Range)'), ('single', 'Single Date')],
        string='Print By', required=True, default='period')
    period_id = fields.Many2one(
        'vat.period', required=False,
        default=lambda self: self.env['vat.period'].search([('company_id', '=', self.env.company.id), ('state', '=', 'open')], order='date_start desc', limit=1))
    report_date = fields.Date(string='Date', default=fields.Date.context_today)
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse', domain="[('company_id', '=', company_id)]")
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    book_type = fields.Selection([('purchase', 'Purchase Book (Mushak 6.1)'), ('sales', 'Sales Book (Mushak 6.2)'), ('high_value', 'High-Value Transactions (Mushak 6.10)')], required=True, default='sales')

    def _date_range(self):
        """Dates printed on the book: (date_from, date_to)."""
        self.ensure_one()
        if self.date_mode == 'single':
            if not self.report_date:
                raise UserError(_('Select the date to print.'))
            return self.report_date, self.report_date
        if not self.period_id:
            raise UserError(_('Select a VAT period.'))
        return self.period_id.date_start, self.period_id.date_end

    def _ledger_start(self):
        """Running ledgers (6.1/6.2) must start at the period start so a
        single-day print still carries the correct opening balance."""
        self.ensure_one()
        date_from, __ = self._date_range()
        if self.date_mode == 'period':
            return date_from
        period = self.env['vat.period'].search([
            ('company_id', '=', self.company_id.id),
            ('date_start', '<=', date_from), ('date_end', '>=', date_from),
        ], limit=1)
        return period.date_start if period else date_from.replace(day=1)

    def _line_warehouse(self, line):
        """Warehouse of the order that generated an invoice line."""
        sale_orders = line.sale_line_ids.order_id
        if sale_orders:
            return sale_orders[:1].warehouse_id
        purchase = line.purchase_line_id.order_id
        if purchase:
            return purchase.picking_type_id.warehouse_id
        return self.env['stock.warehouse']

    def _lines(self, move):
        """Product lines of ``move`` that belong to the selected warehouse."""
        lines = move.invoice_line_ids.filtered(lambda item: item.display_type == 'product')
        if not self.warehouse_id:
            return lines
        single_warehouse = self.env['stock.warehouse'].search_count([('company_id', '=', self.company_id.id)]) == 1

        def belongs(line):
            warehouse = self._line_warehouse(line)
            # Manual invoice lines have no order; they can only be assigned
            # when the company has one warehouse.
            return warehouse == self.warehouse_id if warehouse else single_warehouse
        return lines.filtered(belongs)

    def _moves(self, date_from=None, date_to=None):
        self.ensure_one()
        range_from, range_to = self._date_range()
        date_from = date_from or range_from
        date_to = date_to or range_to
        domain = [('company_id', '=', self.company_id.id), ('state', '=', 'posted'), ('invoice_date', '>=', date_from), ('invoice_date', '<=', date_to)]
        move_types = (
            ('in_invoice', 'in_refund') if self.book_type == 'purchase'
            else ('in_invoice', 'in_refund', 'out_invoice', 'out_refund') if self.book_type == 'high_value'
            else ('out_invoice', 'out_refund')
        )
        domain.append(('move_type', 'in', move_types))
        moves = self.env['account.move'].search(domain, order='invoice_date, name')
        if self.warehouse_id:
            moves = moves.filtered(lambda move: self._lines(move))
        return moves.filtered('vat_is_high_value') if self.book_type == 'high_value' else moves

    def action_print(self):
        self.ensure_one()
        qweb_forms = {'purchase': '6.1', 'sales': '6.2'}
        if self.book_type in qweb_forms:
            return mushak_report_action(self, qweb_forms[self.book_type])
        # This renderer fills the prescribed Mushak PDF with live invoice-line
        # values; the legacy QWeb template has only a blank specimen row.
        action = official_mushak_action(self, '6.10')
        # ``close`` makes the web client open the PDF in a new tab and then
        # close this dialog (it runs an act_window_close afterwards).
        action['close'] = True
        return action