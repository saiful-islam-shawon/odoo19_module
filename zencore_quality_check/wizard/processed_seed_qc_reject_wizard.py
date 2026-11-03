# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ZencoreProcessedSeedQcRejectWizard(models.TransientModel):
    _name = 'zencore.processed.seed.qc.reject.wizard'
    _description = 'Reject Processed Seed QC Wizard'

    qc_id = fields.Many2one(
        'zencore.processed.seed.qc',
        string='Processed Seed QC',
        required=True,
        readonly=True,
        ondelete='cascade',
        help="Processed seed QC record being rejected."
    )
    rejection_reason = fields.Text(
        string='Rejection Reason',
        required=True,
        help="Specify the clear scientific or quality reason for rejecting this seed lot."
    )

    def action_confirm_reject(self):
        self.ensure_one()
        if not self.rejection_reason or not self.rejection_reason.strip():
            raise ValidationError(_("Please provide a valid rejection reason."))

        qc = self.qc_id
        if qc.state != 'draft':
            raise ValidationError(_("Only draft QC tests can be rejected."))

        qc.with_context(bypass_state_lock=True).write({
            'state': 'rejected',
            'rejection_reason': self.rejection_reason.strip(),
            'rejected_by_id': self.env.user.id,
            'date_rejected': fields.Datetime.now(),
        })
        qc.message_post(
            body=_(
                "<b>Processed Seed QC Rejected</b><br/>"
                "<b>Reason:</b> %s<br/>"
                "<b>Rejected By:</b> %s"
            ) % (
                self.rejection_reason.strip(),
                self.env.user.name
            ),
            subtype_xmlid='mail.mt_note'
        )
        return {'type': 'ir.actions.act_window_close'}

