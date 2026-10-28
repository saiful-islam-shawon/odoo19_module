# -*- coding: utf-8 -*-
from datetime import date, timedelta
from psycopg2 import IntegrityError
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError
from odoo.tools import mute_logger


class TestTeamsAndInward(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Employee = cls.env['hr.employee']
        cls.Team = cls.env['cold.storage.team']
        cls.Season = cls.env['cold.storage.season']
        cls.Partner = cls.env['res.partner']
        cls.Inward = cls.env['cold.storage.inward']
        cls.today = date.today()

        # Create test employees
        cls.emp_leader = cls.Employee.create({'name': 'Leader Rafiq'})
        cls.emp_member_1 = cls.Employee.create({'name': 'Staff Karim'})
        cls.emp_member_2 = cls.Employee.create({'name': 'Staff Hasan'})

        # Create customer
        cls.customer = cls.Partner.create({'name': 'Farmer Jamal'})

        # Create season
        cls.season = cls.Season.create({
            'name': 'Potato Season 2026',
            'date_start': cls.today,
            'date_end': cls.today + timedelta(days=120),
            'default_bag_rate': 125.00,
        })

    def test_01_create_team_with_leader_and_members(self):
        """Test operational team creation with leader and members from hr.employee."""
        team = self.Team.create({
            'name': 'Field Team Beta',
            'leader_id': self.emp_leader.id,
            'member_ids': [(6, 0, [self.emp_member_1.id, self.emp_member_2.id])],
        })
        self.assertEqual(team.leader_id, self.emp_leader)
        self.assertEqual(len(team.member_ids), 2)
        self.assertIn(self.emp_member_1, team.member_ids)
        self.assertTrue(team.active)

    def test_02_employee_multi_team_membership(self):
        """Test that an employee can belong to multiple cold storage teams."""
        team_a = self.Team.create({
            'name': 'Team Alpha',
            'member_ids': [(6, 0, [self.emp_member_1.id])],
        })
        team_b = self.Team.create({
            'name': 'Team Omega',
            'member_ids': [(6, 0, [self.emp_member_1.id])],
        })
        self.assertIn(self.emp_member_1, team_a.member_ids)
        self.assertIn(self.emp_member_1, team_b.member_ids)

    def test_03_create_inward_sequences_and_bag_rate(self):
        """Test Inward auto-generation of Lot number as primary name and bag rate."""
        inward = self.Inward.create({
            'partner_id': self.customer.id,
            'season_id': self.season.id,
            'product_name': 'Cardinal Potato',
            'bag_quantity': 250,
            'bag_rate': 125.00,
            'date_start': self.today,
            'date_end': self.today + timedelta(days=90),
        })
        # Verify lot number sequence
        self.assertTrue(inward.name.startswith('LOT/'))
        self.assertEqual(inward.lot_number, inward.name)
        self.assertEqual(inward.bag_quantity, 250)
        self.assertEqual(inward.bag_rate, 125.00)

    def test_04_inward_bag_rate_manual_override(self):
        """Test manual override of bag_rate persists."""
        inward = self.Inward.create({
            'partner_id': self.customer.id,
            'season_id': self.season.id,
            'product_name': 'Granola Seed',
            'bag_quantity': 100,
            'bag_rate': 110.00,  # Overridden from 125.00
            'date_start': self.today,
            'date_end': self.today + timedelta(days=60),
        })
        self.assertEqual(inward.bag_rate, 110.00)

    def test_05_inward_date_validation_constraint(self):
        """Test that date_end < date_start raises ValidationError."""
        with self.assertRaises(ValidationError):
            self.Inward.create({
                'partner_id': self.customer.id,
                'season_id': self.season.id,
                'product_name': 'Test Potato',
                'bag_quantity': 50,
                'date_start': self.today,
                'date_end': self.today - timedelta(days=1),
            })

    def test_06_inward_quantity_constraint(self):
        """Test that bag_quantity <= 0 raises ValidationError."""
        with self.assertRaises(ValidationError):
            self.Inward.create({
                'partner_id': self.customer.id,
                'season_id': self.season.id,
                'product_name': 'Test Potato',
                'bag_quantity': 0,
                'date_start': self.today,
                'date_end': self.today + timedelta(days=30),
            })

    def test_07_lot_uniqueness_constraint(self):
        """Test that duplicate lot numbers raise unique constraint error."""
        self.Inward.create({
            'partner_id': self.customer.id,
            'season_id': self.season.id,
            'product_name': 'Batch 1',
            'bag_quantity': 10,
            'name': 'LOT/MANUAL/001',
            'date_start': self.today,
            'date_end': self.today + timedelta(days=30),
        })
        other_customer = self.Partner.create({'name': 'Farmer Anwar'})
        with mute_logger('odoo.sql_db'):
            with self.assertRaises(Exception):
                with self.cr.savepoint():
                    self.Inward.create({
                        'partner_id': other_customer.id,
                        'season_id': self.season.id,
                        'product_name': 'Batch 2',
                        'bag_quantity': 20,
                        'name': 'LOT/MANUAL/001',  # Duplicate lot number
                        'date_start': self.today,
                        'date_end': self.today + timedelta(days=30),
                    })
