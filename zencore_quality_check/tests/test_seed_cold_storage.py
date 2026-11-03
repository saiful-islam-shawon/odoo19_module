# -*- coding: utf-8 -*-
from datetime import timedelta
from odoo import fields
from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import ValidationError, UserError


@tagged('post_install', '-at_install')
class TestSeedColdStorage(TransactionCase):

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
        cls.ColdStorage = cls.env['zencore.seed.cold.storage']
        cls.Retest = cls.env['zencore.seed.retest']
        cls.Scrap = cls.env['zencore.seed.cold.storage.scrap']
        cls.ScrapWizard = cls.env['zencore.seed.retest.scrap.wizard']

        cls.vendor = cls.Partner.create({'name': 'Northern Agro Farms'})
        cls.raw_seed = cls.Product.create({'name': 'Raw Mustard Seed', 'type': 'consu'})
        cls.finished_seed = cls.Product.create({'name': 'Mustard Grade A Special', 'type': 'consu'})

    def _create_approved_qc(self, suffix='01'):
        receipt = self.SeedReceipt.create({
            'partner_id': self.vendor.id,
            'product_id': self.raw_seed.id,
            'variety': 'Tori-7 High Yield',
            'challan_no': f'CHAL-MSTD-{suffix}',
            'bag_count': 30,
            'challan_weight': 1500.0,
            'received_weight': 1500.0,
        })
        receipt.action_send_to_testing()
        receipt.action_approve()

        lab_test = self.SeedLabTest.create({
            'receipt_id': receipt.id,
            'sample_id': f'LAB-MSTD-{suffix}',
        })
        lab_test.action_submit()
        lab_test.action_verify()
        lab_test.action_approve()

        batch = self.ProcessingBatch.create({'lab_test_id': lab_test.id})
        batch.action_start_drying()
        batch.action_proceed_grading()

        self.OutputLine.create({
            'batch_id': batch.id,
            'product_id': self.finished_seed.id,
            'category': 'good',
            'pack_size': '10 Kg',
            'bag_count': 50,
            'quantity': 500.0,
        })
        batch.action_proceed_packing()
        batch.action_mark_done()
        batch.action_send_to_qc()

        qc = self.ProcessedSeedQc.search([('batch_id', '=', batch.id)], limit=1)
        return qc

    def test_01_send_to_cold_storage_state_gating_and_creation(self):
        qc = self._create_approved_qc('01')
        self.assertEqual(qc.state, 'draft')

        # Draft QC cannot be sent to cold storage
        with self.assertRaises(UserError):
            qc.action_send_to_cold_storage()

        # Approve QC
        qc.action_approve()
        self.assertEqual(qc.state, 'approved')
        self.assertFalse(qc.is_cold_storage_sent)

        # Dispatch to cold storage
        qc.action_send_to_cold_storage()
        self.assertTrue(qc.is_cold_storage_sent)

        # Retrieve created cold storage record
        storage = self.ColdStorage.search([('qc_id', '=', qc.id)])
        self.assertEqual(len(storage), 1)
        self.assertEqual(storage.state, 'stored')
        self.assertTrue(storage.name.startswith('CS/'))
        self.assertEqual(storage.product_id, self.finished_seed)
        self.assertEqual(storage.bag_count, 50)
        self.assertEqual(storage.quantity, 500.0)
        self.assertTrue(bool(storage.lot_name))

        # Duplicate dispatch blocked
        with self.assertRaises(UserError):
            qc.action_send_to_cold_storage()

    def test_02_direct_release_within_validity(self):
        qc = self._create_approved_qc('02')
        qc.action_approve()
        qc.action_send_to_cold_storage()

        storage = self.ColdStorage.search([('qc_id', '=', qc.id)], limit=1)
        today = fields.Date.context_today(self)

        # Release without validity date fails
        with self.assertRaises(ValidationError):
            storage.action_release()

        # Set valid future validity date (30 days from today)
        storage.validity_date = today + timedelta(days=30)
        storage.invalidate_recordset(['validity_status'])
        self.assertEqual(storage.validity_status, 'valid')

        # Release succeeds
        storage.action_release()
        self.assertEqual(storage.state, 'released')
        self.assertEqual(storage.released_by_id, self.env.user)
        self.assertTrue(bool(storage.released_date))

        # Immutability
        with self.assertRaises(UserError):
            storage.write({'notes': 'Unauthorized modification'})

    def test_03_release_blocked_when_validity_expired(self):
        qc = self._create_approved_qc('03')
        qc.action_approve()
        qc.action_send_to_cold_storage()

        storage = self.ColdStorage.search([('qc_id', '=', qc.id)], limit=1)
        today = fields.Date.context_today(self)

        # Set expired past validity date (10 days ago)
        storage.validity_date = today - timedelta(days=10)
        storage.invalidate_recordset(['validity_status'])
        self.assertEqual(storage.validity_status, 'expired')

        # Direct release must be blocked
        with self.assertRaises(UserError):
            storage.action_release()

    def test_04_send_for_retest_and_passed_release(self):
        qc = self._create_approved_qc('04')
        qc.action_approve()
        qc.action_send_to_cold_storage()

        storage = self.ColdStorage.search([('qc_id', '=', qc.id)], limit=1)
        today = fields.Date.context_today(self)
        storage.validity_date = today - timedelta(days=5)
        storage.invalidate_recordset(['validity_status'])

        # Dispatch for retest
        storage.action_send_for_retest()
        self.assertEqual(storage.state, 'under_retest')
        self.assertTrue(bool(storage.retest_id))

        retest = storage.retest_id
        self.assertEqual(retest.state, 'draft')
        self.assertEqual(len(retest.line_ids), 4)

        # Retest passes -> releases cold storage
        retest.action_release()
        self.assertEqual(retest.state, 'passed')
        self.assertEqual(storage.state, 'released')
        self.assertEqual(storage.released_by_id, self.env.user)

    def test_05_retest_failed_scrap_workflow_and_scrap_registry(self):
        qc = self._create_approved_qc('05')
        qc.action_approve()
        qc.action_send_to_cold_storage()

        storage = self.ColdStorage.search([('qc_id', '=', qc.id)], limit=1)
        today = fields.Date.context_today(self)
        storage.validity_date = today - timedelta(days=15)
        storage.invalidate_recordset(['validity_status'])

        storage.action_send_for_retest()
        retest = storage.retest_id

        # Retest failed -> Scrap wizard
        wizard = self.ScrapWizard.create({
            'retest_id': retest.id,
            'scrap_reason': 'Severe germination decay to 35% after long cold storage.',
        })
        wizard.action_confirm_scrap()

        self.assertEqual(retest.state, 'failed')
        self.assertEqual(storage.state, 'scrapped')

        # Check isolated scrap registry
        scrap = self.Scrap.search([('storage_id', '=', storage.id)])
        self.assertEqual(len(scrap), 1)
        self.assertTrue(scrap.name.startswith('SCRAP/'))
        self.assertEqual(scrap.product_id, self.finished_seed)
        self.assertEqual(scrap.quantity, 500.0)
        self.assertIn('Severe germination decay', scrap.scrap_reason)

        # Scrap record cannot be modified or deleted
        with self.assertRaises(UserError):
            scrap.write({'scrap_reason': 'Altered'})
        with self.assertRaises(UserError):
            scrap.unlink()

