# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ColdStorageInwardPlotting(models.Model):
    _name = 'cold.storage.inward.plotting'
    _description = 'Cold Storage Inward Slot Plotting (Relocation)'
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
        help="Unique auto-generated plotting reference."
    )
    inward_id = fields.Many2one(
        'cold.storage.inward',
        string='Inward Lot',
        required=True,
        ondelete='cascade',
        index=True,
        help="Inward lot being relocated."
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.context_today,
        help="Date of physical slot relocation."
    )
    from_slot_id = fields.Many2one(
        'cold.storage.master.setup',
        string='From Slot',
        required=True,
        ondelete='restrict',
        help="Current storage slot of the products."
    )
    allowed_from_slot_ids = fields.Many2many(
        'cold.storage.master.setup',
        compute='_compute_allowed_from_slot_ids',
        string="Allowed From Slots",
        help="Dynamic list of slots currently holding products in this inward lot."
    )
    available_quantity = fields.Integer(
        string='Available in From Slot',
        compute='_compute_available_quantity',
        readonly=True,
        help="Quantity of bags currently available in the source slot."
    )
    to_slot_id = fields.Many2one(
        'cold.storage.master.setup',
        string='To Slot',
        required=True,
        domain="[('activate', '=', True)]",
        ondelete='restrict',
        help="Destination active storage slot."
    )
    quantity = fields.Integer(
        string='Transfer Quantity (Bosta)',
        required=True,
        default=1,
        help="Quantity in bags / bosta to transfer to the destination slot."
    )
    user_id = fields.Many2one(
        'res.users',
        string='Responsible',
        default=lambda self: self.env.user,
        readonly=True,
        help="User responsible for recording this transfer."
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='inward_id.company_id',
        store=True,
        readonly=True
    )

    @api.depends('inward_id.allocation_ids.slot_id', 'inward_id.allocation_ids.quantity')
    def _compute_allowed_from_slot_ids(self):
        for record in self:
            if record.inward_id:
                allocated_slots = record.inward_id.allocation_ids.filtered(lambda a: a.quantity > 0).mapped('slot_id')
                record.allowed_from_slot_ids = allocated_slots
            else:
                record.allowed_from_slot_ids = self.env['cold.storage.master.setup']

    @api.depends('from_slot_id', 'inward_id.allocation_ids.quantity', 'inward_id.allocation_ids.slot_id')
    def _compute_available_quantity(self):
        for record in self:
            if record.inward_id and record.from_slot_id:
                alloc = record.inward_id.allocation_ids.filtered(lambda a: a.slot_id == record.from_slot_id)
                record.available_quantity = sum(alloc.mapped('quantity'))
            else:
                record.available_quantity = 0

    @api.onchange('inward_id')
    def _onchange_inward_id(self):
        if self.inward_id:
            allocated_slot_ids = self.inward_id.allocation_ids.mapped('slot_id').ids
            return {'domain': {'from_slot_id': [('id', 'in', allocated_slot_ids)]}}
        return {'domain': {'from_slot_id': []}}

    @api.onchange('from_slot_id')
    def _onchange_from_slot_id(self):
        if self.inward_id and self.from_slot_id:
            alloc = self.inward_id.allocation_ids.filtered(lambda a: a.slot_id == self.from_slot_id)
            self.available_quantity = sum(alloc.mapped('quantity'))
        else:
            self.available_quantity = 0

    @api.constrains('from_slot_id', 'to_slot_id')
    def _check_slots(self):
        for record in self:
            if record.from_slot_id and record.to_slot_id and record.from_slot_id == record.to_slot_id:
                raise ValidationError(_("From Slot and To Slot cannot be the same!"))

    @api.constrains('quantity')
    def _check_quantity_positive(self):
        for record in self:
            if record.quantity <= 0:
                raise ValidationError(_("Transfer Quantity (Bosta) must be greater than zero."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('cold.storage.plotting') or _('New')
        records = super().create(vals_list)
        for record in records:
            record._sync_storage_allocation()
        return records

    def _sync_storage_allocation(self):
        self.ensure_one()
        inward = self.inward_id
        from_alloc = inward.allocation_ids.filtered(lambda a: a.slot_id == self.from_slot_id)
        if not from_alloc:
            raise ValidationError(
                _("From Slot '%s' is not currently allocated in this Inward Lot.") % (self.from_slot_id.name or '')
            )

        total_avail = sum(from_alloc.mapped('quantity'))
        if self.quantity > total_avail:
            raise ValidationError(_(
                "Transfer quantity (%(qty)s bosta) cannot exceed available quantity (%(avail)s bosta) in From Slot '%(slot)s'."
            ) % {
                'qty': self.quantity,
                'avail': total_avail,
                'slot': self.from_slot_id.name,
            })

        # Deduct from from_alloc lines
        qty_to_deduct = self.quantity
        for alloc in from_alloc:
            if alloc.quantity <= qty_to_deduct:
                qty_to_deduct -= alloc.quantity
                alloc.unlink()
            else:
                alloc.quantity -= qty_to_deduct
                qty_to_deduct = 0
                break

        # Add to to_slot_id line
        to_alloc = inward.allocation_ids.filtered(lambda a: a.slot_id == self.to_slot_id)
        if to_alloc:
            to_alloc[0].quantity += self.quantity
        else:
            self.env['cold.storage.inward.allocation'].create({
                'inward_id': inward.id,
                'slot_id': self.to_slot_id.id,
                'quantity': self.quantity,
            })
