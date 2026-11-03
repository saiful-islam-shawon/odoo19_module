# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import ValidationError, UserError


@tagged('post_install', '-at_install')
class TestSeedProcessingBatch(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Partner = cls.env['res.partner']
        cls.Product = cls.env['product.product']
        cls.SeedReceipt = cls.env['zencore.seed.receipt']
        cls.SeedLabTest = cls.env['zencore.seed.lab.test']
        cls.ProcessingBatch = cls.env['zencore.seed.processing.batch']
        cls.OutputLine = cls.env['zencore.seed.processing.output.line']

        cls.vendor = cls.Partner.create({
            'name': 'Green Agro Growers Ltd',
        })
        cls.raw_seed = cls.Product.create({
            'name': 'Raw Paddy Seed',
            'type': 'consu',
        })
        cls.grade_a_product = cls.Product.create({
            'name': 'Processed Paddy Grade A',
            'type': 'consu',
        })
        cls.grade_b_product = cls.Product.create({
            'name': 'Processed Paddy Grade B',
            'type': 'consu',
        })
        cls.waste_product = cls.Product.create({
            'name': 'Paddy Waste & Husk',
            'type': 'consu',
        })

    def _create_approved_lab_test(self, suffix='01'):
        receipt = self.SeedReceipt.create({
            'partner_id': self.vendor.id,
            'product_id': self.raw_seed.id,
            'variety': 'BR-28 Supreme',
            'challan_no': f'CHAL-GAPL-{suffix}',
            'bag_count': 50,
            'challan_weight': 2500.0,
            'received_weight': 2490.0,
        })
        receipt.action_send_to_testing()
        receipt.action_approve()

        lab_test = self.SeedLabTest.create({
            'receipt_id': receipt.id,
            'sample_id': f'LAB-SMP-{suffix}',
        })
        lab_test.action_submit()
        lab_test.action_verify()
        lab_test.action_approve()
        return lab_test

    def test_01_processing_batch_creation_and_auto_population(self):
        """Verify processing batch sequence generation, defaults, and auto-populated linkage."""
        lab_test = self._create_approved_lab_test('T1')
        batch = self.ProcessingBatch.create({
            'lab_test_id': lab_test.id,
        })

        self.assertEqual(batch.state, 'draft', "Initial batch state must be 'draft'.")
        self.assertTrue(batch.name.startswith('PB/'), "Sequence must begin with 'PB/'.")
        self.assertEqual(batch.raw_product_id, self.raw_seed)
        self.assertEqual(batch.variety, 'BR-28 Supreme')
        self.assertEqual(batch.partner_id, self.vendor)
        self.assertEqual(batch.input_weight, 2490.0)
        self.assertEqual(batch.input_bags, 50)
        self.assertEqual(batch.receipt_id, lab_test.receipt_id)
        self.assertTrue(lab_test.is_processed, "Lab test must be marked as processed.")
        self.assertEqual(lab_test.processing_batch_id, batch)

    def test_02_duplicate_prevention_1_to_1(self):
        """Verify that an approved lab test cannot be linked to more than one processing batch."""
        lab_test = self._create_approved_lab_test('T2')
        batch1 = self.ProcessingBatch.create({
            'lab_test_id': lab_test.id,
        })

        with self.assertRaises(ValidationError):
            self.ProcessingBatch.create({
                'lab_test_id': lab_test.id,
            })

        # Test cancellation release
        batch1.action_cancel()
        self.assertEqual(batch1.state, 'cancelled')
        self.assertFalse(lab_test.is_processed, "Cancelled batch must release the lab test.")

        # Now creating a new batch should succeed
        batch2 = self.ProcessingBatch.create({
            'lab_test_id': lab_test.id,
        })
        self.assertEqual(batch2.state, 'draft')
        self.assertEqual(lab_test.processing_batch_id, batch2)

    def test_03_stage_lifecycle_and_drying_parameters(self):
        """Test statusbar transitions (Draft -> Drying -> Grading -> Packing -> Done) and drying computes."""
        lab_test = self._create_approved_lab_test('T3')
        batch = self.ProcessingBatch.create({
            'lab_test_id': lab_test.id,
        })

        # Transition to Drying
        batch.action_start_drying()
        self.assertEqual(batch.state, 'drying')
        self.assertTrue(batch.drying_start)

        batch.write({
            'initial_moisture': 16.5,
            'final_moisture': 11.0,
            'drying_method': 'mechanical',
            'drying_temp': 45.0,
            'weight_after_drying': 2400.0,
        })
        self.assertEqual(batch.moisture_loss, 90.0, "Moisture loss should be 2490 - 2400 = 90.0 kg.")

        # Transition to Grading
        batch.action_proceed_grading()
        self.assertEqual(batch.state, 'grading')
        self.assertTrue(batch.drying_end)

        # Transition to Packing
        batch.action_proceed_packing()
        self.assertEqual(batch.state, 'packing')

        # Transition to Done
        batch.action_mark_done()
        self.assertEqual(batch.state, 'done')

    def test_04_multi_product_grading_and_format1_auto_lot(self):
        """Test multi-product grading lines, Format 1 lot numbering (LOT/YYYY/00001), and smart totals."""
        lab_test = self._create_approved_lab_test('T4')
        batch = self.ProcessingBatch.create({
            'lab_test_id': lab_test.id,
        })
        batch.action_start_drying()
        batch.action_proceed_grading()

        # Add 3 distinct output lines (Grade A, Grade B, Waste)
        line1 = self.OutputLine.create({
            'batch_id': batch.id,
            'product_id': self.grade_a_product.id,
            'category': 'good',
            'pack_size': '20 Kg Bag',
            'bag_count': 80,
            'quantity': 1600.0,
        })
        line2 = self.OutputLine.create({
            'batch_id': batch.id,
            'product_id': self.grade_b_product.id,
            'category': 'by_product',
            'pack_size': '20 Kg Bag',
            'bag_count': 20,
            'quantity': 400.0,
        })
        line3 = self.OutputLine.create({
            'batch_id': batch.id,
            'product_id': self.waste_product.id,
            'category': 'waste',
            'quantity': 50.0,
        })

        # Verify Format 1 Lot Numbering (starts with LOT/)
        self.assertTrue(line1.lot_name.startswith('LOT/'), "Line 1 Lot must follow Format 1.")
        self.assertTrue(line2.lot_name.startswith('LOT/'), "Line 2 Lot must follow Format 1.")
        self.assertTrue(line3.lot_name.startswith('LOT/'), "Line 3 Lot must follow Format 1.")
        self.assertNotEqual(line1.lot_name, line2.lot_name, "Lot numbers must be unique.")
        self.assertNotEqual(line2.lot_name, line3.lot_name, "Lot numbers must be unique.")

        # Verify Stock Lot linkage
        self.assertTrue(line1.lot_id, "Stock lot record must be created and linked.")
        self.assertEqual(line1.lot_id.name, line1.lot_name)
        self.assertEqual(line1.lot_id.product_id, self.grade_a_product)

        # Verify Header Aggregates & Smart Buttons
        batch.invalidate_recordset()
        self.assertEqual(batch.output_lot_count, 2, "Produced lots count must be 2 (excluding waste).")
        self.assertEqual(batch.total_good_weight, 2000.0, "Good yield weight must match.")
        self.assertEqual(batch.total_good_bags, 100, "Good yield bag count must match.")
        self.assertEqual(batch.total_waste_weight, 50.0, "Waste weight must match.")

        # Test drill-down actions
        lots_action = batch.action_view_lots()
        self.assertEqual(lots_action['res_model'], 'zencore.seed.processing.output.line')
        self.assertEqual(lots_action['domain'], [('batch_id', '=', batch.id), ('category', '!=', 'waste')])

        waste_action = batch.action_view_waste()
        self.assertEqual(waste_action['res_model'], 'zencore.seed.processing.output.line')
        self.assertEqual(waste_action['domain'], [('batch_id', '=', batch.id), ('category', '=', 'waste')])

        good_action = batch.action_view_good_yield()
        self.assertEqual(good_action['res_model'], 'zencore.seed.processing.output.line')
        self.assertEqual(good_action['domain'], [('batch_id', '=', batch.id), ('category', 'in', ['good', 'bad', 'by_product'])])

    def test_05_immutability_on_done(self):
        """Test that once marked as Done, batch and lines cannot be modified or deleted."""
        lab_test = self._create_approved_lab_test('T5')
        batch = self.ProcessingBatch.create({
            'lab_test_id': lab_test.id,
        })
        batch.action_start_drying()
        batch.action_proceed_grading()
        line = self.OutputLine.create({
            'batch_id': batch.id,
            'product_id': self.grade_a_product.id,
            'category': 'good',
            'quantity': 100.0,
        })
        batch.action_proceed_packing()
        batch.action_mark_done()

        # Batch modification should fail
        with self.assertRaises(UserError):
            batch.write({'notes': 'Tampering with notes'})

        # Batch deletion should fail
        with self.assertRaises(UserError):
            batch.unlink()

        # Line modification should fail
        with self.assertRaises(UserError):
            line.write({'quantity': 200.0})

        # Line deletion should fail
        with self.assertRaises(UserError):
            line.unlink()
