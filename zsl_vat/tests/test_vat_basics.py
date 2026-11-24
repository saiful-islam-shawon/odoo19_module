from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestVatBasics(TransactionCase):
    def test_company_invalid_bin(self):
        with self.assertRaises(ValidationError):
            self.env.company.write({'vat_bin': '123'})

    def test_company_valid_bin(self):
        self.env.company.write({'vat_bin': '1234567890123'})
        self.assertEqual(self.env.company.vat_bin, '1234567890123')

    def test_due_day_validation(self):
        with self.assertRaises(ValidationError):
            self.env.company.write({'vat_return_due_day': 31})

    def test_document_series_model_present(self):
        self.assertIn('vat.document.series', self.env.registry)

    def test_vat_return_model_present(self):
        self.assertIn('vat.return', self.env.registry)

    def test_treasury_non_positive_payment_blocked(self):
        from odoo.exceptions import ValidationError
        payment = self.env['vat.treasury.payment'].create({
            'company_id': self.env.company.id,
            'challan_number': 'TEST-ZERO-PAYMENT',
            'amount': 0,
        })
        with self.assertRaises(ValidationError):
            payment.action_confirm()
