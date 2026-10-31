# -*- coding: utf-8 -*-
from datetime import date, timedelta
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError
from .common import setup_test_accounting


class TestSeasonWorkflow(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Season = cls.env['cold.storage.season']
        cls.today = date.today()
        cls.acc_setup = setup_test_accounting(cls.env)

    def test_01_create_season_success(self):
        """Test successful season creation in draft state."""
        team = self.env['cold.storage.team'].create({'name': 'Operations Team Alpha'})
        season = self.Season.create({
            'name': 'Potato Season 2026-27',
            'date_start': self.today,
            'date_end': self.today + timedelta(days=180),
            'default_bag_rate': 120.50,
            'team_id': team.id,
            'season_manager': 'Manager Rahim',
        })
        self.assertEqual(season.state, 'draft')
        self.assertEqual(season.default_bag_rate, 120.50)
        self.assertEqual(season.team_id, team)

    def test_02_date_validation_constraint(self):
        """Test that date_end < date_start raises ValidationError."""
        with self.assertRaises(ValidationError):
            self.Season.create({
                'name': 'Invalid Season Dates',
                'date_start': self.today,
                'date_end': self.today - timedelta(days=5),
            })

    def test_03_negative_bag_rate_constraint(self):
        """Test that negative default_bag_rate raises ValidationError."""
        with self.assertRaises(ValidationError):
            self.Season.create({
                'name': 'Invalid Bag Rate',
                'date_start': self.today,
                'date_end': self.today + timedelta(days=30),
                'default_bag_rate': -10.0,
            })

    def test_04_state_transitions(self):
        """Test draft -> open -> closed -> draft transitions."""
        season = self.Season.create({
            'name': 'State Test Season',
            'date_start': self.today,
            'date_end': self.today + timedelta(days=60),
        })
        self.assertEqual(season.state, 'draft')

        # Open season
        season.action_open()
        self.assertEqual(season.state, 'open')

        # Close season
        season.action_close()
        self.assertEqual(season.state, 'closed')

        # Reset to draft
        season.action_reset_draft()
        self.assertEqual(season.state, 'draft')

    def test_05_season_inward_linkage_and_kpis(self):
        """Test inward_ids linkage, KPI aggregation, and release_status computation."""
        customer = self.env['res.partner'].create({'name': 'Farmer Motaleb'})
        season = self.Season.create({
            'name': 'Potato Season 2026-B',
            'date_start': self.today,
            'date_end': self.today + timedelta(days=90),
            'default_bag_rate': 60.0,
        })
        season.action_open()

        # Create 2 inward lots under this season
        inward_1 = self.env['cold.storage.inward'].create({
            'partner_id': customer.id,
            'season_id': season.id,
            'product_name': 'Diamond Potato',
            'bag_quantity': 40,
            'date_start': self.today,
            'date_end': self.today + timedelta(days=60),
        })
        inward_2 = self.env['cold.storage.inward'].create({
            'partner_id': customer.id,
            'season_id': season.id,
            'product_name': 'Cardinal Potato',
            'bag_quantity': 60,
            'date_start': self.today,
            'date_end': self.today + timedelta(days=60),
        })

        # Test linkage & KPIs
        self.assertEqual(len(season.inward_ids), 2)
        self.assertEqual(season.total_inward_count, 2)
        self.assertEqual(season.total_received_bags, 100)
        self.assertEqual(season.total_released_bags, 0)
        self.assertEqual(season.total_remaining_bags, 100)

        # Inward statuses
        self.assertEqual(inward_1.release_status, 'unreleased')
        self.assertEqual(inward_1.payment_status, 'no_invoice')
        self.assertEqual(inward_1.due_amount, 0.0)

    def test_06_close_season_blocked_when_bags_unreleased(self):
        """Test that action_close() is blocked when any inward lot has remaining bags."""
        customer = self.env['res.partner'].create({'name': 'Farmer Kashem'})
        season = self.Season.create({
            'name': 'Season Clearance Block Test',
            'date_start': self.today,
            'date_end': self.today + timedelta(days=90),
        })
        season.action_open()

        inward = self.env['cold.storage.inward'].create({
            'partner_id': customer.id,
            'season_id': season.id,
            'product_name': 'Seed Potato',
            'bag_quantity': 30,
            'date_start': self.today,
            'date_end': self.today + timedelta(days=60),
        })

        self.assertEqual(inward.remaining_quantity, 30)

        # Attempt to close season must raise ValidationError
        with self.assertRaises(ValidationError) as cm:
            season.action_close()

        self.assertIn("still 30 unreleased bag(s) in storage", str(cm.exception))
        self.assertEqual(season.state, 'open')

    def test_07_close_season_allowed_when_all_bags_released(self):
        """Test that action_close() succeeds when all inward lots are fully released."""
        customer = self.env['res.partner'].create({'name': 'Farmer Jahangir'})
        setup_test_accounting(self.env, customer)
        season = self.Season.create({
            'name': 'Season Complete Release Test',
            'date_start': self.today,
            'date_end': self.today + timedelta(days=90),
            'default_bag_rate': 50.0,
        })
        season.action_open()

        # Slot master setup
        chamber = self.env['cold.storage.chamber'].create({'name': 'Chamber S1'})
        floor = self.env['cold.storage.floor'].create({'name': 'Floor S1'})
        line = self.env['cold.storage.line'].create({'name': 'Line S1'})
        pocket = self.env['cold.storage.pocket'].create({'name': 'Pocket S1'})
        slot = self.env['cold.storage.master.setup'].create({
            'chamber_id': chamber.id,
            'floor_id': floor.id,
            'line_id': line.id,
            'pocket_id': pocket.id,
            'activate': True,
        })

        inward = self.env['cold.storage.inward'].create({
            'partner_id': customer.id,
            'season_id': season.id,
            'product_name': 'Red Potato',
            'bag_quantity': 10,
            'bag_rate': 50.0,
            'date_start': self.today,
            'date_end': self.today + timedelta(days=60),
            'allocation_ids': [(0, 0, {'slot_id': slot.id, 'quantity': 10})],
        })

        # Release all 10 bags via release wizard
        journal = self.acc_setup['cash_journal']
        wizard = self.env['cold.storage.inward.release.wizard'].with_context(
            default_inward_id=inward.id
        ).create({
            'inward_id': inward.id,
            'receiver_name': 'Driver Joynal',
        })
        wizard.line_ids.filtered(lambda l: l.slot_id == slot).quantity = 10
        wizard.action_confirm_release()

        self.assertEqual(inward.released_quantity, 10)
        self.assertEqual(inward.remaining_quantity, 0)
        self.assertEqual(inward.release_status, 'full')
        self.assertEqual(inward.payment_status, 'due')  # unpaid due
        self.assertEqual(inward.due_amount, 500.0)

        # Under Option A, physical clearance permits season close even with due amount
        season.action_close()
        self.assertEqual(season.state, 'closed')
        self.assertEqual(season.total_remaining_bags, 0)
        self.assertEqual(season.total_released_bags, 10)
        self.assertEqual(season.total_due_amount, 500.0)

