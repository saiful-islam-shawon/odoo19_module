# Part of Odoo. See LICENSE file for full copyright and licensing details.

import io
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
                'company_information': 'zencore_accounting_filter.company_information',
                'pdf_export_main_table_header': 'zencore_accounting_filter.pdf_export_main_table_header',
                'pdf_export_main_table_body': 'zencore_accounting_filter.pdf_export_main_table_body',
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

    def export_to_xlsx(self, options, response=None):
        report = self.env['account.report'].browse(options['report_id'])
        if not options.get('is_single_partner'):
            return report.export_to_xlsx(options, response=response)
        return self._export_single_partner_to_xlsx(report, options, response=response)

    def _export_single_partner_to_xlsx(self, report, options, response=None):
        import xlsxwriter

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {
            'in_memory': True,
            'strings_to_formulas': False,
        })
        sheet = workbook.add_worksheet('Partner Ledger')
        sheet.set_paper(9)  # A4
        sheet.set_landscape()

        # Format styles
        company_format = workbook.add_format({
            'font_name': 'Arial', 'font_size': 12, 'bold': True, 'font_color': '#111827'
        })
        report_title_format = workbook.add_format({
            'font_name': 'Arial', 'font_size': 14, 'bold': True, 'font_color': '#1E3A8A'
        })
        meta_label_format = workbook.add_format({
            'font_name': 'Arial', 'font_size': 10, 'bold': True, 'font_color': '#374151'
        })
        meta_val_format = workbook.add_format({
            'font_name': 'Arial', 'font_size': 10, 'font_color': '#4B5563'
        })

        # Table header styles
        th_left_format = workbook.add_format({
            'font_name': 'Arial', 'font_size': 10, 'bold': True, 'bg_color': '#F1F5F9',
            'border': 1, 'align': 'left', 'valign': 'vcenter'
        })
        th_right_format = workbook.add_format({
            'font_name': 'Arial', 'font_size': 10, 'bold': True, 'bg_color': '#F1F5F9',
            'border': 1, 'align': 'right', 'valign': 'vcenter'
        })
        date_bar_format = workbook.add_format({
            'font_name': 'Arial', 'font_size': 11, 'bold': True, 'bg_color': '#E2E8F0',
            'border': 1, 'align': 'center', 'valign': 'vcenter'
        })

        # Data cell styles
        td_left_format = workbook.add_format({
            'font_name': 'Arial', 'font_size': 10, 'border': 1, 'align': 'left', 'valign': 'vcenter'
        })
        td_date_format = workbook.add_format({
            'font_name': 'Arial', 'font_size': 10, 'border': 1, 'align': 'left', 'valign': 'vcenter'
        })
        td_num_format = workbook.add_format({
            'font_name': 'Arial', 'font_size': 10, 'border': 1, 'align': 'right', 'valign': 'vcenter',
            'num_format': '#,##0.00'
        })

        # Total row styles
        total_label_format = workbook.add_format({
            'font_name': 'Arial', 'font_size': 11, 'bold': True, 'border': 1,
            'align': 'center', 'valign': 'vcenter', 'bg_color': '#F8FAFC'
        })
        total_num_format = workbook.add_format({
            'font_name': 'Arial', 'font_size': 11, 'bold': True, 'border': 1,
            'align': 'right', 'valign': 'vcenter', 'num_format': '#,##0.00', 'bg_color': '#F8FAFC'
        })

        # Set Column Widths
        sheet.set_column(0, 0, 26)  # Customer Name
        sheet.set_column(1, 1, 22)  # Number
        sheet.set_column(2, 2, 14)  # Date
        sheet.set_column(3, 3, 16)  # Debit
        sheet.set_column(4, 4, 16)  # Credit
        sheet.set_column(5, 5, 18)  # Balance

        # Write Report Info Block
        company_name = self.env.company.name
        partner_name = options.get('selected_partner_name', '')
        date_range_str = options.get('formatted_date_range', '')
        category_name = options.get('selected_category_name') or 'All Categories'

        curr_row = 0
        sheet.write(curr_row, 0, company_name, company_format)
        curr_row += 1
        sheet.write(curr_row, 0, 'Partner Ledger', report_title_format)
        curr_row += 1
        sheet.write(curr_row, 0, 'Customer Name:', meta_label_format)
        sheet.write(curr_row, 1, partner_name, meta_val_format)
        curr_row += 1
        sheet.write(curr_row, 0, 'Date:', meta_label_format)
        sheet.write(curr_row, 1, date_range_str, meta_val_format)
        curr_row += 1
        sheet.write(curr_row, 0, 'Category:', meta_label_format)
        sheet.write(curr_row, 1, category_name, meta_val_format)
        curr_row += 2  # Blank line separator

        # Date header row spanning all 6 columns
        if date_range_str:
            sheet.merge_range(curr_row, 0, curr_row, 5, date_range_str, date_bar_format)
            sheet.set_row(curr_row, 24)
            curr_row += 1

        # Table Column Headers
        sheet.set_row(curr_row, 22)
        sheet.write(curr_row, 0, 'Customer Name', th_left_format)
        sheet.write(curr_row, 1, 'Number', th_left_format)
        sheet.write(curr_row, 2, 'Date', th_left_format)
        sheet.write(curr_row, 3, 'Debit', th_right_format)
        sheet.write(curr_row, 4, 'Credit', th_right_format)
        sheet.write(curr_row, 5, 'Balance', th_right_format)
        curr_row += 1

        # Fetch lines
        lines = report._get_lines(options)

        for line in lines:
            if 'total' in str(line.get('id', '')):
                # TOTAL summary row: merge cols 0 to 2
                sheet.set_row(curr_row, 22)
                sheet.merge_range(curr_row, 0, curr_row, 2, 'TOTAL', total_label_format)
                deb_val = line['columns'][2].get('no_format', 0.0)
                cred_val = line['columns'][3].get('no_format', 0.0)
                bal_val = line['columns'][4].get('no_format', 0.0)
                sheet.write(curr_row, 3, float(deb_val) if isinstance(deb_val, (int, float)) else 0.0, total_num_format)
                sheet.write(curr_row, 4, float(cred_val) if isinstance(cred_val, (int, float)) else 0.0, total_num_format)
                sheet.write(curr_row, 5, float(bal_val) if isinstance(bal_val, (int, float)) else 0.0, total_num_format)
                curr_row += 1
            else:
                # Regular transaction row
                sheet.set_row(curr_row, 19)
                cust_val = line.get('name', '')
                num_val = line['columns'][0].get('no_format') or line['columns'][0].get('name', '')
                date_val = line['columns'][1].get('no_format') or line['columns'][1].get('name', '')
                deb_val = line['columns'][2].get('no_format', 0.0)
                cred_val = line['columns'][3].get('no_format', 0.0)
                bal_val = line['columns'][4].get('no_format', 0.0)

                sheet.write(curr_row, 0, cust_val, td_left_format)
                sheet.write(curr_row, 1, num_val, td_left_format)
                sheet.write(curr_row, 2, str(date_val) if date_val else '', td_date_format)
                sheet.write(curr_row, 3, float(deb_val) if isinstance(deb_val, (int, float)) else 0.0, td_num_format)
                sheet.write(curr_row, 4, float(cred_val) if isinstance(cred_val, (int, float)) else 0.0, td_num_format)
                sheet.write(curr_row, 5, float(bal_val) if isinstance(bal_val, (int, float)) else 0.0, td_num_format)
                curr_row += 1

        workbook.close()
        output.seek(0)
        generated_file = output.read()
        output.close()

        return {
            'file_name': report.get_default_report_filename(options, 'xlsx'),
            'file_content': generated_file,
            'file_type': 'xlsx',
        }
