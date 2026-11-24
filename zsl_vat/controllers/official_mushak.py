from odoo import http
from odoo.http import content_disposition, request
from werkzeug.exceptions import NotFound

from odoo.addons.zsl_vat.models.official_mushak_pdf import FORM_FILES


class OfficialMushakController(http.Controller):
    """Serve official prescribed forms only to users entitled to the record."""

    _models = {
        '2.1': 'vat.registration.application', '2.3': 'vat.registration.certificate',
        '4.3': 'vat.io.coefficient',
        '6.1': 'vat.book.wizard', '6.2': 'vat.book.wizard', '6.10': 'vat.book.wizard',
        '6.3': 'account.move', '6.7': 'account.move', '6.8': 'account.move',
        '6.4': 'stock.picking', '6.5': 'stock.picking', '6.6': 'vat.vds.certificate',
        '6.2.1': 'vat.stock.register', '9.1': 'vat.return', '9.2': 'vat.return',
        'tr6': 'vat.treasury.payment',
    }

    @http.route('/zsl_vat/official-mushak/<string:form_code>/<string:model>/<int:record_id>', type='http', auth='user')
    def official_mushak(self, form_code, model, record_id, **kwargs):
        if form_code not in FORM_FILES or self._models.get(form_code) != model:
            raise NotFound()
        records = request.env[model].browse(record_id).exists()
        if not records:
            raise NotFound()
        records.check_access_rights('read')
        records.check_access_rule('read')
        payload = request.env['zsl_vat.official.mushak.pdf'].render_pdf(form_code, records)
        if not payload:
            raise NotFound()
        filename = 'Mushak_%s_%s.pdf' % (form_code.replace('.', '_'), records.display_name.replace('/', '_'))
        return request.make_response(payload, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Disposition', content_disposition(filename)),
        ])
