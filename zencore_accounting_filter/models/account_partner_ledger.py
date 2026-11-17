# Part of Odoo. See LICENSE file for full copyright and licensing details.

from collections import defaultdict
from odoo import api, fields, models, _
from odoo.tools.float_utils import float_is_zero


class AccountPartnerLedgerReportHandler(models.AbstractModel):
    _inherit = 'account.partner.ledger.report.handler'

    def _custom_options_initializer(self, report, options, previous_options=None):
        super()._custom_options_initializer(report, options, previous_options=previous_options)
        previous_options = previous_options or {}

        # Preserve or initialize product category filter
        options['product_category_id'] = previous_options.get('product_category_id', False)

        # Load available product categories for both top bar and in-report dropdown
        categories = self.env['product.category'].search_read(
            [], ['id', 'display_name'], order='name asc'
        )
        options['available_product_categories'] = categories

        if options['product_category_id']:
            cat = self.env['product.category'].browse(int(options['product_category_id']))
            options['selected_category_name'] = cat.display_name if cat.exists() else ''
        else:
            options['selected_category_name'] = ''

        # Date string formatting for single partner custom header (both web and PDF)
        date_opt = options.get('date', {})
        if date_opt.get('filter') == 'custom' and date_opt.get('date_from') and date_opt.get('date_to'):
            from_d = fields.Date.from_string(date_opt['date_from']).strftime('%m/%d/%Y')
            to_d = fields.Date.from_string(date_opt['date_to']).strftime('%m/%d/%Y')
            options['formatted_date_range'] = f"From {from_d} to {to_d}"
        else:
            raw_date = date_opt.get('string', '')
            options['formatted_date_range'] = raw_date.replace('\n', ' ') if raw_date else ''

        partner_ids = options.get('partner_ids') or []
        if len(partner_ids) == 1:
            partner = self.env['res.partner'].browse(partner_ids[0])
            options['is_single_partner'] = True
            options['selected_partner_id'] = partner.id
            options['selected_partner_name'] = partner.display_name

            # Replace standard columns with custom 5 columns for single partner
            # (First column "Customer Name" is represented by line['name'])
            col_group_key = list(options['column_groups'].keys())[0] if options.get('column_groups') else 'default'
            options['columns'] = [
                {
                    'name': _('Number'),
                    'expression_label': 'number',
                    'figure_type': 'string',
                    'column_group_key': col_group_key,
                },
                {
                    'name': _('Date'),
                    'expression_label': 'date',
                    'figure_type': 'date',
                    'column_group_key': col_group_key,
                },
                {
                    'name': _('Debit'),
                    'expression_label': 'debit',
                    'figure_type': 'monetary',
                    'column_group_key': col_group_key,
                },
                {
                    'name': _('Credit'),
                    'expression_label': 'credit',
                    'figure_type': 'monetary',
                    'column_group_key': col_group_key,
                },
                {
                    'name': _('Balance'),
                    'expression_label': 'balance',
                    'figure_type': 'monetary',
                    'column_group_key': col_group_key,
                },
            ]

            # In-report header template and styling
            options['custom_display_config']['css_custom_class'] += ' zencore_single_partner_ledger'
            options['custom_display_config']['templates']['AccountReportHeader'] = 'zencore_accounting_filter.PartnerLedgerHeader'

            # PDF export customization for single partner view
            options['custom_display_config']['pdf_export'] = {
                'pdf_export_main_table_header': 'zencore_accounting_filter.pdf_export_main_table_header',
                'pdf_export_filters': 'zencore_accounting_filter.pdf_export_filters',
            }
        else:
            options['is_single_partner'] = False

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        if options.get('is_single_partner'):
            return self._build_single_partner_category_lines(report, options)
        return super()._dynamic_lines_generator(
            report, options, all_column_groups_expression_totals, warnings=warnings
        )

    def _build_single_partner_category_lines(self, report, options):
        partner_id = options.get('selected_partner_id')
        if not partner_id:
            return []

        partner = self.env['res.partner'].browse(partner_id)
        if not partner.exists():
            return []

        partner_name = partner.display_name
        company_ids = report.get_report_company_ids(options)

        date_from = options.get('date', {}).get('date_from')
        date_to = options.get('date', {}).get('date_to')

        category_id = options.get('product_category_id')
        partner_domain_ids = tuple(partner.ids + partner.child_ids.ids)

        all_rows = []

        if not category_id:
            # Case 1: No category selected -> show all partner journal items (default ledger rows)
            aml_domain = [
                ('parent_state', '=', 'posted'),
                ('company_id', 'in', company_ids),
                ('partner_id', 'in', partner_domain_ids),
                ('account_type', 'in', ('asset_receivable', 'liability_payable')),
            ]
            if date_from:
                aml_domain.append(('date', '>=', date_from))
            if date_to:
                aml_domain.append(('date', '<=', date_to))

            amls = self.env['account.move.line'].search(aml_domain, order='date asc, id asc')
            for a in amls:
                mdate = a.move_id.invoice_date or a.date
                all_rows.append({
                    'id': a.id,
                    'number': a.move_id.name or a.name or '',
                    'date': fields.Date.to_string(mdate) if mdate else '',
                    'debit': a.debit,
                    'credit': a.credit,
                })
        else:
            # Case 2: Specific category selected -> filter category invoice lines & matched reconciled payments
            category_id = int(category_id)
            all_category_ids = set(
                self.env['product.category'].search([('id', 'child_of', category_id)]).ids
            )

            invoice_domain = [
                ('state', '=', 'posted'),
                ('company_id', 'in', company_ids),
                ('partner_id', 'in', partner_domain_ids),
                ('move_type', 'in', ('out_invoice', 'out_refund')),
            ]
            if date_from:
                invoice_domain.append(('invoice_date', '>=', date_from))
            if date_to:
                invoice_domain.append(('invoice_date', '<=', date_to))

            invoices = self.env['account.move'].search(invoice_domain, order='invoice_date asc, id asc')

            matched_category_invoices = set()
            for inv in invoices:
                cat_lines = inv.invoice_line_ids.filtered(
                    lambda l: l.display_type == 'product' and l.product_id.categ_id.id in all_category_ids
                )
                if not cat_lines:
                    continue
                cat_amount = sum(cat_lines.mapped('price_total'))
                if float_is_zero(cat_amount, precision_digits=2):
                    continue
                matched_category_invoices.add(inv.id)

                inv_date = inv.invoice_date or inv.date
                date_str = fields.Date.to_string(inv_date) if inv_date else ''

                if inv.move_type == 'out_invoice':
                    debit = cat_amount
                    credit = 0.0
                else:  # out_refund
                    debit = 0.0
                    credit = cat_amount

                all_rows.append({
                    'id': inv.id,
                    'number': inv.name or '',
                    'date': date_str,
                    'debit': debit,
                    'credit': credit,
                })

            # Reconciled payments against those category invoices
            if matched_category_invoices:
                rec_lines = self.env['account.move.line'].search([
                    ('move_id', 'in', list(matched_category_invoices)),
                    ('account_type', '=', 'asset_receivable'),
                ])
                partials = self.env['account.partial.reconcile'].search([
                    ('debit_move_id', 'in', rec_lines.ids),
                ])

                payments_by_move = defaultdict(lambda: {'amount': 0.0, 'date': None, 'name': ''})
                for part in partials:
                    pay_aml = part.credit_move_id
                    pay_move = pay_aml.move_id

                    pay_date = pay_move.date
                    if date_from and str(pay_date) < str(date_from):
                        continue
                    if date_to and str(pay_date) > str(date_to):
                        continue

                    inv_move = part.debit_move_id.move_id
                    prop = 1.0
                    if inv_move.amount_total > 0:
                        inv_cat_lines = inv_move.invoice_line_ids.filtered(
                            lambda l: l.display_type == 'product' and l.product_id.categ_id.id in all_category_ids
                        )
                        inv_cat_amount = sum(inv_cat_lines.mapped('price_total'))
                        prop = min(1.0, inv_cat_amount / inv_move.amount_total)

                    payments_by_move[pay_move.id]['amount'] += part.amount * prop
                    payments_by_move[pay_move.id]['date'] = pay_date
                    payments_by_move[pay_move.id]['name'] = pay_move.name or pay_aml.name or ''

                for move_id, pdata in payments_by_move.items():
                    pdate_str = fields.Date.to_string(pdata['date']) if pdata['date'] else ''
                    all_rows.append({
                        'id': move_id,
                        'number': pdata['name'],
                        'date': pdate_str,
                        'debit': 0.0,
                        'credit': pdata['amount'],
                    })

        # If no records exist for this partner/category/date, return a placeholder row
        # so the table structure, column headers, and in-report header dropdown STAY VISIBLE!
        if not all_rows:
            placeholder_line = {
                'id': report._get_generic_line_id('account.move', None, markup='no_data'),
                'name': partner_name,
                'columns': [
                    report._build_column_dict(_('No records found for this category/date'), options['columns'][0], options=options),
                    report._build_column_dict('', options['columns'][1], options=options),
                    report._build_column_dict(0.0, options['columns'][2], options=options),
                    report._build_column_dict(0.0, options['columns'][3], options=options),
                    report._build_column_dict(0.0, options['columns'][4], options=options),
                ],
                'level': 1,
            }
            total_line = {
                'id': report._get_generic_line_id(None, None, markup='total'),
                'name': _('TOTAL'),
                'level': 1,
                'class': 'total fw-bold',
                'columns': [
                    report._build_column_dict('', options['columns'][0], options=options),
                    report._build_column_dict('', options['columns'][1], options=options),
                    report._build_column_dict(0.0, options['columns'][2], options=options),
                    report._build_column_dict(0.0, options['columns'][3], options=options),
                    report._build_column_dict(0.0, options['columns'][4], options=options),
                ],
            }
            return [(0, placeholder_line), (0, total_line)]

        # Sort chronologically by date, then id
        all_rows.sort(key=lambda r: (r['date'] or '', r['id']))

        # Calculate Running Balance & Totals
        running_balance = 0.0
        total_debit = 0.0
        total_credit = 0.0

        for r in all_rows:
            total_debit += r['debit']
            total_credit += r['credit']
            running_balance += (r['debit'] - r['credit'])
            r['balance'] = running_balance

        # Build Formatted Report Lines
        lines = []
        for r in all_rows:
            line = {
                'id': report._get_generic_line_id('account.move', r['id']),
                'name': partner_name,
                'columns': [
                    report._build_column_dict(r['number'], options['columns'][0], options=options),
                    report._build_column_dict(r['date'], options['columns'][1], options=options),
                    report._build_column_dict(r['debit'], options['columns'][2], options=options),
                    report._build_column_dict(r['credit'], options['columns'][3], options=options),
                    report._build_column_dict(r['balance'], options['columns'][4], options=options),
                ],
                'level': 1,
            }
            lines.append((0, line))

        # Total summary row
        total_line = {
            'id': report._get_generic_line_id(None, None, markup='total'),
            'name': _('TOTAL'),
            'level': 1,
            'class': 'total fw-bold',
            'columns': [
                report._build_column_dict('', options['columns'][0], options=options),
                report._build_column_dict('', options['columns'][1], options=options),
                report._build_column_dict(total_debit, options['columns'][2], options=options),
                report._build_column_dict(total_credit, options['columns'][3], options=options),
                report._build_column_dict(running_balance, options['columns'][4], options=options),
            ],
        }
        lines.append((0, total_line))

        return lines
