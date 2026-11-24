from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    hs_code_id = fields.Many2one(
        "zencore.hs.code",
        string="VAT HS Code Master",
        ondelete="restrict",
        index=True,
    )

    @api.model
    def _sync_hs_code_values(self, vals):
        vals = dict(vals)
        hs_code_model = self.env["zencore.hs.code"]
        if "hs_code_id" in vals:
            hs_code = hs_code_model.browse(vals["hs_code_id"]).exists()
            vals["hs_code"] = hs_code.hscode if hs_code else False
        elif "hs_code" in vals:
            code = vals.get("hs_code")
            hs_code = hs_code_model.search([("hscode", "=", code)], limit=1) if code else hs_code_model.browse()
            vals["hs_code_id"] = hs_code.id or False
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([self._sync_hs_code_values(vals) for vals in vals_list])

    def write(self, vals):
        return super().write(self._sync_hs_code_values(vals))
