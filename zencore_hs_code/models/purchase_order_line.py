from odoo import api, fields, models


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    hs_cd = fields.Monetary(string="CD", currency_field="currency_id", compute="_compute_hs_duty_amounts")
    hs_sd = fields.Monetary(string="SD", currency_field="currency_id", compute="_compute_hs_duty_amounts")
    hs_vat = fields.Monetary(string="VAT", currency_field="currency_id", compute="_compute_hs_duty_amounts")
    hs_ait = fields.Monetary(string="AIT", currency_field="currency_id", compute="_compute_hs_duty_amounts")
    hs_at = fields.Monetary(string="AT", currency_field="currency_id", compute="_compute_hs_duty_amounts")
    hs_rd = fields.Monetary(string="RD", currency_field="currency_id", compute="_compute_hs_duty_amounts")

    @api.depends(
        "price_unit", "product_qty",
        "product_id.product_tmpl_id.hs_code_id.cd",
        "product_id.product_tmpl_id.hs_code_id.sd",
        "product_id.product_tmpl_id.hs_code_id.vat",
        "product_id.product_tmpl_id.hs_code_id.ait",
        "product_id.product_tmpl_id.hs_code_id.at",
        "product_id.product_tmpl_id.hs_code_id.rd",
    )
    def _compute_hs_duty_amounts(self):
        for line in self:
            code = line.product_id.product_tmpl_id.hs_code_id
            base = line.price_unit * line.product_qty
            line.hs_cd = base * (code.cd or 0.0)
            line.hs_sd = base * (code.sd or 0.0)
            line.hs_vat = base * (code.vat or 0.0)
            line.hs_ait = base * (code.ait or 0.0)
            line.hs_at = base * (code.at or 0.0)
            line.hs_rd = base * (code.rd or 0.0)

    def _get_hs_total_duty(self):
        self.ensure_one()
        return sum((self.hs_cd, self.hs_sd, self.hs_vat, self.hs_ait, self.hs_at, self.hs_rd))
