# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import ValidationError


@tagged('post_install', '-at_install')
class TestSeedLabTest(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Partner = cls.env['res.partner']
        cls.Product = cls.env['product.product']
        cls.SeedReceipt = cls.env['zencore.seed.receipt']
        cls.SeedLabTest = cls.env['zencore.seed.lab.test']
        cls.LabTestLine = cls.env['zencore.seed.lab.test.line']
        cls.LabRejectWizard = cls.env['zencore.seed.lab.test.reject.wizard']

        cls.vendor = cls.Partner.create({
            'name': 'Northern Seed Grower Laboratory Test',
        })
        cls.seed_product = cls.Product.create({
            'name': 'Hybrid Rice Lab Batch-01',
            'type': 'consu',
        })

        # Create a passed seed receipt
        cls.receipt_passed = cls.SeedReceipt.create({
            'partner_id': cls.vendor.id,
            'product_id': cls.seed_product.id,
            'variety': 'BR-29 Hybrid',
            'challan_no': 'CHAL-LAB-001',
            'bag_count': 100,
            'challan_weight': 5000.0,
            'received_weight': 4980.0,
        })
        cls.receipt_passed.action_send_to_testing()
        cls.receipt_passed.action_approve()
        assert cls.receipt_passed.state == 'passed'

    def test_01_lab_test_defaults_and_passed_receipt_linkage(self):
        """Test lab test initialization, auto-populated header, sequence, and default parameter lines."""
        # Use default_get like form view does
        fields_list = ['receipt_id', 'line_ids', 'date_test', 'name', 'state']
        defaults = self.SeedLabTest.default_get(fields_list)
        defaults.update({
            'receipt_id': self.receipt_passed.id,
            'sample_id': 'SAMPLE-BOT-101',
        })
        lab_test = self.SeedLabTest.create(defaults)

        self.assertEqual(lab_test.state, 'draft', "Initial state must be draft.")
        self.assertTrue(lab_test.name.startswith('QC/LAB/'), "Sequence must start with QC/LAB/.")
        self.assertEqual(lab_test.partner_id, self.vendor)
        self.assertEqual(lab_test.product_id, self.seed_product)
        self.assertEqual(lab_test.variety, 'BR-29 Hybrid')
        self.assertEqual(lab_test.challan_no, 'CHAL-LAB-001')
        self.assertEqual(lab_test.received_weight, 4980.0)
        self.assertEqual(lab_test.bag_count, 100)

        # Verify 6 default parameter lines
        param_names = lab_test.line_ids.mapped('parameter_name')
        self.assertIn('Moisture', param_names)
        self.assertIn('Physical Purity', param_names)
        self.assertIn('Germination', param_names)
        self.assertIn('Genetic Purity', param_names)
        self.assertIn('Inert Matter', param_names)
        self.assertIn('Other Crop Seed', param_names)
        self.assertEqual(len(lab_test.line_ids), 6, "Must contain 6 default test parameters.")
        for line in lab_test.line_ids:
            self.assertEqual(line.result, 'pending', "Default line status must be pending.")
            self.assertFalse(line.measured_value, "Default line measured value must be blank.")

    def test_02_dynamic_lines_addition_and_removal(self):
        """Test adding custom parameter line and deleting lines in draft state."""
        lab_test = self.SeedLabTest.create({
            'receipt_id': self.receipt_passed.id,
            'sample_id': 'SAMPLE-BOT-102',
            'line_ids': [
                (0, 0, {'parameter_name': 'Moisture', 'unit': '%', 'standard_value': 'Max 12.0%', 'measured_value': '11.2', 'result': 'pass'}),
            ]
        })
        self.assertEqual(len(lab_test.line_ids), 1)

        # Add custom parameter line
        self.LabTestLine.create({
            'test_id': lab_test.id,
            'parameter_name': 'Oil Content',
            'unit': '%',
            'standard_value': 'Min 40.0%',
            'measured_value': '42.5',
            'result': 'pass',
        })
        self.assertEqual(len(lab_test.line_ids), 2)
        self.assertIn('Oil Content', lab_test.line_ids.mapped('parameter_name'))

        # Delete first line
        lab_test.line_ids[0].unlink()
        self.assertEqual(len(lab_test.line_ids), 1)
        self.assertEqual(lab_test.line_ids[0].parameter_name, 'Oil Content')

    def test_03_three_tier_approval_lifecycle(self):
        """Test 3-tier lifecycle: Technician submit -> Checker verify -> Approver approve."""
        lab_test = self.SeedLabTest.create({
            'receipt_id': self.receipt_passed.id,
            'sample_id': 'SAMPLE-BOT-103',
            'line_ids': [
                (0, 0, {'parameter_name': 'Germination', 'unit': '%', 'standard_value': 'Min 85.0%', 'measured_value': '92.0', 'result': 'pass'}),
            ]
        })

        # 1. Technician Submits
        lab_test.action_submit()
        self.assertEqual(lab_test.state, 'to_verify')
        self.assertEqual(lab_test.submitted_by_id, self.env.user)
        self.assertTrue(lab_test.date_submitted)

        # Locked from editing parameters while under review
        with self.assertRaises(ValidationError):
            lab_test.write({'sample_id': 'TAMPERED-SAMPLE'})

        # 2. Checker Verifies
        lab_test.action_verify()
        self.assertEqual(lab_test.state, 'to_approve')
        self.assertEqual(lab_test.verified_by_id, self.env.user)
        self.assertTrue(lab_test.date_verified)

        # 3. GM / Approver Approves
        lab_test.action_approve()
        self.assertEqual(lab_test.state, 'approved')
        self.assertEqual(lab_test.approved_by_id, self.env.user)
        self.assertTrue(lab_test.date_approved)

        # Terminal state permanently locked
        with self.assertRaises(ValidationError):
            lab_test.write({'overall_notes': 'Modifying after approved'})

    def test_04_return_to_draft_retesting_loop(self):
        """Test that Checker and Approver can return to draft for re-testing."""
        lab_test = self.SeedLabTest.create({
            'receipt_id': self.receipt_passed.id,
            'sample_id': 'SAMPLE-BOT-104',
            'line_ids': [
                (0, 0, {'parameter_name': 'Moisture', 'unit': '%', 'standard_value': 'Max 12.0%', 'measured_value': '13.5', 'result': 'fail'}),
            ]
        })
        lab_test.action_submit()
        self.assertEqual(lab_test.state, 'to_verify')

        # Checker returns to draft
        lab_test.action_return_to_draft()
        self.assertEqual(lab_test.state, 'draft')

        # Technician modifies and resubmits
        lab_test.line_ids[0].write({'measured_value': '11.8', 'result': 'pass'})
        lab_test.action_submit()
        lab_test.action_verify()
        self.assertEqual(lab_test.state, 'to_approve')

        # Approver also returns to draft for verification
        lab_test.action_return_to_draft()
        self.assertEqual(lab_test.state, 'draft')

    def test_05_lab_rejection_wizard_workflow(self):
        """Test rejection wizard validation, reason recording, and terminal locking."""
        lab_test = self.SeedLabTest.create({
            'receipt_id': self.receipt_passed.id,
            'sample_id': 'SAMPLE-BOT-105',
            'line_ids': [
                (0, 0, {'parameter_name': 'Germination', 'unit': '%', 'standard_value': 'Min 80.0%', 'measured_value': '52.0', 'result': 'fail'}),
            ]
        })
        lab_test.action_submit()

        # Blank rejection reason raises ValidationError
        wizard_blank = self.LabRejectWizard.create({
            'test_id': lab_test.id,
            'rejection_reason': '   ',
        })
        with self.assertRaises(ValidationError):
            wizard_blank.action_confirm_reject()

        # Valid rejection succeeds
        wizard = self.LabRejectWizard.create({
            'test_id': lab_test.id,
            'rejection_reason': 'Germination is 52% which fails minimum 80% standard.',
        })
        wizard.action_confirm_reject()

        self.assertEqual(lab_test.state, 'rejected')
        self.assertEqual(lab_test.rejection_reason, 'Germination is 52% which fails minimum 80% standard.')
        self.assertEqual(lab_test.rejected_by_id, self.env.user)
        self.assertTrue(lab_test.date_rejected)

        # Permanent lock on rejected record
        with self.assertRaises(ValidationError):
            lab_test.write({'sample_id': 'SHOULD-FAIL'})

    def test_06_receipt_smart_button_integration(self):
        """Test smart button on seed receipt reflects linked lab test count and action."""
        initial_count = self.receipt_passed.lab_test_count
        test = self.SeedLabTest.create({
            'receipt_id': self.receipt_passed.id,
            'sample_id': 'SAMPLE-BOT-106',
            'line_ids': [
                (0, 0, {'parameter_name': 'Moisture', 'unit': '%', 'standard_value': 'Max 12.0%', 'measured_value': '11.0', 'result': 'pass'}),
            ]
        })
        self.receipt_passed.invalidate_recordset(['lab_test_count'])
        self.assertEqual(self.receipt_passed.lab_test_count, initial_count + 1)

        action = self.receipt_passed.action_view_lab_tests()
        self.assertEqual(action['res_model'], 'zencore.seed.lab.test')
        self.assertEqual(action['domain'], [('receipt_id', '=', self.receipt_passed.id)])

    def test_07_strict_role_based_permissions(self):
        """Test that only users with the specific role group can submit, verify, or approve."""
        User = self.env['res.users']
        tech_group = self.env.ref('zencore_quality_check.group_zencore_quality_technician')
        checker_group = self.env.ref('zencore_quality_check.group_zencore_quality_checker')
        approver_group = self.env.ref('zencore_quality_check.group_zencore_quality_approver')

        tech_user = User.create({
            'name': 'QC Technician User',
            'login': 'qc_tech_user_test',
            'group_ids': [(6, 0, [tech_group.id, self.env.ref('base.group_user').id])],
        })
        checker_user = User.create({
            'name': 'QC Checker User',
            'login': 'qc_checker_user_test',
            'group_ids': [(6, 0, [checker_group.id, self.env.ref('base.group_user').id])],
        })
        approver_user = User.create({
            'name': 'QC Approver User',
            'login': 'qc_approver_user_test',
            'group_ids': [(6, 0, [approver_group.id, self.env.ref('base.group_user').id])],
        })
        plain_user = User.create({
            'name': 'Plain User',
            'login': 'plain_user_test',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
        })

        lab_test = self.SeedLabTest.create({
            'receipt_id': self.receipt_passed.id,
            'sample_id': 'SAMPLE-ROLE-TEST',
            'line_ids': [
                (0, 0, {'parameter_name': 'Germination', 'unit': '%', 'standard_value': 'Min 80%', 'measured_value': '88', 'result': 'pass'}),
            ]
        })

        # Plain user cannot submit
        with self.assertRaises(ValidationError):
            lab_test.with_user(plain_user).action_submit()

        # Checker cannot submit
        with self.assertRaises(ValidationError):
            lab_test.with_user(checker_user).action_submit()

        # Tech user can submit
        lab_test.with_user(tech_user).action_submit()
        self.assertEqual(lab_test.state, 'to_verify')
        self.assertEqual(lab_test.submitted_by_id, tech_user)

        # Tech user cannot verify
        with self.assertRaises(ValidationError):
            lab_test.with_user(tech_user).action_verify()

        # Approver cannot verify
        with self.assertRaises(ValidationError):
            lab_test.with_user(approver_user).action_verify()

        # Checker user can verify
        lab_test.with_user(checker_user).action_verify()
        self.assertEqual(lab_test.state, 'to_approve')
        self.assertEqual(lab_test.verified_by_id, checker_user)

        # Checker user cannot approve
        with self.assertRaises(ValidationError):
            lab_test.with_user(checker_user).action_approve()

        # Approver user can approve
        lab_test.with_user(approver_user).action_approve()
        self.assertEqual(lab_test.state, 'approved')
        self.assertEqual(lab_test.approved_by_id, approver_user)

