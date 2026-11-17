from odoo import models, fields, api


class ResPartnerExtended(models.Model):
    _inherit = 'res.partner'

    customer_id = fields.Char(
        string="Customer ID",
        copy=False,
        index=True,
    )

    thana_id = fields.Many2one(
        'res.thana',
        string='Thana'
    )

    district_id = fields.Many2one(
        'res.district',
        string='District',
    )

    @api.onchange('thana_id')
    def _onchange_thana_id(self):
        if self.thana_id:
            self.district_id = self.thana_id.district_id
            self.state_id = self.thana_id.state_id
            self.country_id = self.thana_id.country_id

    # @api.model
    # def _name_search(self, name='', domain=None, operator='ilike', limit=100, order=None):
    #     domain = domain or []
    #     if name:
    #         partners = self.search(
    #             [('customer_id', '=', name)] + domain,
    #             limit=limit,
    #             order=order,
    #         )
    #         if partners:
    #             return partners.ids
    #     return super()._name_search(
    #         name=name, domain=domain, operator=operator,
    #         limit=limit, order=order,
    #     )



    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        domain = domain or []
        if name:
            partners = self.search(
                [('customer_id', 'ilike', name)] + domain,
                limit=limit,
            )
            name_partners = self.search(
                [('name', operator, name)] + domain,
                limit=limit,
            )
            combined = partners | name_partners
            return [(p.id, p.display_name) for p in combined[:limit]]
        
        return super().name_search(name=name, domain=domain, operator=operator, limit=limit)
    


class ResThana(models.Model):
    _name = 'res.thana'
    _description = 'Thana'

    name = fields.Char(string='Thana Name', required=True)
    district_id = fields.Many2one(
        'res.district',
        string='District',
        required=True
    )
    state_id = fields.Many2one(
        'res.country.state',
        related="district_id.state_id",
        string='Division',
        store=True
    )
    country_id = fields.Many2one(
        'res.country',
        related="district_id.country_id",
        string='Country',
        store=True
    )

    @api.onchange('district_id')
    def _onchange_district_id(self):
        if self.district_id:
            self.state_id = self.district_id.state_id
            self.country_id = self.district_id.country_id


class ResDistrict(models.Model):
    _name = 'res.district'
    _description = 'District'

    name = fields.Char(string='District Name', required=True)
    state_id = fields.Many2one(
        'res.country.state',
        string='Division',
        required=True
    )
    country_id = fields.Many2one(
        'res.country',
        related="state_id.country_id",
        string='Country',
        store=True
    )

    @api.onchange('state_id')
    def _onchange_state_id(self):
        if self.state_id:
            self.country_id = self.state_id.country_id
