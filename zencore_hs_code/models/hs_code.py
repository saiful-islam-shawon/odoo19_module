from odoo import fields, models


class ZencoreHSCode(models.Model):
    _name = "zencore.hs.code"
    _description = "Zencore HS Code"
    _rec_name = "hscode"
    _order = "hscode"

    hscode = fields.Char(
        string="HS Code",
        required=True,
        index=True,
    )

    tariff_description = fields.Text(
        string="Tariff Description",
        required=True,
    )

    cd = fields.Float(
        string="CD",
        digits=(16, 2),
    )

    sd = fields.Float(
        string="SD",
        digits=(16, 2),
    )

    vat = fields.Float(
        string="VAT",
        digits=(16, 2),
    )

    ait = fields.Float(
        string="AIT",
        digits=(16, 2),
    )

    at = fields.Float(
        string="AT",
        digits=(16, 2),
    )

    rd = fields.Float(
        string="RD",
        digits=(16, 2),
    )

    _hscode_unique = models.Constraint(
        "UNIQUE(hscode)",
        "The HS Code must be unique.",
    )


    def write(self, vals):
        result = super().write(vals)
        if "hscode" in vals:
            products = self.env["product.template"].search([("hs_code_id", "in", self.ids)])
            for hs_code in self:
                products.filtered(lambda product: product.hs_code_id == hs_code).write({"hs_code": hs_code.hscode})
        return result
