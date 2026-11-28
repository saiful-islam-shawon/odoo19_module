"""QWeb report actions for the Bangladesh VAT forms.

The reports are composed from the XML/QWeb templates in ``report/``.  No
pre-rendered PDF is used as a background; Odoo renders the prescribed layout
from the live record data.
"""

from odoo import models


REPORT_XMLIDS = {
    '2.1': 'zsl_vat.action_report_mushak_21',
    '2.3': 'zsl_vat.action_report_mushak_23',
    '4.3': 'zsl_vat.action_report_mushak_43',
    '4.4': 'zsl_vat.action_report_mushak_44',
    '4.5': 'zsl_vat.action_report_mushak_45',
    '6.1': 'zsl_vat.action_report_mushak_61',
    '6.2': 'zsl_vat.action_report_mushak_62',
    '6.2.1': 'zsl_vat.action_report_mushak_621',
    '6.3': 'zsl_vat.action_report_mushak_63',
    '6.4': 'zsl_vat.action_report_mushak_64',
    '6.5': 'zsl_vat.action_report_mushak_65',
    '6.6': 'zsl_vat.action_report_mushak_66',
    '6.7': 'zsl_vat.action_report_mushak_67',
    '6.8': 'zsl_vat.action_report_mushak_68',
    '6.10': 'zsl_vat.action_report_mushak_610',
    '9.1': 'zsl_vat.action_report_mushak_91',
    '9.2': 'zsl_vat.action_report_mushak_92',
    'tr6': 'zsl_vat.action_report_tr6',
}


def mushak_report_action(record, form_code, data=None):
    """Return Odoo's native QWeb report action for one statutory form."""
    record.ensure_one()
    return record.env.ref(REPORT_XMLIDS[form_code]).report_action(record, data=data)


class MushakReport(models.AbstractModel):
    _name = 'report.zsl_vat.mushak_report'
    _description = 'Bangladesh VAT QWeb Report Helper'
