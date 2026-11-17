from odoo import models, fields, api


class AccountPaymentExtended(models.Model):
    _inherit = 'account.payment'

    partner_country_id = fields.Many2one(
        'res.country',
        related='partner_id.country_id',
        store=True,
        string='Country',
        index=True,
    )

    partner_state_id = fields.Many2one(
        'res.country.state',
        related='partner_id.state_id',
        store=True,
        string='Division',
        index=True,
    )

    district_id = fields.Many2one(
        'res.district',
        related='partner_id.district_id',
        store=True,
        string='District',
        index=True,
    )

    thana_id = fields.Many2one(
        'res.thana',
        related='partner_id.thana_id',
        store=True,
        string='Thana',
        index=True,
    )
