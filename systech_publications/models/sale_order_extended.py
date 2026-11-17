from odoo import models, fields, api

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # country_id = fields.Many2one('res.country', string="Country")
    
    # state_id = fields.Many2one(
    #     'res.country.state',
    #     string="Division",
    #     domain="[('country_id','=',country_id)]"
    # )

    # district_id = fields.Many2one(
    #     'res.district',
    #     string="District",
    #     domain="[('state_id','=',state_id)]"
    # )

    # thana_id = fields.Many2one(
    #     'res.thana',
    #     string="Thana",
    #     domain="[('district_id','=',district_id)]"
    # )

    country_id = fields.Many2one('res.country', related="partner_id.country_id", store=True,string="Country", index=True)

    state_id = fields.Many2one(
        'res.country.state',
        related="partner_id.state_id",
        store=True,
        string="Division",
        # domain="[('thana_id','=',thana_id)]",
        index=True
    )
    # cmr = fields.Char(string='Customer ID', related="partner_id.cmr", store=True, readonly=True, copy=False, index=True)
    district_id = fields.Many2one(
        'res.district',
        related="partner_id.district_id",
        store=True,
        string="District",
        # domain="[('thana_id','=',thana_id)]",
        index=True
    )

    thana_id = fields.Many2one(
        'res.thana',
        related="partner_id.thana_id",
        store=True,
        string="Thana",
        # domain="[('thana_id','=',thana_id)]",
        index=True
    )

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id:
            self.country_id = self.partner_id.country_id
            self.state_id = self.partner_id.state_id
            self.district_id = self.partner_id.district_id
            self.thana_id = self.partner_id.thana_id
    
    def _create_invoices(self, grouped=False, final=False, date=None):
        moves = super(SaleOrder, self)._create_invoices(grouped, final, date)

        # Propagate thana, district, state, country to account.move
        for order, move in zip(self, moves):
            move.country_id = order.country_id
            move.state_id = order.state_id
            move.district_id = order.district_id
            move.thana_id = order.thana_id

        return moves
    
    def action_confirm(self):
        res = super().action_confirm()

        for order in self:
            for picking in order.picking_ids:
                picking.write({
                    'country_id': order.country_id.id,
                    'state_id': order.state_id.id,
                    'district_id': order.district_id.id,
                    'thana_id': order.thana_id.id,
                })

        return res
    
from odoo import models, fields

class SaleReport(models.Model):
    _inherit = "sale.report"

    district_id = fields.Many2one("res.district", string="District", readonly=True)
    thana_id = fields.Many2one("res.thana", string="Thana", readonly=True)

    def _select_additional_fields(self):
        res = super()._select_additional_fields()
        res.update({
            "district_id": "partner.district_id",
            "thana_id": "partner.thana_id",
        })
        return res

    def _group_by_sale(self):
        res = super()._group_by_sale()
        res += """
            , partner.district_id
            , partner.thana_id
        """
        return res