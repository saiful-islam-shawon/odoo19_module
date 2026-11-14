# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    total_qty = fields.Float(
        string='Total Qty',
        compute='_compute_total_qty',
        store=True,
        digits='Product Unit of Measure',
        readonly=True,
        help="Total quantity of all product lines in this sales order.",
    )
    has_done_delivery = fields.Boolean(
        string='Has Done Delivery',
        compute='_compute_has_done_delivery',
        store=True,
        help="Technical field indicating if at least one delivery picking is validated (done).",
    )

    @api.depends('order_line.product_uom_qty', 'order_line.display_type')
    def _compute_total_qty(self):
        for order in self:
            order.total_qty = sum(
                line.product_uom_qty for line in order.order_line if not line.display_type
            )

    @api.depends('picking_ids.state')
    def _compute_has_done_delivery(self):
        for order in self:
            order.has_done_delivery = any(p.state == 'done' for p in order.picking_ids)

    def action_add_from_catalog(self):
        for order in self:
            if order.has_done_delivery:
                raise UserError(
                    _("Delivery has already started for order '%s'. You cannot add products from catalog.", order.name)
                )
        return super().action_add_from_catalog()


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            display_type = vals.get('display_type')
            if not display_type:
                order_id = vals.get('order_id') or self.env.context.get('default_order_id')
                if order_id:
                    order = self.env['sale.order'].browse(order_id)
                    if order.has_done_delivery:
                        raise UserError(
                            _("Delivery has already started for order '%(order)s'. You cannot add new products to this order.",
                              order=order.name)
                        )
        return super().create(vals_list)

    def write(self, vals):
        if 'product_uom_qty' in vals or 'product_id' in vals:
            precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
            for line in self:
                if line.order_id.has_done_delivery and not line.display_type:
                    if 'product_id' in vals and vals['product_id'] != line.product_id.id:
                        raise UserError(
                            _("Delivery has already started for order '%(order)s'. You cannot change the product on line '%(product)s'.",
                              order=line.order_id.name,
                              product=line.product_id.display_name or line.name)
                        )
                    if 'product_uom_qty' in vals:
                        new_qty = vals['product_uom_qty']
                        if float_compare(new_qty, line.product_uom_qty, precision_digits=precision) > 0:
                            raise UserError(
                                _("Delivery has already started for order '%(order)s'. You cannot increase the quantity of '%(product)s' from %(old_qty)s to %(new_qty)s.",
                                  order=line.order_id.name,
                                  product=line.product_id.display_name or line.name,
                                  old_qty=line.product_uom_qty,
                                  new_qty=new_qty)
                            )
        return super().write(vals)

    def unlink(self):
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        for line in self:
            if line.order_id.has_done_delivery and not line.display_type:
                if float_compare(line.qty_delivered, 0.0, precision_digits=precision) > 0:
                    raise UserError(
                        _("Delivery has already started for order '%(order)s'. You cannot delete the delivered product '%(product)s'.",
                          order=line.order_id.name,
                          product=line.product_id.display_name or line.name)
                    )
        return super().unlink()
