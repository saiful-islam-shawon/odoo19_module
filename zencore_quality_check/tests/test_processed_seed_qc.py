# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import ValidationError, UserError


@tagged('post_install', '-at_install')
class TestProcessedSeedQc(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Partner = cls.env['res.partner']
        cls.Product = cls.env['product.product']
        cls.SeedReceipt = cls.env['zencore.seed.receipt']
        cls.SeedLabTest = cls.env['zencore.seed.lab.test']
        cls.ProcessingBatch = cls.env['zencore.seed.processing.batch']
        cls.OutputLine = cls.env['zencore.seed.processing.output.line']
        cls.ProcessedSeedQc = cls.env['zencore.processed.seed.qc']
        cls.RejectWizard = cls.env['zencore.processed.seed.qc.reject.wizard']

        cls.vendor = cls.Partner.create({'name': 'Golden Harvest Agrico'})
        cls.raw_seed = cls.Product.create({'name': 'Raw Wheat Seed', 'type': 'consu'})
        cls.grade_a = cls.Product.create({'name': 'Wheat Grade A Certified', 'type': 'consu'})
        cls.grade_b = cls.Product.create({'name': 'Wheat Grade B Certified', 'type': 'consu'})
        cls.waste_prod = cls.Product.create({'name': 'Wheat Husks / Waste', 'type': 'consu'})

    def _create_done_batch(self, suffix='01'):
        receipt = self.SeedReceipt.create({
            'partner_id': self.vendor.id,
            'product_id': self.raw_seed.id,
            'variety': 'BARI Gom-33',
            'challan_no': f'CHAL-WHT-{suffix}',
            'bag_count': 60,
            'challan_weight': 3000.0,
            'received_weight': 2990.0,
        })
        receipt.action_send_to_testing()
        receipt.action_approve()

        lab_test = self.SeedLabTest.create({
            'receipt_id': receipt.id,
            'sample_id': f'LAB-WHT-{suffix}',
        })
        lab_test.action_submit()
        lab_test.action_verify()
        lab_test.action_approve()

        batch = self.ProcessingBatch.create({
            'lab_test_id': lab_test.id,
        })
        batch.action_start_drying()
        batch.action_proceed_grading()

        # Add 1 good, 1 bad, 1 waste line
        self.OutputLine.create({
            'batch_id': batch.id,
            'product_id': self.grade_a.id,
            'category': 'good',
            'pack_size': '20 Kg',
            'bag_count': 100,
            'quantity': 2000.0,
        })
        self.OutputLine.create({
            'batch_id': batch.id,
            'product_id': self.grade_b.id,
            'category': 'bad',
            'pack_size': '20 Kg',
            'bag_count': 40,
            'quantity': 800.0,
        })
        self.OutputLine.create({
            'batch_id': batch.id,
            'product_id': self.waste_prod.id,
            'category': 'waste',
            'pack_size': 'Bulk',
            'bag_count': 5,
            'quantity': 100.0,
        })
        batch.action_proceed_packing()
        batch.action_mark_done()
        return batch

    def test_01_send_to_qc_button_state_gating(self):
        receipt = self.SeedReceipt.create({
            'partner_id': self.vendor.id,
            'product_id': self.raw_seed.id,
            'variety': 'BARI Gom-33',
            'challan_no': 'CHAL-GATING-01',
            'bag_count': 20,
            'challan_weight': 1000.0,
            'received_weight': 1000.0,
        })
        receipt.action_send_to_testing()
        receipt.action_approve()

        lab_test = self.SeedLabTest.create({
            'receipt_id': receipt.id,
            'sample_id': 'LAB-GATING-01',
        })
        lab_test.action_submit()
        lab_test.action_verify()
        lab_test.action_approve()

        batch = self.ProcessingBatch.create({'lab_test_id': lab_test.id})
        with self.assertRaises(UserError):
            batch.action_send_to_qc()

        batch.action_start_drying()
        with self.assertRaises(UserError):
            batch.action_send_to_qc()

        batch.action_proceed_grading()
        with self.assertRaises(UserError):
            batch.action_send_to_qc()

    def test_02_waste_exclusion_and_granular_qc_records(self):
        batch = self._create_done_batch('02')
        self.assertEqual(batch.state, 'done')
        self.assertFalse(batch.is_qc_sent)
        self.assertEqual(len(batch.output_line_ids), 3)

        action = batch.action_send_to_qc()
        self.assertTrue(batch.is_qc_sent)

        # Retrieve created QC records
        qc_records = self.ProcessedSeedQc.search([('batch_id', '=', batch.id)])
        # Must be exactly 2 (Grade A and Grade B), waste line excluded
        self.assertEqual(len(qc_records), 2)
        categories = qc_records.mapped('category')
        self.assertIn('good', categories)
        self.assertIn('bad', categories)
        self.assertNotIn('waste', categories)

        # Duplicate send must be blocked
        with self.assertRaises(UserError):
            batch.action_send_to_qc()

    def test_03_auto_populated_traceability_and_default_parameters(self):
        batch = self._create_done_batch('03')
        batch.action_send_to_qc()

        qc_records = self.ProcessedSeedQc.search([('batch_id', '=', batch.id)])
        for qc in qc_records:
            self.assertTrue(qc.name.startswith('QC/PS/'))
            self.assertEqual(qc.state, 'draft')
            self.assertEqual(qc.batch_id, batch)
            self.assertEqual(qc.partner_id, self.vendor)
            self.assertEqual(qc.raw_product_id, self.raw_seed)
            self.assertEqual(qc.variety, 'BARI Gom-33')
            self.assertTrue(bool(qc.lot_name))
            self.assertTrue(bool(qc.lot_id))

            # Verify standard parameters loaded
            param_names = qc.line_ids.mapped('parameter_name')
            self.assertIn('Moisture Content', param_names)
            self.assertIn('Germination Rate', param_names)
            self.assertIn('Physical Purity', param_names)
            self.assertIn('Genetic Purity', param_names)

    def test_04_approval_lifecycle_and_immutability(self):
        batch = self._create_done_batch('04')
        batch.action_send_to_qc()

        qc = self.ProcessedSeedQc.search([('batch_id', '=', batch.id)], limit=1)
        self.assertEqual(qc.state, 'draft')

        # Approve
        qc.action_approve()
        self.assertEqual(qc.state, 'approved')
        self.assertEqual(qc.approved_by_id, self.env.user)
        self.assertTrue(bool(qc.date_approved))

        # Locked against edits
        with self.assertRaises(UserError):
            qc.write({'notes': 'Unauthorized modification after approval'})

    def test_05_rejection_wizard_workflow(self):
        batch = self._create_done_batch('05')
        batch.action_send_to_qc()

        qc = self.ProcessedSeedQc.search([('batch_id', '=', batch.id)], limit=1)
        wizard = self.RejectWizard.create({
            'qc_id': qc.id,
            'rejection_reason': 'Germination rate only 62% - below standard target.',
        })
        wizard.action_confirm_reject()

        self.assertEqual(qc.state, 'rejected')
        self.assertEqual(qc.rejected_by_id, self.env.user)
        self.assertIn('below standard target', qc.rejection_reason)

        # Locked against edits
        with self.assertRaises(UserError):
            qc.write({'notes': 'Editing rejected record'})

    def test_06_return_to_draft_reset(self):
        batch = self._create_done_batch('06')
        batch.action_send_to_qc()

        qc = self.ProcessedSeedQc.search([('batch_id', '=', batch.id)], limit=1)
        qc.action_approve()
        self.assertEqual(qc.state, 'approved')

        # Reset to draft
        qc.action_return_to_draft()
        self.assertEqual(qc.state, 'draft')
        self.assertFalse(qc.approved_by_id)
        self.assertFalse(qc.date_approved)

