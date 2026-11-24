from odoo import _, api, fields, models
from odoo.exceptions import UserError
from .mushak_report import mushak_report_action


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    vat_unit_id = fields.Many2one('vat.unit', string='VAT Unit', domain="[('company_id', '=', company_id)]")
    vat_receiving_unit_id = fields.Many2one('vat.unit', string='Receiving VAT Unit', domain="[('company_id', '=', company_id)]")
    vat_invoice_id = fields.Many2one('account.move', string='Related VAT Invoice', domain="[('company_id', '=', company_id), ('move_type', '=', 'out_invoice'), ('state', '=', 'posted')]")
    vat_tax_document_id = fields.Many2one('account.move', string='Inter-unit Tax Document', domain="[('company_id', '=', company_id), ('state', '=', 'posted')]")
    vat_delivery_trip_no = fields.Integer(string='Delivery Trip No.', default=1)
    vat_delivery_confirmed = fields.Boolean(string='Delivery Confirmed', copy=False)
    vat_delivery_confirmation_date = fields.Datetime(string='Delivery Confirmation Date', copy=False)
    vat_delivery_receiver = fields.Char(string='Received By', copy=False)
    vat_delivery_evidence_id = fields.Many2one('ir.attachment', string='Delivery Evidence', copy=False, ondelete='restrict')
    vat_remarks = fields.Text(string='VAT Remarks')
    vat_transfer_value = fields.Monetary(compute='_compute_vat_transfer_amounts', currency_field='currency_id', string='Value Excl. Tax')
    vat_transfer_tax_amount = fields.Monetary(compute='_compute_vat_transfer_amounts', currency_field='currency_id', string='Applicable Tax')
    currency_id = fields.Many2one(related='company_id.currency_id')
    vat_challan_type = fields.Selection([
        ('delivery', 'Delivery Challan'),
        ('transfer', 'Mushak 6.5 Transfer Challan'),
        ('contract_send', 'Mushak 6.4 Contract Manufacturing Send'),
        ('contract_receive', 'Contract Manufacturing Receive'),
    ], string='VAT Challan Type')
    vat_challan_number = fields.Char(string='VAT Challan No.', readonly=True, copy=False)
    vat_challan_date = fields.Datetime(string='Challan Date', readonly=True)
    vat_adjustment_reason = fields.Text(string='Damage / Destruction Reason')

    def _suggest_vat_challan_type(self):
        self.ensure_one()
        if self.picking_type_id.code == 'internal':
            return 'transfer'
        if self.picking_type_id.code == 'outgoing':
            return 'delivery'
        return False

    @api.model_create_multi
    def create(self, vals_list):
        pickings = super().create(vals_list)
        for picking in pickings.filtered(lambda p: not p.vat_challan_type):
            picking.vat_challan_type = picking._suggest_vat_challan_type()
        return pickings

    @api.onchange('picking_type_id')
    def _onchange_picking_type_id_vat_challan(self):
        for picking in self:
            if picking.vat_challan_type not in ('contract_send', 'contract_receive'):
                picking.vat_challan_type = picking._suggest_vat_challan_type()

    # ``move_ids_without_package`` was removed from stock.picking in Odoo 19.
    # The picking's stock moves are exposed directly through ``move_ids``.
    @api.depends('move_ids.quantity', 'move_ids.product_id', 'vat_tax_document_id.amount_tax')
    def _compute_vat_transfer_amounts(self):
        for picking in self:
            picking.vat_transfer_value = sum(
                move.quantity * move.product_id.standard_price for move in picking.move_ids
            )
            picking.vat_transfer_tax_amount = picking.vat_tax_document_id.amount_tax if picking.vat_tax_document_id else 0.0

    def _check_vat_transfer_compliance(self):
        for picking in self.filtered(lambda record: record.vat_challan_type == 'transfer'):
            if not picking.vat_unit_id or not picking.vat_receiving_unit_id:
                raise UserError(_('Select both sending and receiving VAT units before validating a transfer challan.'))
            if picking.vat_unit_id == picking.vat_receiving_unit_id:
                raise UserError(_('Sending and receiving VAT units must be different.'))
            source_bin = picking.vat_unit_id.bin or picking.company_id.vat_bin
            destination_bin = picking.vat_receiving_unit_id.bin or picking.company_id.vat_bin
            if source_bin != destination_bin and not picking.vat_tax_document_id:
                raise UserError(_('A posted inter-unit tax document is required when the transfer is between separate BINs.'))

    def action_confirm_delivery(self):
        for picking in self:
            if picking.state != 'done' or picking.picking_type_id.code != 'outgoing':
                raise UserError(_('Only a completed outgoing delivery can be confirmed.'))
            picking.write({
                'vat_delivery_confirmed': True,
                'vat_delivery_confirmation_date': fields.Datetime.now(),
            })

    def button_validate(self):
        self._check_vat_transfer_compliance()
        for picking in self:
            traceable_moves = picking.move_ids.filtered(
                lambda move: move.product_id.product_tmpl_id.vat_traceability_required and move.quantity
            )
            missing_lots = traceable_moves.filtered(lambda move: not move.move_line_ids.mapped('lot_id'))
            if missing_lots:
                raise UserError(_(
                    'Assign a batch/lot or serial number before validating VAT-traceable goods: %s'
                ) % ', '.join(missing_lots.mapped('product_id.display_name')))
        result = super().button_validate()
        for picking in self.filtered(lambda p: p.state == 'done' and not p.vat_challan_number):
            if picking.vat_challan_type == 'transfer':
                picking.vat_challan_number = self.env['vat.document.series'].next_number(
                    '65', picking.company_id, picking.vat_unit_id, fields.Date.to_date(picking.date_done),
                )
            elif picking.vat_challan_type == 'contract_send':
                picking.vat_challan_number = self.env['vat.document.series'].next_number(
                    '64', picking.company_id, picking.vat_unit_id, fields.Date.to_date(picking.date_done),
                )
            elif picking.vat_challan_type == 'delivery':
                picking.vat_challan_number = self.env['ir.sequence'].next_by_code('stock.picking') or picking.name
            picking.vat_challan_date = fields.Datetime.now()
        return result

    def action_print_vat_challan(self):
        self.ensure_one()
        if not self.vat_challan_number:
            raise UserError(_('Validate the transfer/delivery before printing its VAT challan.'))
        form_code = '6.4' if self.vat_challan_type in ('contract_send', 'contract_receive') else '6.5'
        return mushak_report_action(self, form_code)

    def action_view_vat_traceability(self):
        """Show each delivered movement with its lot/serial and purchase-bill lineage."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('VAT Goods Traceability'),
            'res_model': 'stock.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.move_ids.ids)],
            'context': {'search_default_done': 1},
        }


class StockMove(models.Model):
    _inherit = 'stock.move'

    vat_trace_lot_ids = fields.Many2many('stock.lot', compute='_compute_vat_purchase_trace', string='Batch / Serial Numbers')
    vat_source_purchase_line_ids = fields.Many2many('purchase.order.line', compute='_compute_vat_purchase_trace', string='Source Purchase Lines')
    vat_source_vendor_bill_ids = fields.Many2many('account.move', compute='_compute_vat_purchase_trace', string='Source Vendor Bills')
    vat_currency_id = fields.Many2one(related='company_id.currency_id')
    vat_source_input_tax = fields.Monetary(compute='_compute_vat_purchase_trace', currency_field='vat_currency_id', string='Traceable Input VAT')

    def _compute_vat_purchase_trace(self):
        for move in self:
            to_visit = move
            visited = self.env['stock.move']
            purchase_lines = self.env['purchase.order.line']
            while to_visit:
                current = to_visit[:1]
                to_visit = to_visit[1:]
                if current in visited:
                    continue
                visited |= current
                purchase_lines |= current.purchase_line_id
                to_visit |= current.move_orig_ids
            bills = purchase_lines.mapped('invoice_lines.move_id').filtered(
                lambda bill: bill.move_type in ('in_invoice', 'in_refund') and bill.state == 'posted'
            )
            move.vat_trace_lot_ids = move.move_line_ids.mapped('lot_id')
            move.vat_source_purchase_line_ids = purchase_lines
            move.vat_source_vendor_bill_ids = bills
            move.vat_source_input_tax = sum(bills.mapped('vat_input_amount'))
