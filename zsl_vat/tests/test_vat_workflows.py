from datetime import date

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestVatWorkflows(TransactionCase):
    """Regression coverage for the SRS workflows added beyond the basic checks."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env['res.partner'].create({'name': 'VAT Workflow Customer'})
        cls.service = cls.env['product.product'].create({
            'name': 'VAT Workflow Service', 'type': 'service', 'list_price': 1000.0,
        })
        cls.period = cls.env['vat.period'].create({
            'company_id': cls.company.id,
            'date_start': date(2026, 1, 1),
            'date_end': date(2026, 1, 31),
        })
        cls.unit = cls.env['vat.unit'].create({
            'name': 'VAT Workflow Unit', 'code': 'VAT-WORKFLOW',
            'company_id': cls.company.id, 'registration_scope': 'sub_location',
            'address': 'Test address',
        })

    def test_cross_application_models_and_fields_exist(self):
        for model in (
            'vat.account.mapping', 'vat.reconciliation', 'vat.input.apportionment',
            'vat.production.valuation', 'vat.service.plan', 'vat.timesheet.billing',
            'vat.nbr.connector', 'vat.compliance.checklist',
        ):
            self.assertIn(model, self.env.registry)
        self.assertIn('vat_mushak_number', self.env['pos.order']._fields)
        self.assertIn('vat_timesheet_billing_id', self.env['account.analytic.line']._fields)

    def test_recurring_service_plan_creates_draft_vat_invoice(self):
        plan = self.env['vat.service.plan'].create({
            'name': 'January service plan', 'partner_id': self.partner.id,
            'product_id': self.service.id, 'quantity': 2,
            'price_unit': 750, 'start_date': date(2026, 1, 1),
            'next_invoice_date': date(2026, 1, 31),
        })
        plan.action_activate()
        action = plan.action_create_invoice()
        invoice = self.env['account.move'].browse(action['domain'][0][2][0])
        self.assertEqual(invoice.move_type, 'out_invoice')
        self.assertEqual(invoice.vat_service_plan_id, plan)
        self.assertEqual(invoice.vat_supply_stage, 'periodic')
        self.assertEqual(invoice.amount_untaxed, 1500)
        self.assertEqual(plan.next_invoice_date, date(2026, 2, 28))

    def test_custom_input_tax_apportionment_percentage(self):
        record = self.env['vat.input.apportionment'].create({
            'company_id': self.company.id, 'period_id': self.period.id,
            'method': 'custom', 'approved_percent': 65,
        })
        self.assertEqual(record.eligible_percent, 65)
        record.action_calculate()
        self.assertEqual(record.state, 'calculated')

    def test_nbr_payload_is_created_for_approved_return(self):
        vat_return = self.env['vat.return'].create({
            'company_id': self.company.id, 'period_id': self.period.id,
        })
        vat_return.write({'state': 'approved'})
        vat_return.action_prepare_nbr_payload()
        self.assertEqual(vat_return.nbr_submission_status, 'prepared')
        self.assertIn('Mushak 9.1', vat_return.nbr_submission_payload)

    def test_compliance_checklist_requires_evidence(self):
        checklist = self.env['vat.compliance.checklist'].create({
            'company_id': self.company.id,
            'line_ids': [(0, 0, {
                'requirement_code': 'FR-76', 'requirement': 'NBR payload and acknowledgement',
                'status': 'passed', 'evidence_note': 'Automated regression test',
            })],
        })
        checklist.action_evaluate()
        self.assertEqual(checklist.state, 'passed')

    def test_issued_invoice_is_immutable_and_cancellation_is_approved(self):
        income_account = self.env['account.account'].search([
            ('company_ids', 'in', self.company.id), ('account_type', '=', 'income'),
        ], limit=1)
        self.assertTrue(income_account, 'The test company needs an income account.')
        self.service.product_tmpl_id.property_account_income_id = income_account
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.partner.id,
            'invoice_date': date(2026, 1, 15),
            'invoice_line_ids': [(0, 0, {
                'product_id': self.service.id, 'name': self.service.name,
                'quantity': 1, 'price_unit': 1000, 'account_id': income_account.id,
            })],
        })
        invoice.action_post()
        self.assertEqual(invoice.vat_taxable_amount, 1000)
        self.assertFalse(invoice.vat_is_high_value)
        mushak_number = invoice.vat_mushak_number
        self.assertTrue(mushak_number)
        self.assertTrue(invoice.vat_qr_payload)
        with self.assertRaises(UserError):
            invoice.write({'invoice_date': date(2026, 1, 16)})
        with self.assertRaises(UserError):
            invoice.invoice_line_ids.write({'price_unit': 900})
        with self.assertRaises(UserError):
            invoice.unlink()
        with self.assertRaises(UserError):
            invoice.button_cancel()
        invoice.write({'vat_cancellation_reason': 'Duplicate invoice issued.'})
        invoice.button_cancel()
        self.assertEqual(invoice.vat_cancellation_state, 'requested')
        manager = self.env.ref('base.user_admin')
        invoice.with_user(manager).action_approve_vat_cancellation()
        self.assertEqual(invoice.state, 'cancel')
        self.assertEqual(invoice.vat_cancellation_state, 'approved')
        self.assertEqual(invoice.vat_mushak_number, mushak_number)

    def test_locked_vat_records_cannot_be_edited_or_deleted(self):
        coefficient = self.env['vat.io.coefficient'].create({
            'product_tmpl_id': self.service.product_tmpl_id.id,
        })
        manager = self.env.ref('base.user_admin')
        coefficient.with_user(manager).action_approve()
        with self.assertRaises(UserError):
            coefficient.write({'value_addition': 10})
        with self.assertRaises(UserError):
            coefficient.unlink()

        opening = self.env['vat.stock.opening'].create({
            'company_id': self.company.id, 'unit_id': self.unit.id,
            'product_id': self.service.id, 'effective_date': date(2026, 1, 1),
            'quantity': 1, 'value': 100, 'source_reference': 'Opening test',
        })
        opening.with_user(manager).action_approve()
        with self.assertRaises(UserError):
            opening.write({'quantity': 2})
        with self.assertRaises(UserError):
            opening.unlink()

        vat_return = self.env['vat.return'].create({
            'company_id': self.company.id, 'period_id': self.period.id,
            'nbr_acknowledgement': 'TEST-ACK-001',
        })
        vat_return.write({'state': 'approved'})
        vat_return.with_user(manager).action_submit()
        with self.assertRaises(UserError):
            vat_return.write({'opening_balance': 50})
        with self.assertRaises(UserError):
            vat_return.unlink()
