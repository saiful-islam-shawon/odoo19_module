# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ZencoreSeedLabTestRejectWizard(models.TransientModel):
    _name = 'zencore.seed.lab.test.reject.wizard'
    _description = 'Reject Lab Test Wizard'

    test_id = fields.Many2one(
        'zencore.seed.lab.test',
        string='Lab Test',
        required=True,
        readonly=True,
        ondelete='cascade',
        help="Lab test record being rejected."
    )
    rejection_reason = fields.Text(
        string='Rejection Reason',
        required=True,
        help="Specify the clear justification for rejecting this laboratory test."
    )

    def action_confirm_reject(self):
        self.ensure_one()
        if not self.rejection_reason or not self.rejection_reason.strip():
            raise ValidationError(_("Please provide a valid rejection reason."))

        test = self.test_id
        test.with_context(bypass_state_lock=True).write({
            'state': 'rejected',
            'rejection_reason': self.rejection_reason.strip(),
            'rejected_by_id': self.env.user.id,
            'date_rejected': fields.Datetime.now(),
        })
        test.message_post(
            body=_(
                "<b>Lab Test Rejected</b><br/>"
                "<b>Reason:</b> %s<br/>"
                "<b>Rejected By:</b> %s"
            ) % (
                self.rejection_reason.strip(),
                self.env.user.name
            ),
            subtype_xmlid='mail.mt_note'
        )
        return {'type': 'ir.actions.act_window_close'}
