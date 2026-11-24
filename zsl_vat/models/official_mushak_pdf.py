"""Render statutory Mushak PDFs without rebuilding the government layout.

The source PDFs are published forms. They are deliberately kept as the base
page and only taxpayer/transaction values are overlaid. This prevents the
usual QWeb/CSS drift (margins, table borders, Bengali headings and page size)
that makes a generated report differ from the prescribed form.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from odoo import fields, models
from odoo.tools import file_path


FORM_FILES = {
    '2.1': 'Mushak_2.1.pdf',
    '2.3': 'Mushak_2.3.pdf',
    '4.3': 'Mushak_4.3.pdf',
    '6.1': 'Mushak_6.1.pdf',
    '6.2': 'Mushak_6.2.pdf',
    '6.2.1': 'Mushak_6.2.1.pdf',
    '6.3': 'Mushak_6.3.pdf',
    '6.4': 'Mushak_6.4.pdf',
    '6.5': 'Mushak_6.5.pdf',
    '6.6': 'Mushak_6.6.pdf',
    '6.7': 'Mushak_6.7.pdf',
    '6.8': 'Mushak_6.8.pdf',
    '6.10': 'Mushak_6.10.pdf',
    '9.1': 'Mushak_9.1.pdf',
    '9.2': 'Mushak_9.2.pdf',
    'tr6': 'TR-6.pdf',
}


def official_mushak_action(record, form_code):
    """Open an official-form PDF for one record in a new browser tab."""
    record.ensure_one()
    return {
        'type': 'ir.actions.act_url',
        'url': '/zsl_vat/official-mushak/%s/%s/%s' % (
            form_code, record._name, record.id
        ),
        'target': 'new',
    }


class OfficialMushakPdf(models.AbstractModel):
    _name = 'zsl_vat.official.mushak.pdf'
    _description = 'Official NBR Mushak PDF Renderer'

    def _form_path(self, form_code):
        filename = FORM_FILES.get(form_code)
        if not filename:
            return False
        try:
            return file_path('zsl_vat/static/src/mushak_forms/%s' % filename)
        except FileNotFoundError:
            return False

    @staticmethod
    def _display(value):
        if value in (False, None):
            return ''
        if hasattr(value, 'display_name'):
            return value.display_name
        if hasattr(value, 'strftime'):
            return value.strftime('%d-%m-%Y')
        if isinstance(value, float):
            return format(value, ',.2f')
        return str(value)

    def _values_for(self, form_code, record):
        """Values for supported overlay fields on statutory forms."""
        company = getattr(record, 'company_id', False) or record.env.company
        company_name = company.vat_legal_name or company.name
        common = {
            'company': company_name,
            'bin': company.vat_bin or '',
            'date': fields.Date.context_today(record),
        }
        if form_code == '2.3':
            return {
                **common,
                'reference': record.certificate_reference,
                'legal_name': record.taxpayer_name,
                'bin': record.bin,
            }
        if form_code in ('6.3', '6.7', '6.8'):
            return {
                **common,
                'reference': record.vat_mushak_number or record.name,
                'date': record.invoice_date or record.date,
                'partner': record.partner_id.name,
                'amount': record.amount_total,
            }
        if form_code in ('6.4', '6.5'):
            return {
                **common,
                'reference': record.vat_challan_number or record.name,
                'date': record.vat_challan_date or record.date_done,
                'partner': record.partner_id.name,
                'amount': record.vat_transfer_value,
            }
        if form_code == '6.6':
            return {
                **common,
                'reference': record.name,
                'date': record.certificate_date,
                'partner': record.partner_id.name,
                'amount': record.amount,
            }
        if form_code in ('9.1', '9.2'):
            return {
                **common,
                'reference': record.name,
                'date': record.period_id.date_end,
                'amount': record.net_payable,
            }
        if form_code == 'tr6':
            return {
                **common,
                'reference': record.challan_number,
                'date': record.payment_date,
                'amount': record.amount,
                'partner': record.bank or '',
            }
        if form_code == '2.1':
            return {
                **common,
                'reference': record.name,
                'legal_name': record.legal_name or '',
                'tin': record.tin or '',
                'trade_name': getattr(record, 'trade_name', '') or '',
                'registered_address': getattr(record, 'registered_address', '') or '',
                'contact_address': getattr(record, 'contact_address', '') or '',
                'business_activity': getattr(record, 'business_activity', '') or '',
                'projected_turnover': getattr(record, 'projected_turnover', '') or '',
                'workforce_count': getattr(record, 'workforce_count', '') or '',
            }
        if form_code == '4.3':
            return {
                **common,
                'reference': record.name,
                'product': getattr(record.product_tmpl_id, 'display_name', '') or '',
                'effective_date': record.effective_date,
                'output_qty': record.output_qty,
                'wastage_percent': record.wastage_percent,
                'value_addition': record.value_addition,
                'material_cost': record.material_cost,
                'declared_price': record.declared_price,
                'state': record.state,
            }
        if form_code in ('6.1', '6.2', '6.10'):
            return {
                **common,
                'date_start': getattr(record, 'date_start', '') or '',
                'date_end': getattr(record, 'date_end', '') or '',
                'company': common['company'],
            }
        if form_code == '6.2.1':
            return {
                **common,
                'unit': getattr(record, 'unit_id', False) and record.unit_id.name or '',
                'period': getattr(record, 'period_id', False) and record.period_id.name or '',
                'opening_total': getattr(record, 'opening_total', '') or '',
                'closing_total': getattr(record, 'closing_total', '') or '',
            }
        return common

    def _lines_for(self, form_code, record, page_width, page_height):
        values = self._values_for(form_code, record)
        if form_code in ('6.3', '6.7', '6.8'):
            return [
                (70, page_height - 119, values['company']),
                (70, page_height - 139, values['bin']),
                (360, page_height - 119, values['reference']),
                (360, page_height - 139, values['date']),
                (70, page_height - 182, values['partner']),
                (430, 125, values['amount']),
            ]
        if form_code in ('6.4', '6.5'):
            return [
                (95, page_height - 130, values['company']),
                (95, page_height - 150, values['bin']),
                (400, page_height - 180, values['reference']),
                (400, page_height - 200, values['date']),
                (95, page_height - 180, values['partner']),
            ]
        if form_code == '6.6':
            return [
                (180, page_height - 126, values['reference']),
                (430, page_height - 126, values['date']),
                (90, page_height - 225, values['partner']),
                (405, page_height - 225, values['amount']),
            ]
        if form_code in ('9.1', '9.2'):
            return [
                (140, page_height - 120, values['bin']),
                (280, page_height - 120, values['company']),
                (425, 82, values['amount']),
            ]
        if form_code == 'tr6':
            return [
                (82, page_height - 76, values['reference']),
                (276, page_height - 76, values['date']),
                (304, page_height - 160, values['company']),
                (410, page_height - 160, values['amount']),
            ]
        if form_code == '2.3':
            return [
                (120, page_height - 220, values['legal_name']),
                (120, page_height - 240, values['bin']),
                (380, page_height - 220, values['reference']),
            ]
        if form_code == '2.1':
            return [
                (120, page_height - 220, values['legal_name']),
                (120, page_height - 240, values['bin']),
                (380, page_height - 220, values['reference']),
                (380, page_height - 240, values['trade_name']),
                (120, page_height - 280, values['registered_address']),
                (120, page_height - 300, values['contact_address']),
                (120, page_height - 340, values['business_activity']),
            ]
        if form_code == '4.3':
            return [
                (60, page_height - 80, values['company']),
                (60, page_height - 100, values['bin']),
                (200, page_height - 80, values['product']),
                (200, page_height - 100, values['reference']),
                (60, page_height - 140, 'Output Qty: %s' % values['output_qty']),
                (200, page_height - 140, 'Wastage %%: %s' % values['wastage_percent']),
                (60, page_height - 160, 'Value Addition: %s' % values['value_addition']),
                (200, page_height - 160, 'Material Cost: %s' % values['material_cost']),
                (60, page_height - 180, 'Declared Price: %s' % values['declared_price']),
            ]
        if form_code in ('6.1', '6.2', '6.10'):
            return [
                (60, page_height - 80, values['company']),
                (60, page_height - 100, values['bin']),
            ]
        if form_code == '6.2.1':
            return [
                (60, page_height - 80, values['company']),
                (60, page_height - 100, values['bin']),
                (200, page_height - 80, values['unit']),
                (200, page_height - 100, values['period']),
            ]
        # No page coordinates are defined for remaining forms yet.
        # Leave the original official PDF unchanged rather than generating an
        # empty overlay (which has no first page).
        return []

    def _overlay_page(self, source_page, painter):
        """Merge an overlay into an untouched prescribed PDF page."""
        from PyPDF2 import PdfReader
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfgen.canvas import Canvas

        font_name = 'ZslNotoBengali'
        try:
            pdfmetrics.getFont(font_name)
        except KeyError:
            pdfmetrics.registerFont(TTFont(
                font_name, '/usr/share/fonts/truetype/noto/NotoSansBengali-Regular.ttf',
            ))
        width = float(source_page.mediabox.width)
        height = float(source_page.mediabox.height)
        buffer = BytesIO()
        canvas = Canvas(buffer, pagesize=(width, height))
        canvas.setFont(font_name, 6)

        def write(value, x, y, width_limit, size=5.5, align='left'):
            value = self._display(value).replace('\n', ' ').strip()
            canvas.setFont(font_name, size)
            while value and pdfmetrics.stringWidth(value, font_name, size) > width_limit:
                value = value[:-1]
            if align == 'right':
                canvas.drawRightString(x, y, value)
            elif align == 'center':
                canvas.drawCentredString(x, y, value)
            else:
                canvas.drawString(x, y, value)

        painter(write, width, height)
        canvas.showPage()
        canvas.save()
        buffer.seek(0)
        source_page.merge_page(PdfReader(buffer).pages[0])
        return source_page

    def _render_book(self, form_path, wizard, form_code):
        """Fill Mushak 6.1/6.2 line by line on the supplied legal sheet."""
        from PyPDF2 import PdfReader, PdfWriter

        moves = wizard._moves()
        rows = []
        for move in moves:
            for line in move.invoice_line_ids.filtered(lambda l: not l.display_type):
                product = line.product_id
                template = product.product_tmpl_id
                rows.append({
                    'date': move.invoice_date or move.date,
                    'document': move.vat_mushak_number or move.vat_supplier_document_number or move.name,
                    'document_date': move.vat_supplier_document_date or move.invoice_date or move.date,
                    'partner': move.partner_id.name,
                    'address': move.partner_id.contact_address or '',
                    'bin': move.partner_id.vat_bin or '',
                    'description': line.name or product.display_name,
                    'quantity': line.quantity,
                    'value': line.price_subtotal,
                    'sd': line._vat_tax_components()[1],
                    'vat': line._vat_tax_components()[0],
                    'uom': template.vat_uom_id.name or line.product_uom_id.name,
                })
        # A blank official page is still a useful legally-identical printout
        # for a period with no transactions.
        pages = rows or [{}]
        template = PdfReader(form_path)
        writer = PdfWriter()
        for number, row in enumerate(pages, 1):
            page = PdfReader(form_path).pages[0]

            def paint(write, width, height):
                # The source form contains one body row.  Values below are
                # positioned inside that row; headers/borders remain original.
                y = 225 if form_code == '6.1' else 229
                if not row:
                    return
                if form_code == '6.1':
                    cells = [
                        (number, 10, 15), (row['date'], 31, 24), (row['quantity'], 60, 20),
                        ('', 82, 22), (row['document'], 106, 28), (row['document_date'], 137, 27),
                        (row['partner'], 168, 27), (row['address'], 201, 35), (row['bin'], 241, 37),
                        (row['description'], 283, 35), (row['quantity'], 321, 27), (row['value'], 351, 28),
                        (row['sd'], 382, 25), (row['vat'], 411, 27), (row['quantity'], 442, 26),
                        (row['value'], 473, 29),
                    ]
                else:
                    cells = [
                        (number, 10, 15), (row['date'], 32, 24), (row['quantity'], 59, 21),
                        ('', 83, 22), (row['quantity'], 108, 21), ('', 132, 22),
                        (row['quantity'], 155, 22), ('', 179, 22), (row['partner'], 204, 27),
                        (row['address'], 234, 33), (row['bin'], 270, 35), (row['document'], 309, 27),
                        (row['document_date'], 340, 26), (row['description'], 370, 33),
                        (row['quantity'], 405, 25), (row['value'], 433, 29), (row['sd'], 465, 25),
                        (row['vat'], 493, 25), (row['quantity'], 523, 25), (row['value'], 552, 27),
                    ]
                for value, x, cell_width in cells:
                    write(value, x + cell_width / 2, y, cell_width - 2, 4.0, 'center')

            writer.add_page(self._overlay_page(page, paint))
        output = BytesIO()
        writer.write(output)
        return output.getvalue()

    def _render_mushak_610(self, form_path, wizard):
        """Fill the official high-value purchase/sales form, no replacement UI."""
        from itertools import zip_longest
        from PyPDF2 import PdfReader, PdfWriter

        company = wizard.company_id or wizard.env.company
        all_moves = wizard._moves()
        purchases = all_moves.filtered(lambda m: m.move_type in ('in_invoice', 'in_refund'))
        sales = all_moves.filtered(lambda m: m.move_type in ('out_invoice', 'out_refund'))
        writer = PdfWriter()
        pairs = list(zip_longest(purchases, sales, fillvalue=False)) or [(False, False)]

        def fields_for(move, index):
            if not move:
                return []
            return [index, move.vat_mushak_number or move.vat_supplier_document_number or move.name,
                    move.invoice_date or move.date, move.amount_total, move.partner_id.name,
                    move.partner_id.contact_address or '', move.partner_id.vat_bin or '']

        for index, (purchase, sale) in enumerate(pairs, 1):
            page = PdfReader(form_path).pages[0]

            def paint(write, width, height, purchase=purchase, sale=sale, index=index):
                write(company.vat_legal_name or company.name, 219, 655, 170, 6.2)
                write(company.vat_bin or '', 435, 655, 95, 6.2)
                top_cells = [(122, 42), (164, 74), (238, 65), (303, 47), (350, 66), (416, 83), (499, 87)]
                bottom_cells = top_cells
                for value, (x, cell_width) in zip(fields_for(purchase, index), top_cells):
                    write(value, x + cell_width / 2, 518, cell_width - 3, 4.5, 'center')
                for value, (x, cell_width) in zip(fields_for(sale, index), bottom_cells):
                    write(value, x + cell_width / 2, 390, cell_width - 3, 4.5, 'center')
                write(getattr(company, 'vat_authorised_person_name', '') or '', 165, 285, 210, 6)
                write(fields.Date.context_today(wizard), 165, 231, 90, 6)

            writer.add_page(self._overlay_page(page, paint))
        output = BytesIO()
        writer.write(output)
        return output.getvalue()


    def _render_mushak_63(self, form_path, record):
        """Fill the supplied one-page Mushak 6.3 without changing its layout.

        The statutory sheet provides three detail rows. Additional pages repeat
        the same prescribed blank form, three invoice lines per page.
        """
        from math import ceil
        from PyPDF2 import PdfReader, PdfWriter
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfgen.canvas import Canvas

        def get(obj, name, default=False):
            return getattr(obj, name, default) if obj else default

        def plain(value):
            return self._display(value).replace('\n', ' ').strip()

        def amount(value):
            return '%0.2f' % (float(value or 0))

        def register_font():
            font = 'ZSL_Mushak_63_Font'
            try:
                pdfmetrics.getFont(font)
            except KeyError:
                path = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
                if not Path(path).is_file():
                    path = '/usr/share/fonts/truetype/noto/NotoSansBengali-Regular.ttf'
                pdfmetrics.registerFont(TTFont(font, path))
            return font

        font = register_font()
        company = record.company_id
        partner = record.partner_id
        invoice_date = record.invoice_date or record.date
        currency = record.currency_id
        # A test or imported database may not have a currency whose ISO code is
        # literally ``BDT``.  The invoice/company currency is still the only
        # valid source for printed monetary values, so use it as the safe
        # fallback instead of making statutory printing unavailable.
        bdt = record.env['res.currency'].search([('name', '=', 'BDT')], limit=1) or currency or company.currency_id
        def to_bdt(value):
            if currency == bdt:
                return float(value or 0)
            return currency._convert(float(value or 0), bdt, company, invoice_date)

        lines = record.invoice_line_ids.filtered(lambda l: l.display_type == 'product')
        if not lines:
            lines = record.invoice_line_ids.filtered(lambda l: not l.display_type)
        details = []
        for line in lines:
            vat, sd = line._vat_tax_components()
            net = to_bdt(line.price_subtotal)
            discount_value = to_bdt(line.quantity * line.price_unit * (line.discount or 0) / 100)
            sd = to_bdt(sd)
            vat = to_bdt(vat)
            product = line.product_id
            template = get(product, 'product_tmpl_id')
            hs = get(template, 'vat_hs_code_id') or get(template, 'hs_code_id') or get(product, 'hs_code_id')
            hs_text = plain(get(hs, 'code')) or plain(get(product, 'default_code'))
            description = plain(get(line, 'name')) or plain(get(product, 'display_name'))
            details.append({
                'description': description, 'hs': hs_text,
                'unit': plain(get(line.product_uom_id, 'name')),
                'quantity': plain(line.quantity),
                'price': to_bdt(line.price_unit),
                'net': net,
                'discount': discount_value,
                'sd': sd, 'vat': vat,
                'total': net + sd + vat,
            })

        template = PdfReader(form_path)
        page_count = max(1, ceil(len(details) / 3))
        writer = PdfWriter()
        total_net = sum(row['net'] for row in details)
        total_sd = sum(row['sd'] for row in details)
        total_vat = sum(row['vat'] for row in details)
        total_all = sum(row['total'] for row in details)

        def draw_fit(canvas, text, x, y_top, max_width, size=7.1, align='left'):
            text = plain(text)
            canvas.setFont(font, size)
            while text and pdfmetrics.stringWidth(text, font, size) > max_width:
                text = text[:-1]
            if align == 'right':
                canvas.drawRightString(x, 841.68 - y_top, text)
            elif align == 'center':
                canvas.drawCentredString(x, 841.68 - y_top, text)
            else:
                canvas.drawString(x, 841.68 - y_top, text)

        # Coordinates measured from the exact 595.44 x 841.68 PDF provided.
        for page_no in range(page_count):
            page = PdfReader(form_path).pages[0]
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)
            overlay_file = BytesIO()
            c = Canvas(overlay_file, pagesize=(width, height))
            def write(text, x, top, max_width, size=7, align='left'):
                # pdf page is A4; use page-local height
                draw_fit(c, text, x, top + (841.68-height), max_width, size, align)

            write(get(company, 'vat_legal_name') or company.name, 346, 221, 120, 7.0)
            write(get(company, 'vat_bin') or '', 346, 237, 120)
            write(plain(get(company, 'street')) + ' ' + plain(get(company, 'city')), 346, 253, 120, 6.7)
            write(partner.name or '', 186, 273, 150, 6.8)
            write(get(partner, 'vat_bin') or '', 218, 288, 115)
            write(plain(get(partner, 'street')) + ' ' + plain(get(partner, 'city')), 220, 303, 112, 6.5)
            write(get(record, 'vat_mushak_number') or record.name, 430, 273, 130, 6.9)
            write(invoice_date, 430, 288, 130)
            issued = get(record, 'create_date')
            if issued:
                write(issued.strftime('%H:%M'), 430, 303, 130)

            # Column centres on the statutory sheet (from the PDF, in pt).
            xs = [131, 161, 201, 239, 274, 311, 347, 385, 424, 459]
            for row_no, row in enumerate(details[page_no * 3:(page_no + 1) * 3]):
                y = 422 + row_no * 15.55
                values = [str(page_no * 3 + row_no + 1), row['description'],
                          row['unit'], row['quantity'], amount(row['price']),
                          amount(row['net']), amount(row['discount']),
                          amount(row['sd']), amount(row['vat']), amount(row['total'])]
                widths = [16, 32, 42, 28, 33, 32, 33, 35, 34, 31]
                for j, value in enumerate(values):
                    if j == 1:
                        write(value, xs[j], y - 2.5, widths[j], 4.9, 'center')
                        if row['hs']:
                            write(row['hs'], xs[j], y + 4, widths[j], 4.9, 'center')
                    else:
                        write(value, xs[j], y, widths[j], 5.7, 'center')

            if page_no == page_count - 1:
                write(amount(total_net), 312, 470, 45, 6, 'right')
                write(amount(total_sd), 385, 470, 35, 6, 'center')
                write(amount(total_vat), 424, 470, 35, 6, 'center')
                write(amount(total_all), 459, 470, 31, 6, 'center')
            write(get(company, 'vat_authorised_person_name') or '', 260, 496, 180, 6.7)
            if page_count > 1:
                write('Page %d/%d' % (page_no + 1, page_count), 440, 707, 45, 6)
            c.showPage()
            c.save()
            overlay_file.seek(0)
            overlay_page = PdfReader(overlay_file).pages[0]
            page.merge_page(overlay_page)
            writer.add_page(page)

        result = BytesIO()
        writer.write(result)
        return result.getvalue()

    def render_pdf(self, form_code, record):
        """Return the original NBR PDF with overlay data where mapped."""
        form_path = self._form_path(form_code)
        if not form_path or not Path(form_path).is_file():
            return False

        if form_code == '6.3':
            return self._render_mushak_63(form_path, record)
        if form_code in ('6.1', '6.2'):
            return self._render_book(form_path, record, form_code)
        if form_code == '6.10':
            return self._render_mushak_610(form_path, record)

        from PyPDF2 import PdfReader, PdfWriter
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfgen.canvas import Canvas

        reader = PdfReader(form_path)
        writer = PdfWriter()

        for index, source_page in enumerate(reader.pages):
            if index:
                writer.add_page(source_page)
                continue

            width = float(source_page.mediabox.width)
            height = float(source_page.mediabox.height)
            lines = self._lines_for(form_code, record, width, height)

            # Most importantly: if no fields are mapped (as with 2.1),
            # there is nothing to merge. Return the original page as is.
            if not lines:
                writer.add_page(source_page)
                continue

            font_name = 'ZslNotoBengali'
            try:
                pdfmetrics.getFont(font_name)
            except KeyError:
                pdfmetrics.registerFont(TTFont(
                    font_name,
                    '/usr/share/fonts/truetype/noto/NotoSansBengali-Regular.ttf',
                ))

            overlay_buffer = BytesIO()
            overlay = Canvas(overlay_buffer, pagesize=(width, height))
            overlay.setFont(font_name, 7.2)
            for x, y, value in lines:
                overlay.drawString(x, y, self._display(value))
            overlay.showPage()  # Ensure ReportLab actually writes a PDF page.
            overlay.save()
            overlay_buffer.seek(0)

            overlay_reader = PdfReader(overlay_buffer)
            if len(overlay_reader.pages) > 0:
                source_page.merge_page(overlay_reader.pages[0])
            writer.add_page(source_page)

        output = BytesIO()
        writer.write(output)
        return output.getvalue()
