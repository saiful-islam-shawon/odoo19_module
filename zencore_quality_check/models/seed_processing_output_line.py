# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class ZencoreSeedProcessingOutputLine(models.Model):
    _name = 'zencore.seed.processing.output.line'
    _description = 'Seed Processing Graded Output Line'
    _order = 'id asc'

    batch_id = fields.Many2one(
        'zencore.seed.processing.batch',
        string='Processing Batch',
        required=True,
        ondelete='cascade',
        index=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='batch_id.company_id',
        store=True,
        readonly=True
    )
    product_id = fields.Many2one(
        'product.product',
        string='Output Product',
        required=True,
        help="Graded output seed product, by-product or scrap item."
    )
    category = fields.Selection(
        [
            ('good', 'Good'),
            ('bad', 'Bad'),
            ('waste', 'Waste'),
            ('by_product', 'Substandard / By-Product'),
        ],
        string='Category',
        default='good',
        required=True,
        help="Classification of the processed output: Good, Bad, or Waste."
    )
    pack_size = fields.Char(
        string='Pack Size',
        help="e.g. 10 Kg Bag, 20 Kg Bag, 50 Kg Bag"
    )
    bag_count = fields.Integer(
        string='Bag Count',
        default=0,
        help="Number of commercial bags packed for this grade."
    )
    quantity = fields.Float(
        string='Total Weight (kg)',
        required=True,
        default=0.0,
        digits=(12, 2),
        help="Net output weight in kilograms."
    )
    lot_id = fields.Many2one(
        'stock.lot',
        string='Stock Lot',
        readonly=True,
        copy=False,
        help="Traceable Odoo Stock Lot."
    )
    lot_name = fields.Char(
        string='Unique Lot Number',
        copy=False,
        readonly=True,
        help="Format 1 Unique Lot Number (e.g., LOT/YYYY/00001)."
    )
    remarks = fields.Char(
        string='Remarks',
        help="Specific grading notes or observations."
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('lot_name'):
                lot_name = self.env['ir.sequence'].next_by_code('zencore.seed.processing.lot.seq')
                if not lot_name:
                    lot_name = _('LOT/%s/00001') % fields.Date.today().year
                vals['lot_name'] = lot_name
            
            # Create or link corresponding stock.lot
            if vals.get('product_id') and not vals.get('lot_id'):
                batch_company_id = False
                if vals.get('batch_id'):
                    batch = self.env['zencore.seed.processing.batch'].browse(vals['batch_id'])
                    batch_company_id = batch.company_id.id if batch else self.env.company.id
                else:
                    batch_company_id = self.env.company.id

                try:
                    stock_lot = self.env['stock.lot'].create({
                        'name': vals['lot_name'],
                        'product_id': vals['product_id'],
                        'company_id': batch_company_id,
                    })
                    vals['lot_id'] = stock_lot.id
                except Exception:
                    # In case tracking is not enabled or lot creation fails safely
                    pass

        return super().create(vals_list)

    def write(self, vals):
        for record in self:
            if record.batch_id and record.batch_id.state == 'done':
                raise UserError(_("Cannot modify output lines of a completed processing batch!"))
        return super().write(vals)

    def unlink(self):
        for record in self:
            if record.batch_id and record.batch_id.state == 'done':
                raise UserError(_("Cannot delete output lines of a completed processing batch!"))
        return super().unlink()

