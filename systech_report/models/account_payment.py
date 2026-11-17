from odoo import models, fields, api


class BookCategory(models.Model):
    _name = 'book.category'
    _description = 'Book Category'

    name = fields.Char(string='Category Name', required=True)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    received_by_cheque_no = fields.Char(
        string='Cheque/TT/Bank Draft No.',
        compute='_compute_received_by_cheque_no',
        store=False,
    )

    drawn_on_bank = fields.Char(string='Drawn on Bank')
    bank_branch = fields.Char(string='Branch')

    amount_in_words = fields.Char(
        string='Amount in Words',
        compute='_compute_amount_in_words',
        store=False,
    )

    due_cash_pay = fields.Monetary(
        string='DUE (Cash Pay)',
        currency_field='currency_id',
        compute='_compute_due_cash_pay',
        store=False,
    )

    collection_deposit = fields.Monetary(
        string='Collection & Deposit',
        currency_field='currency_id',
        compute='_compute_collection_deposit',
        store=False,
    )

    authorized_by = fields.Char(
        string='Received By / Authorized Signatory',
        default=lambda self: self.env.user.name,
    )

    book_category_id = fields.Many2one(
        comodel_name='book.category',
        string='Category',
    )

    payment_notes = fields.Text(string='Notes')


    @api.depends('journal_id')
    def _compute_received_by_cheque_no(self):
        for payment in self:
            payment.received_by_cheque_no = payment.journal_id.name if payment.journal_id else ''

    @api.depends('partner_id', 'currency_id', 'company_id', 'date', 'amount')
    def _compute_due_cash_pay(self):
     
        for payment in self:
            if not payment.partner_id:
                payment.due_cash_pay = 0.0
                continue

            partner = payment.partner_id.commercial_partner_id

            domain = [
                ('partner_id', 'child_of', partner.id),
                ('account_id.account_type', '=', 'asset_receivable'),
                ('parent_state', '=', 'posted'),
                ('company_id', '=', payment.company_id.id),
            ]

            lines = self.env['account.move.line'].search(domain)

            # Balance = sum(debit) - sum(credit)
            total_debit  = sum(lines.mapped('debit'))
            total_credit = sum(lines.mapped('credit'))
            balance = total_debit - total_credit

            payment.due_cash_pay = balance if balance > 0 else 0.0

    @api.depends('amount')
    def _compute_collection_deposit(self):
        for payment in self:
            payment.collection_deposit = payment.amount

    @api.depends('amount', 'currency_id')
    def _compute_amount_in_words(self):
        for payment in self:
            payment.amount_in_words = payment.currency_id.amount_to_text(payment.amount)

    def action_print_money_receipt(self):
        return self.env.ref('systech_report.action_report_money_receipt').report_action(self)