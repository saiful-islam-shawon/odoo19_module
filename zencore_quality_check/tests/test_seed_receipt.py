# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import ValidationError


@tagged('post_install', '-at_install')
class TestSeedReceipt(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Partner = cls.env['res.partner']
        cls.Product = cls.env['product.product']
        cls.SeedReceipt = cls.env['zencore.seed.receipt']
        cls.RejectWizard = cls.env['zencore.seed.receipt.reject.wizard']

        cls.vendor = cls.Partner.create({
            'name': 'Bhaluka Seed Grower Test',
        })
        cls.seed_product = cls.Product.create({
            'name': 'Hybrid Rice Seed A-101',
            'type': 'consu',
        })

    def test_01_seed_receipt_creation_and_shortage_calculation(self):
        """Test receipt creation, auto sequence number, and shortage calculation."""
        receipt = self.SeedReceipt.create({
            'partner_id': self.vendor.id,
            'product_id': self.seed_product.id,
            'variety': 'BR-28 Hybrid',
            'challan_no': 'CHAL-2026-001',
            'challan_date': '2026-11-02',
            'vehicle_no': 'DHAKA-METRO-TA-1234',
            'bag_count': 50,
            'challan_weight': 2500.0,
            'received_weight': 2470.0,
        })
        self.assertEqual(receipt.state, 'draft', "Initial state must be draft.")
        self.assertTrue(receipt.name.startswith('QC/REC/'), "Sequence must start with QC/REC/")
        self.assertEqual(receipt.shortage_weight, 30.0, "Shortage must equal 2500 - 2470 = 30 kg.")

    def test_02_send_to_testing_and_receipt_immutability(self):
        """Test transitioning to testing and immutability of arrival fields."""
        receipt = self.SeedReceipt.create({
            'partner_id': self.vendor.id,
            'product_id': self.seed_product.id,
            'variety': 'Hybrid Gold',
            'challan_no': 'CHAL-2026-002',
            'bag_count': 20,
            'challan_weight': 1000.0,
            'received_weight': 1000.0,
        })
        receipt.action_send_to_testing()
        self.assertEqual(receipt.state, 'testing', "State must be 'testing'.")
        self.assertEqual(receipt.inspected_by_id, self.env.user, "Inspector defaults to current user.")
        self.assertTrue(receipt.inspection_date, "Inspection date must be recorded.")

        # Attempt to edit arrival field during testing should fail
        with self.assertRaises(ValidationError):
            receipt.write({'challan_weight': 1100.0})

        # But editing physical inspection fields during testing must succeed
        receipt.write({
            'damaged_bag_count': 2,
            'pest_infestation': 'none',
            'moisture_condition': 'normal',
            'label_condition': 'good',
            'inspection_notes': 'All bags inspected and healthy.',
        })
        self.assertEqual(receipt.damaged_bag_count, 2)

    def test_03_approval_and_terminal_lock(self):
        """Test approval transition and strict immutability in passed state."""
        receipt = self.SeedReceipt.create({
            'partner_id': self.vendor.id,
            'product_id': self.seed_product.id,
            'variety': 'Certified Aman',
            'challan_no': 'CHAL-2026-003',
            'bag_count': 10,
            'challan_weight': 500.0,
            'received_weight': 500.0,
        })
        # Approval directly from draft should fail
        with self.assertRaises(ValidationError):
            receipt.action_approve()

        receipt.action_send_to_testing()
        receipt.action_approve()
        self.assertEqual(receipt.state, 'passed', "State must be 'passed'.")

        # Modifying record in passed state must raise ValidationError
        with self.assertRaises(ValidationError):
            receipt.write({'damaged_bag_count': 5})

    def test_04_rejection_wizard_workflow(self):
        """Test rejection wizard validation, reason capture, and terminal locking."""
        receipt = self.SeedReceipt.create({
            'partner_id': self.vendor.id,
            'product_id': self.seed_product.id,
            'variety': 'Damaged Seed Lot',
            'challan_no': 'CHAL-2026-004',
            'bag_count': 30,
            'challan_weight': 1500.0,
            'received_weight': 1500.0,
        })
        receipt.action_send_to_testing()

        # 1. Blank rejection reason must fail
        wizard_empty = self.RejectWizard.create({
            'receipt_id': receipt.id,
            'rejection_reason': '   ',
        })
        with self.assertRaises(ValidationError):
            wizard_empty.action_confirm_reject()

        # 2. Valid rejection reason succeeds
        wizard = self.RejectWizard.create({
            'receipt_id': receipt.id,
            'rejection_reason': 'Observed live weevils and 8 torn bags.',
        })
        wizard.action_confirm_reject()

        self.assertEqual(receipt.state, 'rejected', "State must be 'rejected'.")
        self.assertEqual(receipt.rejection_reason, 'Observed live weevils and 8 torn bags.')
        self.assertEqual(receipt.rejected_by_id, self.env.user)
        self.assertTrue(receipt.rejection_date)

        # Modifying record in rejected state must raise ValidationError
        with self.assertRaises(ValidationError):
            receipt.write({'inspection_notes': 'Trying to edit rejected record.'})
