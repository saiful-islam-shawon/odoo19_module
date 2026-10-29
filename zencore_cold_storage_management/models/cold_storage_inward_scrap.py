# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ColdStorageInwardScrap(models.Model):
    _name = 'cold.storage.inward.scrap'
    _description = 'Cold Storage Inward Scrap (Damage & Loss)'
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
        help="Unique auto-generated scrap reference."
    )
    inward_id = fields.Many2one(
        'cold.storage.inward',
        string='Inward Lot',
        required=True,
        ondelete='cascade',
        index=True,
        help="Inward lot experiencing damage or loss."
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.context_today,
        help="Date when damage or loss was identified."
    )
    slot_id = fields.Many2one(
        'cold.storage.master.setup',
        string='Storage Slot',
        required=True,
        ondelete='restrict',
        help="Storage slot where damaged goods were located."
    )
    allowed_slot_ids = fields.Many2many(
        'cold.storage.master.setup',
        compute='_compute_allowed_slot_ids',
        string="Allowed Slots",
        help="Dynamic list of slots currently holding products in this inward lot."
    )
    available_quantity = fields.Integer(
        string='Available in Slot',
        compute='_compute_available_quantity',
        readonly=True,
        help="Quantity of bags currently available in the selected slot."
    )
    quantity = fields.Integer(
        string='Scrap Quantity (Bags)',
        required=True,
        default=1,
        help="Quantity in bags lost, rotten, or damaged."
    )
    reason = fields.Char(
        string='Reason / Cause of Damage',
        required=True,
        help="Description or reason for scrap (e.g. Rotten, damaged during handling, moisture loss)."
    )
    user_id = fields.Many2one(
        'res.users',
        string='Responsible',
        default=lambda self: self.env.user,
        readonly=True,
        help="User responsible for recording this scrap entry."
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='inward_id.company_id',
        store=True,
        readonly=True
    )

    @api.depends('inward_id.allocation_ids.slot_id', 'inward_id.allocation_ids.quantity')
    def _compute_allowed_slot_ids(self):
        for record in self:
            if record.inward_id:
                allocated_slots = record.inward_id.allocation_ids.filtered(lambda a: a.quantity > 0).mapped('slot_id')
                record.allowed_slot_ids = allocated_slots
            else:
                record.allowed_slot_ids = self.env['cold.storage.master.setup']

    @api.depends('slot_id', 'inward_id.allocation_ids.quantity', 'inward_id.allocation_ids.slot_id')
    def _compute_available_quantity(self):
        for record in self:
            if record.inward_id and record.slot_id:
                alloc = record.inward_id.allocation_ids.filtered(lambda a: a.slot_id == record.slot_id)
                record.available_quantity = sum(alloc.mapped('quantity'))
            else:
                record.available_quantity = 0

    @api.onchange('inward_id')
    def _onchange_inward_id(self):
        if self.inward_id:
            allocated_slot_ids = self.inward_id.allocation_ids.filtered(lambda a: a.quantity > 0).mapped('slot_id').ids
            return {'domain': {'slot_id': [('id', 'in', allocated_slot_ids)]}}
        return {'domain': {'slot_id': []}}

    @api.onchange('slot_id')
    def _onchange_slot_id(self):
        if self.inward_id and self.slot_id:
            alloc = self.inward_id.allocation_ids.filtered(lambda a: a.slot_id == self.slot_id)
            self.available_quantity = sum(alloc.mapped('quantity'))
        else:
            self.available_quantity = 0

    @api.constrains('quantity')
    def _check_quantity_positive(self):
        for record in self:
            if record.quantity <= 0:
                raise ValidationError(_("Scrap Quantity (Bags) must be greater than zero."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('cold.storage.scrap') or _('New')
        records = super().create(vals_list)
        for record in records:
            record._sync_storage_allocation_scrap()
        return records

    def _sync_storage_allocation_scrap(self):
        self.ensure_one()
        inward = self.inward_id
        slot_alloc = inward.allocation_ids.filtered(lambda a: a.slot_id == self.slot_id)
        if not slot_alloc:
            raise ValidationError(
                _("Storage Slot '%s' is not currently allocated in this Inward Lot.") % (self.slot_id.name or '')
            )

        total_avail = sum(slot_alloc.mapped('quantity'))
        if self.quantity > total_avail:
            raise ValidationError(_(
                "Scrap quantity (%(qty)s bags) cannot exceed available quantity (%(avail)s bags) in Slot '%(slot)s'."
            ) % {
                'qty': self.quantity,
                'avail': total_avail,
                'slot': self.slot_id.name,
            })

        # Deduct from slot_alloc lines
        qty_to_deduct = self.quantity
        for alloc in slot_alloc:
            if alloc.quantity <= qty_to_deduct:
                qty_to_deduct -= alloc.quantity
                alloc.unlink()
            else:
                alloc.quantity -= qty_to_deduct
                qty_to_deduct = 0
                break
