# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ZencoreSeedRetestScrapWizard(models.TransientModel):
    _name = 'zencore.seed.retest.scrap.wizard'
    _description = 'Retest Scrap Confirmation Wizard'

    retest_id = fields.Many2one(
        'zencore.seed.retest',
        string='Retest Evaluation',
        required=True,
        readonly=True,
        ondelete='cascade'
    )
    scrap_reason = fields.Text(
        string='Scrap Reason / Defect Justification',
        required=True,
        help="Specify the scientific or storage failure reasons for condemning this seed lot."
    )

    def action_confirm_scrap(self):
        self.ensure_one()
        if not self.scrap_reason or not self.scrap_reason.strip():
            raise ValidationError(_("Please provide a valid reason for scrapping this seed lot."))

        retest = self.retest_id
        if retest.state != 'draft':
            raise ValidationError(_("Only draft retests can be scrapped."))

        reason = self.scrap_reason.strip()

        # Update retest record
        retest.with_context(bypass_state_lock=True).write({
            'state': 'failed',
            'scrap_reason': reason,
            'evaluated_by_id': self.env.user.id,
            'date_evaluated': fields.Datetime.now(),
        })
        retest.message_post(
            body=_(
                "<b>Retest Failed &amp; Seed Scrapped</b><br/>"
                "<b>Reason:</b> %s<br/>"
                "<b>Evaluated By:</b> %s"
            ) % (reason, self.env.user.name),
            subtype_xmlid='mail.mt_note'
        )

        # Update cold storage record
        storage = retest.storage_id
        storage.with_context(bypass_state_lock=True).write({
            'state': 'scrapped',
        })
        storage.message_post(
            body=_(
                "<b>Seed Condemned &amp; Scrapped</b> following Retest failure (%s).<br/>"
                "<b>Reason:</b> %s<br/>"
                "<b>Authorized By:</b> %s"
            ) % (retest.name, reason, self.env.user.name),
            subtype_xmlid='mail.mt_note'
        )

        # Create isolated Cold Storage Scrap entry
        self.env['zencore.seed.cold.storage.scrap'].create({
            'storage_id': storage.id,
            'retest_id': retest.id,
            'product_id': retest.product_id.id,
            'lot_name': retest.lot_name,
            'lot_id': retest.lot_id.id if retest.lot_id else False,
            'category': retest.category,
            'pack_size': retest.pack_size,
            'bag_count': retest.bag_count,
            'quantity': retest.quantity,
            'storage_date': retest.storage_date,
            'validity_date': retest.validity_date,
            'scrap_date': fields.Datetime.now(),
            'scrapped_by_id': self.env.user.id,
            'scrap_reason': reason,
            'company_id': retest.company_id.id,
        })

        return {'type': 'ir.actions.act_window_close'}

