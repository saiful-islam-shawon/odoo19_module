# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ColdStorageInwardReleaseWizard(models.TransientModel):
    _name = 'cold.storage.inward.release.wizard'
    _description = 'Cold Storage Inward Product Release Wizard'

    inward_id = fields.Many2one(
        'cold.storage.inward',
        string='Inward Lot',
        required=True
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        related='inward_id.partner_id',
        readonly=True
    )
    date = fields.Date(
        string='Release Date',
        required=True,
        default=fields.Date.context_today
    )
    receiver_name = fields.Char(
        string='Receiver / Delivered To',
        required=True,
        help="Person taking delivery of the bags."
    )
    vehicle_no = fields.Char(
        string='Vehicle / Gate Pass No',
        help="Truck plate number or gate pass reference."
    )
    notes = fields.Text(
        string='Remarks / Notes'
    )
    line_ids = fields.One2many(
        'cold.storage.inward.release.wizard.line',
        'wizard_id',
        string='Slot Breakdown'
    )
    total_release_quantity = fields.Integer(
        string='Total Released Bags',
        compute='_compute_totals'
    )
    bag_rate = fields.Float(
        string='Bag Rate',
        related='inward_id.bag_rate',
        readonly=True
    )
    total_amount = fields.Float(
        string='Total Charge',
        compute='_compute_totals'
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        inward_id = self.env.context.get('default_inward_id') or res.get('inward_id')
        if inward_id:
            inward = self.env['cold.storage.inward'].browse(inward_id)
            res['inward_id'] = inward.id
            lines = []
            for alloc in inward.allocation_ids.filtered(lambda a: a.quantity > 0):
                lines.append((0, 0, {
                    'slot_id': alloc.slot_id.id,
                    'available_quantity': alloc.quantity,
                    'quantity': 0,
                }))
            res['line_ids'] = lines
        return res

    @api.depends('line_ids.quantity', 'bag_rate')
    def _compute_totals(self):
        for record in self:
            total_qty = sum(record.line_ids.mapped('quantity'))
            record.total_release_quantity = total_qty
            record.total_amount = total_qty * (record.bag_rate or 0.0)

    def action_confirm_release(self):
        self.ensure_one()
        inward = self.inward_id
        if self.total_release_quantity <= 0:
            raise ValidationError(_("Please specify a release quantity greater than 0 for at least one slot."))

        # Validate line quantities and deduct from inward.allocation_ids
        release_lines_vals = []
        for line in self.line_ids:
            if line.quantity < 0:
                raise ValidationError(_("Release quantity cannot be negative for Slot '%s'.") % line.slot_id.name)
            if line.quantity > line.available_quantity:
                raise ValidationError(_(
                    "Release quantity (%(qty)s bags) cannot exceed available quantity (%(avail)s bags) in Slot '%(slot)s'."
                ) % {
                    'qty': line.quantity,
                    'avail': line.available_quantity,
                    'slot': line.slot_id.name,
                })
            if line.quantity > 0:
                alloc = inward.allocation_ids.filtered(lambda a: a.slot_id == line.slot_id)
                if not alloc:
                    raise ValidationError(_("Slot '%s' is no longer allocated to this lot.") % line.slot_id.name)

                qty_to_deduct = line.quantity
                for a in alloc:
                    if a.quantity <= qty_to_deduct:
                        qty_to_deduct -= a.quantity
                        a.unlink()
                        if qty_to_deduct == 0:
                            break
                    else:
                        a.quantity -= qty_to_deduct
                        qty_to_deduct = 0
                        break

                release_lines_vals.append((0, 0, {
                    'slot_id': line.slot_id.id,
                    'quantity': line.quantity,
                }))

        # Create persistent release record
        release = self.env['cold.storage.inward.release'].create({
            'inward_id': inward.id,
            'date': self.date,
            'receiver_name': self.receiver_name,
            'vehicle_no': self.vehicle_no,
            'notes': self.notes,
            'quantity': self.total_release_quantity,
            'bag_rate': self.bag_rate,
            'total_amount': self.total_amount,
            'line_ids': release_lines_vals,
        })

        # Create Draft Customer Invoice (account.move)
        move_vals = {
            'move_type': 'out_invoice',
            'partner_id': inward.partner_id.id,
            'invoice_date': self.date,
            'ref': f"Release {release.name} - Lot {inward.name}",
            'invoice_line_ids': [(0, 0, {
                'name': f"Cold Storage Service Charge - Lot {inward.name} ({self.total_release_quantity} Bags @ {self.bag_rate:.2f})",
                'quantity': self.total_release_quantity,
                'price_unit': self.bag_rate,
            })],
        }
        if inward.company_id:
            move_vals['company_id'] = inward.company_id.id

        move = self.env['account.move'].create(move_vals)
        release.move_id = move.id

        # Close wizard and keep user on current Inward form
        return {'type': 'ir.actions.act_window_close'}


class ColdStorageInwardReleaseWizardLine(models.TransientModel):
    _name = 'cold.storage.inward.release.wizard.line'
    _description = 'Cold Storage Inward Release Wizard Slot Line'

    wizard_id = fields.Many2one(
        'cold.storage.inward.release.wizard',
        required=True,
        ondelete='cascade'
    )
    slot_id = fields.Many2one(
        'cold.storage.master.setup',
        string='Storage Slot',
        required=True
    )
    available_quantity = fields.Integer(
        string='Available in Slot'
    )
    quantity = fields.Integer(
        string='Quantity to Release',
        default=0
    )
