# -*- coding: utf-8 -*-
from odoo import api, models, _
from odoo.exceptions import ValidationError
from odoo.tools import float_compare


class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_post(self):
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        for move in self:
            if move.move_type == 'out_invoice':
                for line in move.invoice_line_ids:
                    if line.display_type in ('line_section', 'line_note', 'line_subsection') or not line.product_id:
                        continue
                    if line.sale_line_ids:
                        for sale_line in line.sale_line_ids:
                            # Convert delivered quantity to invoice line UoM if different
                            delivered_qty = sale_line.qty_delivered
                            if (
                                sale_line.product_uom_id
                                and line.product_uom_id
                                and sale_line.product_uom_id != line.product_uom_id
                            ):
                                delivered_qty = sale_line.product_uom_id._compute_quantity(
                                    delivered_qty, line.product_uom_id
                                )

                            if float_compare(line.quantity, delivered_qty, precision_digits=precision) > 0:
                                raise ValidationError(
                                    _(
                                        "You cannot confirm the invoice because the quantity (%(inv_qty)s) for product '%(product)s' exceeds the delivered quantity (%(del_qty)s) from Sales Order %(order)s.",
                                        inv_qty=line.quantity,
                                        product=line.product_id.display_name or line.name,
                                        del_qty=delivered_qty,
                                        order=sale_line.order_id.name,
                                    )
                                )
        return super().action_post()
