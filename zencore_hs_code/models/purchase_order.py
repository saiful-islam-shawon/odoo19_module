from odoo import api, fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    # Duties are shown for information only; they are not part of amount_total.
    total_cd = fields.Monetary(string="CD", currency_field="currency_id", compute="_compute_hs_duty_totals", store=True)
    total_sd = fields.Monetary(string="SD", currency_field="currency_id", compute="_compute_hs_duty_totals", store=True)
    total_vat = fields.Monetary(string="VAT", currency_field="currency_id", compute="_compute_hs_duty_totals", store=True)
    total_ait = fields.Monetary(string="AIT", currency_field="currency_id", compute="_compute_hs_duty_totals", store=True)
    total_at = fields.Monetary(string="AT", currency_field="currency_id", compute="_compute_hs_duty_totals", store=True)
    total_rd = fields.Monetary(string="RD", currency_field="currency_id", compute="_compute_hs_duty_totals", store=True)
    total_duty = fields.Monetary(
        string="Total Duty", currency_field="currency_id",
        compute="_compute_hs_duty_totals", store=True,
    )

    @api.depends(
        "order_line.display_type",
        "order_line.hs_cd", "order_line.hs_sd", "order_line.hs_vat",
        "order_line.hs_ait", "order_line.hs_at", "order_line.hs_rd",
    )
    def _compute_hs_duty_totals(self):
        for order in self:
            lines = order.order_line.filtered(lambda line: not line.display_type)
            order.total_cd = sum(lines.mapped("hs_cd"))
            order.total_sd = sum(lines.mapped("hs_sd"))
            order.total_vat = sum(lines.mapped("hs_vat"))
            order.total_ait = sum(lines.mapped("hs_ait"))
            order.total_at = sum(lines.mapped("hs_at"))
            order.total_rd = sum(lines.mapped("hs_rd"))
            order.total_duty = sum(line._get_hs_total_duty() for line in lines)
