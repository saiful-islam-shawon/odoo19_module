# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ZencoreSeedReceiptRejectWizard(models.TransientModel):
    _name = 'zencore.seed.receipt.reject.wizard'
    _description = 'Reject Seed Receipt Wizard'

    receipt_id = fields.Many2one(
        'zencore.seed.receipt',
        string='Seed Receipt',
        required=True,
        readonly=True,
        ondelete='cascade',
        help="Seed receipt record being rejected."
    )
    rejection_reason = fields.Text(
        string='Rejection Reason',
        required=True,
        help="Specify the clear justification for rejecting this seed consignment."
    )

    def action_confirm_reject(self):
        self.ensure_one()
        if not self.rejection_reason or not self.rejection_reason.strip():
            raise ValidationError(_("Please provide a valid rejection reason."))

        receipt = self.receipt_id
        receipt.with_context(bypass_state_lock=True).write({
            'state': 'rejected',
            'rejection_reason': self.rejection_reason.strip(),
            'rejected_by_id': self.env.user.id,
            'rejection_date': fields.Datetime.now(),
        })
        receipt.message_post(
            body=_(
                "<b>Consignment Rejected</b><br/>"
                "<b>Reason:</b> %s<br/>"
                "<b>Rejected By:</b> %s"
            ) % (
                self.rejection_reason.strip(),
                self.env.user.name
            ),
            subtype_xmlid='mail.mt_note'
        )
        return {'type': 'ir.actions.act_window_close'}
