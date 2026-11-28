"""Render statutory Mushak PDFs without rebuilding the government layout.

The source PDFs are published forms. They are deliberately kept as the base
page and only taxpayer/transaction values are overlaid. This prevents the
usual QWeb/CSS drift (margins, table borders, Bengali headings and page size)
that makes a generated report differ from the prescribed form.
"""

from __future__ import annotations

from datetime import timedelta
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

        bengali_font_name = 'ZslNotoBengali'
        latin_font_name = 'ZslNotoSans'
        try:
            pdfmetrics.getFont(bengali_font_name)
        except KeyError:
            pdfmetrics.registerFont(TTFont(
                bengali_font_name, '/usr/share/fonts/truetype/noto/NotoSansBengali-Regular.ttf',
            ))
        try:
            pdfmetrics.getFont(latin_font_name)
        except KeyError:
            pdfmetrics.registerFont(TTFont(
                latin_font_name, '/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf',
            ))
        width = float(source_page.mediabox.width)
        height = float(source_page.mediabox.height)
        buffer = BytesIO()
        canvas = Canvas(buffer, pagesize=(width, height))
        canvas.setFont(latin_font_name, 6)

        def write(value, x, y, width_limit, size=5.5, align='left', max_lines=1):
            value = self._display(value).replace('\n', ' ').strip()
            # Noto Sans Bengali omits several Latin glyphs in PDF overlays.
            # Select its Latin companion for supplier, product and document
            # values so English letters do not disappear in the PDF.
            font_name = (
                bengali_font_name
                if any('\u0980' <= character <= '\u09ff' for character in value)
                else latin_font_name
            )
            # Keep ordinary statutory cells on one line.  Narrow cells such
            # as the challan number use a smaller font before any truncation;
            # wrapping changes the row layout of the prescribed form.
            if max_lines == 1:
                fitted_size = size
                while (
                    value
                    and pdfmetrics.stringWidth(value, font_name, fitted_size) > width_limit
                    and fitted_size > 2.0
                ):
                    fitted_size -= 0.2
                while value and pdfmetrics.stringWidth(value, font_name, fitted_size) > width_limit:
                    value = value[:-1]
                canvas.setFont(font_name, fitted_size)
                if align == 'right':
                    canvas.drawRightString(x, y, value)
                elif align == 'center':
                    canvas.drawCentredString(x, y, value)
                else:
                    canvas.drawString(x, y, value)
                return

            canvas.setFont(font_name, size)

            # A supplier challan number or product name often cannot fit in a
            # single statutory-book column.  Preserve the complete value over
            # two compact lines instead of silently cutting off its end.
            lines = []
            remaining = value
            while remaining and len(lines) < max_lines:
                end = len(remaining)
                while end and pdfmetrics.stringWidth(remaining[:end], font_name, size) > width_limit:
                    end -= 1
                if not end:
                    break
                if end < len(remaining):
                    # Prefer a natural separator; retain a trailing hyphen
                    # with the first part of a challan number.
                    split_at = max(
                        remaining.rfind(' ', 0, end + 1),
                        remaining.rfind('-', 0, end + 1) + 1,
                    )
                    if split_at > 0:
                        end = split_at
                lines.append(remaining[:end].strip())
                remaining = remaining[end:].lstrip()
            if remaining and lines:
                # An exceptionally long value has no room even after wrapping.
                # Mark the visible value as abbreviated rather than presenting
                # it as a complete legal reference.
                lines[-1] = lines[-1][:-1].rstrip() + '…'
            if not lines and value:
                lines = ['…']

            line_height = size + 0.8
            start_y = y + (len(lines) - 1) * line_height / 2
            for index, line_value in enumerate(lines):
                line_y = start_y - index * line_height
                if align == 'right':
                    canvas.drawRightString(x, line_y, line_value)
                elif align == 'center':
                    canvas.drawCentredString(x, line_y, line_value)
                else:
                    canvas.drawString(x, line_y, line_value)

        painter(write, width, height)
        canvas.showPage()
        canvas.save()
        buffer.seek(0)
        source_page.merge_page(PdfReader(buffer).pages[0])
        return source_page

    def _mushak_61_rows(self, wizard):
        """Build the Mushak 6.1 running material ledger (columns 1--20)."""
        events = []
        date_from, date_to = wizard._date_range()
        ledger_start = wizard._ledger_start()
        for move in wizard._moves(ledger_start, date_to):
            for line in wizard._lines(move):
                partner = move.partner_id
                vat, sd = line._vat_tax_components()
                po = line.purchase_line_id.order_id
                confirmation_date = (
                    fields.Datetime.context_timestamp(wizard, po.date_approve).date()
                    if po and po.date_approve
                    else False
                )
                events.append({
                    'kind': 'purchase',
                    # Column 2 displays the linked Purchase Order Confirmation Date
                    # in the caller's timezone; column 6 retains the challan/bill date.
                    'date': confirmation_date,
                    'event_date': move.invoice_date or move.date,
                    'product': line.product_id,
                    # Imported goods use the statutory Bill of Entry in
                    # columns 5--6; local purchases use the supplier challan.
                    'document': (
                        move.vat_import_bill_of_entry
                        if move.vat_supply_type == 'import'
                        else move.vat_mushak_number or move.vat_supplier_document_number or move.name
                    ),
                    'document_date': (
                        move.vat_import_bill_date
                        if move.vat_supply_type == 'import'
                        else move.invoice_date or move.date
                    ),
                    'partner': partner.name,
                    'address': partner.contact_address or '',
                    # Column 9 is the seller's registration/enlistment/NID.
                    # Registered suppliers use BIN; NID/TIN are fallbacks.
                    'supplier_tax_id': partner.vat_bin or partner.vat_nid or partner.vat_tin or '',
                    'description': line.product_id.name or line.name,
                    'purchase_qty': line.quantity,
                    'purchase_value': line.price_subtotal,
                    'sd': sd,
                    'vat': vat,
                    'used_qty': 0.0,
                })

        # Record actual consumed raw materials in columns 17--18.  Purchase
        # columns are deliberately blank on these production-usage rows.
        production_domain = [
            ('company_id', '=', wizard.company_id.id),
            ('state', 'in', ('to_close', 'done')),
            ('date_finished', '>=', ledger_start),
            ('date_finished', '<', date_to + timedelta(days=1)),
        ]
        if wizard.warehouse_id:
            production_domain.append(('picking_type_id.warehouse_id', '=', wizard.warehouse_id.id))
        for production in self.env['mrp.production'].search(production_domain):
            for raw_move in production.move_raw_ids.filtered(lambda item: item.state == 'done'):
                quantity = raw_move.quantity or raw_move.product_uom_qty
                if quantity:
                    events.append({
                        'kind': 'usage',
                        'date': False,
                        'event_date': (raw_move.date or production.date_finished).date(),
                        'product': raw_move.product_id,
                        'document': '',
                        'document_date': False,
                        'partner': '',
                        'address': '',
                        'supplier_tax_id': '',
                        'description': raw_move.product_id.name,
                        'purchase_qty': 0.0,
                        'purchase_value': 0.0,
                        'sd': 0.0,
                        'vat': 0.0,
                        'used_qty': quantity,
                    })

        product_ids = [event['product'].id for event in events if event['product']]
        openings_by_product = {}
        if product_ids:
            opening_domain = [
                ('company_id', '=', wizard.company_id.id),
                ('product_id', 'in', product_ids),
                ('effective_date', '<=', ledger_start),
                ('state', '=', 'locked'),
            ]
            if wizard.warehouse_id:
                opening_domain.append(('location_id.warehouse_id', '=', wizard.warehouse_id.id))
            openings = self.env['vat.stock.opening'].search(
                opening_domain, order='product_id, effective_date desc, id desc'
            )
            for opening in openings:
                openings_by_product.setdefault(opening.product_id.id, opening)

        # Purchases are applied before production usage on the same date.
        # Consumption value uses the running weighted-average material cost.
        events.sort(key=lambda event: (
            event['event_date'], 0 if event['kind'] == 'purchase' else 1,
            event['document'] or '', event['product'].id,
        ))
        balances = {}
        rows = []
        for event in events:
            product_id = event['product'].id
            if product_id not in balances:
                opening = openings_by_product.get(product_id)
                balances[product_id] = {
                    'quantity': opening.quantity if opening else 0.0,
                    'value': opening.value if opening else 0.0,
                }
            balance = balances[product_id]
            opening_qty = balance['quantity']
            opening_value = balance['value']
            total_qty = opening_qty + event['purchase_qty']
            total_value = opening_value + event['purchase_value']
            used_qty = event['used_qty']
            used_value = total_value * used_qty / total_qty if used_qty and total_qty else 0.0
            closing_qty = total_qty - used_qty
            closing_value = total_value - used_value
            balance.update({'quantity': closing_qty, 'value': closing_value})
            rows.append({
                **event,
                'opening_qty': opening_qty,
                'opening_value': opening_value,
                'total_qty': total_qty,
                'total_value': total_value,
                'used_value': used_value,
                'closing_qty': closing_qty,
                'closing_value': closing_value,
            })
        return [row for row in rows if date_from <= row['event_date'] <= date_to]

    def _mushak_62_rows(self, wizard):
        """Build the Mushak 6.2 running finished-goods/sales ledger.

        Columns (3)-(4): opening balance of the product before this row.
        Columns (5)-(6): production (only on production rows).
        Columns (7)-(8): (3)+(5) and (4)+(6).
        Columns (15)-(18): sale quantity, value, SD and VAT (sale rows).
        Columns (19)-(20): closing balance = total - quantity sold, valued
        at the running weighted-average cost (a selling price must not be
        deducted from a cost-based stock value).
        """
        events = []
        date_from, date_to = wizard._date_range()
        ledger_start = wizard._ledger_start()
        for move in wizard._moves(ledger_start, date_to):
            for line in wizard._lines(move):
                product = line.product_id
                template = product.product_tmpl_id
                vat, sd = line._vat_tax_components()
                events.append({
                    'kind': 'sale',
                    'date': move.invoice_date or move.date,
                    'product': product,
                    'document': move.vat_mushak_number or move.vat_supplier_document_number or move.name,
                    'document_date': move.vat_supplier_document_date or move.invoice_date or move.date,
                    'partner': move.partner_id.name,
                    'address': move.partner_id.contact_address or '',
                    'supplier_tax_id': move.partner_id.vat_bin or move.partner_id.vat_nid or '',
                    'description': line.name or product.display_name,
                    'quantity': line.quantity,
                    'value': line.price_subtotal,
                    'sd': sd,
                    'vat': vat,
                    'production_qty': 0.0,
                    'production_value': 0.0,
                })

        # Finished goods produced in the period appear in columns (5)-(6).
        production_domain = [
            ('company_id', '=', wizard.company_id.id),
            ('state', 'in', ('to_close', 'done')),
            ('date_finished', '>=', ledger_start),
            ('date_finished', '<', date_to + timedelta(days=1)),
        ]
        if wizard.warehouse_id:
            production_domain.append(('picking_type_id.warehouse_id', '=', wizard.warehouse_id.id))
        for production in self.env['mrp.production'].search(production_domain):
            for finished in production.move_finished_ids.filtered(
                lambda item: item.state == 'done' and item.product_id
            ):
                quantity = finished.quantity or finished.product_uom_qty
                if not quantity:
                    continue
                events.append({
                    'kind': 'production',
                    'date': (finished.date or production.date_finished).date(),
                    'datetime': finished.date or production.date_finished,
                    'product': finished.product_id,
                    'document': '', 'document_date': False, 'partner': '',
                    'address': '', 'supplier_tax_id': '',
                    'description': finished.product_id.name,
                    'quantity': 0.0, 'value': 0.0, 'sd': 0.0, 'vat': 0.0,
                    'production_qty': quantity,
                    'production_value': quantity * finished.product_id.standard_price,
                })

        # Goods received into stock by Purchase Receipt (trading goods or
        # materials sold on) also increase the quantity available for sale.
        # They are shown in columns (5)-(6) so that (7)=(3)+(5) and the
        # closing balance (19) always agrees with the stock on hand.
        sold_product_ids = {event['product'].id for event in events if event['product']}
        if sold_product_ids:
            receipt_domain = [
                ('company_id', '=', wizard.company_id.id),
                ('state', '=', 'done'),
                ('picking_type_id.code', '=', 'incoming'),
                ('product_id', 'in', list(sold_product_ids)),
                ('date', '>=', ledger_start),
                ('date', '<', date_to + timedelta(days=1)),
            ]
            if wizard.warehouse_id:
                receipt_domain.append(('picking_type_id.warehouse_id', '=', wizard.warehouse_id.id))
            for receipt in self.env['stock.move'].search(receipt_domain):
                quantity = receipt.quantity or receipt.product_uom_qty
                if not quantity:
                    continue
                purchase_line = getattr(receipt, 'purchase_line_id', False)
                unit_cost = purchase_line.price_unit if purchase_line else receipt.product_id.standard_price
                events.append({
                    'kind': 'receipt',
                    'date': receipt.date.date(),
                    'datetime': receipt.date,
                    'product': receipt.product_id,
                    'document': '', 'document_date': False, 'partner': '',
                    'address': '', 'supplier_tax_id': '',
                    'description': receipt.product_id.name,
                    'quantity': 0.0, 'value': 0.0, 'sd': 0.0, 'vat': 0.0,
                    'production_qty': quantity,
                    'production_value': quantity * unit_cost,
                })

        product_ids = [event['product'].id for event in events if event['product']]
        openings_by_product = {}
        if product_ids:
            opening_domain = [
                ('company_id', '=', wizard.company_id.id),
                ('product_id', 'in', product_ids),
                ('effective_date', '<=', date_to),
                ('state', '=', 'locked'),
            ]
            if wizard.warehouse_id:
                opening_domain.append(('location_id.warehouse_id', '=', wizard.warehouse_id.id))
            # Oldest first: an opening dated on/before the ledger start is the
            # initial balance; one dated inside the printed range re-bases the
            # ledger from its effective date (it is a stock adjustment that
            # sets the on-hand quantity, exactly like Physical Inventory).
            for opening in self.env['vat.stock.opening'].search(
                opening_domain, order='product_id, effective_date asc, id asc'
            ):
                openings_by_product.setdefault(opening.product_id.id, []).append(opening)

        initial_openings = {}
        for product_id, openings in openings_by_product.items():
            for opening in openings:
                # An opening dated on/before the ledger start is the initial
                # balance.  When the product has none (e.g. the opening was
                # entered after back-dated sales), the first opening inside
                # the printed range is the book's opening balance for the
                # whole range.  Any later opening re-bases the ledger.
                if opening.effective_date <= ledger_start or product_id not in initial_openings:
                    initial_openings[product_id] = opening
                else:
                    events.append({
                        'kind': 'opening', 'date': opening.effective_date,
                        'product': opening.product_id, 'document': '',
                        'opening_record': opening,
                    })

        # Production is booked before sales made on the same date.
        events.sort(key=lambda event: (
            event['date'], {'opening': -1, 'production': 0, 'receipt': 0}.get(event['kind'], 1),
            event['document'] or '', event['product'].id,
        ))
        balances = {}
        rows = []
        for event in events:
            product_id = event['product'].id
            if product_id not in balances:
                opening = initial_openings.get(product_id)
                balances[product_id] = {
                    'quantity': opening.quantity if opening else 0.0,
                    'value': opening.value if opening else 0.0,
                }
            balance = balances[product_id]
            if event['kind'] == 'opening':
                # Re-base the running balance; this is not a printed row.
                record = event['opening_record']
                balance.update({'quantity': record.quantity, 'value': record.value})
                continue
            base = initial_openings.get(product_id)
            # An opening entered after these transactions is a snapshot of the
            # stock that already includes them: they are printed against that
            # opening but must not be applied to it a second time.
            is_pre_opening = bool(
                base and base.effective_date > ledger_start and (
                    event['date'] < base.effective_date
                    or (
                        event.get('datetime') and base.inventory_applied_date
                        and event['datetime'] < base.inventory_applied_date
                    )
                )
            )
            opening_qty, opening_value = balance['quantity'], balance['value']
            total_qty = opening_qty + event['production_qty']
            total_value = opening_value + event['production_value']
            sold_qty = event['quantity']
            sold_cost = total_value * sold_qty / total_qty if sold_qty and total_qty else 0.0
            closing_qty = total_qty - sold_qty
            closing_value = total_value - sold_cost
            if not is_pre_opening:
                balance.update({'quantity': closing_qty, 'value': closing_value})
            rows.append({
                **event,
                'opening_qty': opening_qty, 'opening_value': opening_value,
                'total_qty': total_qty, 'total_value': total_value,
                'closing_qty': closing_qty, 'closing_value': closing_value,
            })
        return [row for row in rows if date_from <= row['date'] <= date_to]

    def _render_book(self, form_path, wizard, form_code):
        """Fill Mushak 6.1/6.2 line by line on the supplied legal sheet."""
        from PyPDF2 import PdfReader, PdfWriter

        rows = (
            self._mushak_61_rows(wizard) if form_code == '6.1'
            else self._mushak_62_rows(wizard)
        )
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
                # The 6.2 source grid has a separate row for the column
                # numbers/formulas above the actual transaction row.  The
                # latter spans y=232..250 (PDF coordinates), so its visual
                # centre is y=240.  Using y=250 drew values on top of the
                # formula row, which made columns (7), (8), (19) and (20)
                # look incorrectly mapped.
                y = 225 if form_code == '6.1' else 240
                if not row:
                    return
                if form_code == '6.1':
                    # The running material ledger fills columns 1--20.
                    # Each x value is the centre of its printed statutory
                    # cell, aligned to the column labels
                    # (1)–(21) of the NBR source form.
                    cells = [
                        (number, 135, 24), (row['date'], 162, 25), (row['opening_qty'], 192, 27),
                        (row['opening_value'], 223, 28), (row['document'], 259, 29),
                        (row['document_date'], 292, 28), (row['partner'], 320, 27),
                        (row['address'], 354, 34), (row['supplier_tax_id'], 396, 42),
                        (row['description'], 434, 35), (row['purchase_qty'], 468, 27),
                        (row['purchase_value'], 502, 28), (row['sd'], 538, 27),
                        (row['vat'], 570, 26), (row['total_qty'], 599, 25),
                        (row['total_value'], 625, 26), (row['used_qty'], 653, 26),
                        (row['used_value'], 674, 20), (row['closing_qty'], 704, 27),
                        (row['closing_value'], 737, 28), ('', 769, 21),
                    ]
                else:
                    # Centres and widths of Mushak 6.2 columns (1)--(21),
                    # measured from the official NBR PDF grid.  Do not share
                    # these values with 6.1: the two statutory forms have
                    # different left margins and column widths.
                    is_sale = row['kind'] == 'sale'
                    is_production = row['kind'] in ('production', 'receipt')

                    def amount(value, show=True):
                        # Python treats 0.0 == False, which made the generic
                        # ``_display`` print zero balances as blank cells.
                        # Format numbers explicitly so 0.00 is printed.
                        if not show:
                            return ''
                        return format(float(value or 0.0), ',.2f')

                    # (value, centre x, cell width, max_lines, font size)
                    cells = [
                        (number, 135, 29, 1, 4.0),
                        (row['date'], 163, 26, 1, 4.0),
                        (amount(row['opening_qty']), 193, 27, 1, 4.0),            # (3)
                        (amount(row['opening_value']), 228, 33, 1, 4.0),          # (4)
                        (amount(row['production_qty'], is_production), 257, 21, 1, 4.0),   # (5)
                        (amount(row['production_value'], is_production), 282, 23, 1, 4.0), # (6)
                        (amount(row['total_qty']), 308, 27, 1, 4.0),              # (7)=(3)+(5)
                        (amount(row['total_value']), 336, 29, 1, 4.0),            # (8)=(4)+(6)
                        (row['partner'], 361, 20, 3, 3.4),                        # (9)
                        (row['address'], 385, 26, 3, 3.4),                        # (10)
                        (row['supplier_tax_id'], 426, 53, 1, 4.0),                # (11)
                        (row['document'], 464, 21, 3, 3.4),                       # (12)
                        (row['document_date'], 489, 25, 1, 4.0),                  # (13)
                        (row['description'], 516, 26, 3, 3.4),                    # (14)
                        (amount(row['quantity'], is_sale), 543, 26, 1, 4.0),      # (15)
                        (amount(row['value'], is_sale), 575, 34, 1, 4.0),         # (16)
                        (amount(row['sd'], is_sale), 612, 35, 1, 4.0),            # (17)
                        (amount(row['vat'], is_sale), 642, 22, 1, 4.0),           # (18)
                        (amount(row['closing_qty']), 670, 31, 1, 4.0),            # (19)
                        (amount(row['closing_value']), 705, 37, 1, 4.0),          # (20)
                        ('', 736, 24, 1, 4.0),                                    # (21)
                    ]
                if form_code == '6.1':
                    cells = [(v, x, w, 1, 4.0) for v, x, w, *_ in cells]
                for value, x, cell_width, max_lines, font_size in cells:
                    # ``x`` is already the cell centre.
                    write(value, x, y, cell_width - 2, font_size, 'center', max_lines)

            writer.add_page(self._overlay_page(page, paint))
        output = BytesIO()
        writer.write(output)
        return output.getvalue()

    def _render_mushak_43(self, form_path, record):
        """Fill the official Mushak 4.3 input-output coefficient form.

        The supplied NBR page is landscape and its single detail row has a
        different grid from the generic report forms.  A dedicated overlay is
        therefore required; otherwise values appear above the table or are
        omitted altogether.
        """
        from PyPDF2 import PdfReader, PdfWriter

        def code_of(template):
            code = template.vat_hs_code_id or template.hs_code_id
            return getattr(code, 'code', '') or ''

        def amount(value):
            return '%.2f' % (value or 0.0)

        company = record.env.company
        product = record.product_tmpl_id
        inputs = record.line_ids
        source_page = PdfReader(form_path).pages[0]
        writer = PdfWriter()

        # A coefficient is for one output product.  The statutory form
        # provides one output row, so its inputs are kept together in the
        # material-description column and their values are totalled.
        material_description = '; '.join(inputs.mapped('product_id.display_name'))
        input_quantity = sum(inputs.mapped('quantity'))
        wastage_quantity = input_quantity * (record.wastage_percent or 0.0) / 100.0
        output_uom = product.vat_uom_id or product.uom_id
        address = company.vat_registered_address or company.partner_id.contact_address or ''

        def paint(write, width, height):
            # Header information: positions are the blank space following the
            # five labels in the prescribed landscape form.
            write(company.vat_legal_name or company.name, 185, 383, 220, 6.5)
            write(address, 185, 371, 260, 5.4)
            write(company.vat_bin or '', 185, 359, 120, 6.5)
            write(fields.Date.context_today(record), 185, 347, 90, 6.3)
            write(record.effective_date or '', 310, 335, 90, 6.3)

            # (centre x, usable width) for columns (1) through (12).
            cells = [
                (140, 37), (192, 60), (285, 118), (368, 61),
                (414, 36), (464, 40), (514, 34), (560, 52),
                (614, 42), (671, 52), (710, 40), (760, 26),
            ]
            values = [
                '1', code_of(product), product.display_name or '',
                output_uom.name or '', material_description,
                amount(input_quantity * (1.0 + (record.wastage_percent or 0.0) / 100.0)),
                amount(record.material_cost),
                amount(wastage_quantity), amount(record.wastage_percent),
                'মূল্য সংযোজন', amount(record.value_addition), '',
            ]
            for value, (x, cell_width) in zip(values, cells):
                write(value, x, 243, cell_width - 3, 4.7, 'center')

            write(getattr(company, 'vat_authorised_person_name', '') or '', 650, 145, 125, 6)

        writer.add_page(self._overlay_page(source_page, paint))
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
                # The original form has two distinct table grids.  Keep the
                # company fields inside their dotted blanks, then use the
                # actual centre of each printed column (rather than sharing
                # the purchase grid coordinates with the sales grid).
                write(company.vat_legal_name or company.name, 260, 655, 80, 6.2)
                write(company.vat_bin or '', 382, 655, 100, 6.2)

                # (centre x, available width) — purchase columns (1) to (7)
                purchase_cells = [
                    (126, 43), (182, 64), (242, 50), (286, 31),
                    (332, 54), (389, 54), (462, 84),
                ]
                # (centre x, available width) — sales columns (1) to (7)
                sales_cells = [
                    (123, 36), (176, 63), (241, 57), (297, 47),
                    (348, 47), (404, 59), (476, 78),
                ]
                for value, (x, cell_width) in zip(fields_for(purchase, index), purchase_cells):
                    write(value, x, 518, cell_width - 3, 4.5, 'center')
                for value, (x, cell_width) in zip(fields_for(sale, index), sales_cells):
                    write(value, x, 390, cell_width - 3, 4.5, 'center')
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
            lines = record.invoice_line_ids.filtered(lambda l: l.display_type == 'product')
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
        if form_code == '4.3':
            return self._render_mushak_43(form_path, record)
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