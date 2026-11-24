from odoo.tests.common import TransactionCase

from odoo.addons.zsl_vat.models.mushak_report import REPORT_XMLIDS


class TestOfficialMushakReports(TransactionCase):
    """Each statutory form must use Odoo's native QWeb report engine."""

    def test_all_statutory_qweb_reports_exist(self):
        for form_code, xmlid in REPORT_XMLIDS.items():
            report = self.env.ref(xmlid)
            self.assertEqual(report.report_type, 'qweb-pdf', form_code)
            self.assertTrue(report.report_name, form_code)

    def test_tr6_uses_qweb_report_action(self):
        payment = self.env['vat.treasury.payment'].create({
            'company_id': self.env.company.id,
            'challan_number': 'TR6-TEST-001',
            'amount': 1250.0,
            'bank': 'Bangladesh Bank',
        })
        action = payment.action_print_treasury_challan()
        self.assertEqual(action['type'], 'ir.actions.report')
        self.assertEqual(action['report_name'], 'zsl_vat.report_tr6')
