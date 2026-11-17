from collections import OrderedDict

from odoo import models


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _render_qweb_pdf_prepare_streams(self, report_ref, data, res_ids=None):
        """Render Systech batch prints one record at a time.

        The Qt 5 renderer used to match the approved invoice design does not
        support multiple input HTML documents. Rendering each move separately
        also gives Odoo an unambiguous stream for invoices spanning many pages.
        """
        report = self._get_report(report_ref)
        is_systech_invoice = (
            report.report_name == 'systech_report.report_invoice_document_top'
        )
        unique_res_ids = list(dict.fromkeys(res_ids or []))

        if is_systech_invoice and len(unique_res_ids) > 1:
            streams = OrderedDict()
            for res_id in unique_res_ids:
                record_streams = super()._render_qweb_pdf_prepare_streams(
                    report_ref,
                    dict(data or {}),
                    res_ids=[res_id],
                )
                streams.update(record_streams)
            return streams

        return super()._render_qweb_pdf_prepare_streams(
            report_ref,
            data,
            res_ids=res_ids,
        )
