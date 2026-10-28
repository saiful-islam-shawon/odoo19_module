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

    def test_08_storage_allocation_valid_and_partial(self):
        """Test valid full and partial storage allocation lines."""
        chamber = self.env['cold.storage.chamber'].create({'name': 'Chamber 1'})
        floor = self.env['cold.storage.floor'].create({'name': 'Floor 1'})
        line = self.env['cold.storage.line'].create({'name': 'Line 1'})
        pocket_a = self.env['cold.storage.pocket'].create({'name': 'Pocket A'})
        pocket_b = self.env['cold.storage.pocket'].create({'name': 'Pocket B'})

        slot_a = self.env['cold.storage.master.setup'].create({
            'chamber_id': chamber.id,
            'floor_id': floor.id,
            'line_id': line.id,
            'pocket_id': pocket_a.id,
            'activate': True,
        })
        slot_b = self.env['cold.storage.master.setup'].create({
            'chamber_id': chamber.id,
            'floor_id': floor.id,
            'line_id': line.id,
            'pocket_id': pocket_b.id,
            'activate': True,
        })

        inward = self.Inward.create({
            'partner_id': self.customer.id,
            'season_id': self.season.id,
            'product_name': 'Potato 10 Bosta',
            'bag_quantity': 20,
            'date_start': self.today,
            'date_end': self.today + timedelta(days=30),
            'allocation_ids': [
                (0, 0, {'slot_id': slot_a.id, 'quantity': 10}),
                (0, 0, {'slot_id': slot_b.id, 'quantity': 5}),
            ],
        })
        self.assertEqual(len(inward.allocation_ids), 2)
        total_allocated = sum(inward.allocation_ids.mapped('quantity'))
        self.assertEqual(total_allocated, 15)
        self.assertLessEqual(total_allocated, inward.bag_quantity)

        # Later, add another 5 bags to reach total 20
        inward.write({
            'allocation_ids': [(0, 0, {'slot_id': slot_a.id, 'quantity': 5})]
        })
        self.assertEqual(sum(inward.allocation_ids.mapped('quantity')), 20)

    def test_09_storage_allocation_exceeds_total_quantity(self):
        """Test that sum of allocated quantities exceeding bag_quantity raises ValidationError."""
        chamber = self.env['cold.storage.chamber'].create({'name': 'Chamber 2'})
        floor = self.env['cold.storage.floor'].create({'name': 'Floor 2'})
        line = self.env['cold.storage.line'].create({'name': 'Line 2'})
        pocket = self.env['cold.storage.pocket'].create({'name': 'Pocket C'})

        slot = self.env['cold.storage.master.setup'].create({
            'chamber_id': chamber.id,
            'floor_id': floor.id,
            'line_id': line.id,
            'pocket_id': pocket.id,
            'activate': True,
        })

        with self.assertRaises(ValidationError):
            self.Inward.create({
                'partner_id': self.customer.id,
                'season_id': self.season.id,
                'product_name': 'Overallocated Potato',
                'bag_quantity': 20,
                'date_start': self.today,
                'date_end': self.today + timedelta(days=30),
                'allocation_ids': [
                    (0, 0, {'slot_id': slot.id, 'quantity': 25}),  # 25 > 20
                ],
            })

    def test_10_storage_allocation_non_positive_quantity(self):
        """Test that allocation line quantity <= 0 raises ValidationError."""
        chamber = self.env['cold.storage.chamber'].create({'name': 'Chamber 3'})
        floor = self.env['cold.storage.floor'].create({'name': 'Floor 3'})
        line = self.env['cold.storage.line'].create({'name': 'Line 3'})
        pocket = self.env['cold.storage.pocket'].create({'name': 'Pocket D'})

        slot = self.env['cold.storage.master.setup'].create({
            'chamber_id': chamber.id,
            'floor_id': floor.id,
            'line_id': line.id,
            'pocket_id': pocket.id,
            'activate': True,
        })

        with self.assertRaises(ValidationError):
            self.Inward.create({
                'partner_id': self.customer.id,
                'season_id': self.season.id,
                'product_name': 'Zero Quantity Line',
                'bag_quantity': 20,
                'date_start': self.today,
                'date_end': self.today + timedelta(days=30),
                'allocation_ids': [
                    (0, 0, {'slot_id': slot.id, 'quantity': 0}),
                ],
            })

    def test_11_slot_plotting_success_and_auto_sync(self):
        """Test creating a plotting record reduces from_slot and increases to_slot."""
        chamber = self.env['cold.storage.chamber'].create({'name': 'Chamber 4'})
        floor = self.env['cold.storage.floor'].create({'name': 'Floor 4'})
        line = self.env['cold.storage.line'].create({'name': 'Line 4'})
        pocket_a = self.env['cold.storage.pocket'].create({'name': 'Pocket 4A'})
        pocket_b = self.env['cold.storage.pocket'].create({'name': 'Pocket 4B'})
        pocket_c = self.env['cold.storage.pocket'].create({'name': 'Pocket 4C'})

        slot_a = self.env['cold.storage.master.setup'].create({
            'chamber_id': chamber.id,
            'floor_id': floor.id,
            'line_id': line.id,
            'pocket_id': pocket_a.id,
            'activate': True,
        })
        slot_b = self.env['cold.storage.master.setup'].create({
            'chamber_id': chamber.id,
            'floor_id': floor.id,
            'line_id': line.id,
            'pocket_id': pocket_b.id,
            'activate': True,
        })
        slot_c = self.env['cold.storage.master.setup'].create({
            'chamber_id': chamber.id,
            'floor_id': floor.id,
            'line_id': line.id,
            'pocket_id': pocket_c.id,
            'activate': True,
        })

        inward = self.Inward.create({
            'partner_id': self.customer.id,
            'season_id': self.season.id,
            'product_name': 'Potato Batch 4',
            'bag_quantity': 20,
            'date_start': self.today,
            'date_end': self.today + timedelta(days=30),
            'allocation_ids': [
                (0, 0, {'slot_id': slot_a.id, 'quantity': 15}),
                (0, 0, {'slot_id': slot_b.id, 'quantity': 5}),
            ],
        })
        self.assertEqual(inward.plotting_count, 0)

        # Plot 10 bags from Slot A to Slot C
        plotting = self.env['cold.storage.inward.plotting'].create({
            'inward_id': inward.id,
            'from_slot_id': slot_a.id,
            'to_slot_id': slot_c.id,
            'quantity': 10,
        })
        self.assertTrue(plotting.name.startswith('PLT/'))
        self.assertEqual(inward.plotting_count, 1)

        # Check allocations in inward
        line_a = inward.allocation_ids.filtered(lambda a: a.slot_id == slot_a)
        line_b = inward.allocation_ids.filtered(lambda a: a.slot_id == slot_b)
        line_c = inward.allocation_ids.filtered(lambda a: a.slot_id == slot_c)

        self.assertEqual(line_a.quantity, 5)   # 15 - 10 = 5
        self.assertEqual(line_b.quantity, 5)   # untouched = 5
        self.assertEqual(line_c.quantity, 10)  # new = 10
        self.assertEqual(sum(inward.allocation_ids.mapped('quantity')), 20)

        # Smart button action check
        action = inward.action_view_plottings()
        self.assertEqual(action['res_model'], 'cold.storage.inward.plotting')
        self.assertEqual(action['domain'], [('inward_id', '=', inward.id)])

    def test_12_slot_plotting_complete_depletion(self):
        """Test moving all remaining quantity unlinks the source allocation line."""
        chamber = self.env['cold.storage.chamber'].create({'name': 'Chamber 5'})
        floor = self.env['cold.storage.floor'].create({'name': 'Floor 5'})
        line = self.env['cold.storage.line'].create({'name': 'Line 5'})
        pocket_a = self.env['cold.storage.pocket'].create({'name': 'Pocket 5A'})
        pocket_b = self.env['cold.storage.pocket'].create({'name': 'Pocket 5B'})

        slot_a = self.env['cold.storage.master.setup'].create({
            'chamber_id': chamber.id,
            'floor_id': floor.id,
            'line_id': line.id,
            'pocket_id': pocket_a.id,
            'activate': True,
        })
        slot_b = self.env['cold.storage.master.setup'].create({
            'chamber_id': chamber.id,
            'floor_id': floor.id,
            'line_id': line.id,
            'pocket_id': pocket_b.id,
            'activate': True,
        })

        inward = self.Inward.create({
            'partner_id': self.customer.id,
            'season_id': self.season.id,
            'product_name': 'Potato Batch 5',
            'bag_quantity': 10,
            'date_start': self.today,
            'date_end': self.today + timedelta(days=30),
            'allocation_ids': [
                (0, 0, {'slot_id': slot_a.id, 'quantity': 10}),
            ],
        })

        # Transfer all 10 bags from A to B
        self.env['cold.storage.inward.plotting'].create({
            'inward_id': inward.id,
            'from_slot_id': slot_a.id,
            'to_slot_id': slot_b.id,
            'quantity': 10,
        })

        line_a = inward.allocation_ids.filtered(lambda a: a.slot_id == slot_a)
        line_b = inward.allocation_ids.filtered(lambda a: a.slot_id == slot_b)
        self.assertFalse(line_a)
        self.assertEqual(line_b.quantity, 10)

    def test_13_slot_plotting_constraints(self):
        """Test over-transfer and same-slot validation constraints."""
        chamber = self.env['cold.storage.chamber'].create({'name': 'Chamber 6'})
        floor = self.env['cold.storage.floor'].create({'name': 'Floor 6'})
        line = self.env['cold.storage.line'].create({'name': 'Line 6'})
        pocket_a = self.env['cold.storage.pocket'].create({'name': 'Pocket 6A'})
        pocket_b = self.env['cold.storage.pocket'].create({'name': 'Pocket 6B'})

        slot_a = self.env['cold.storage.master.setup'].create({
            'chamber_id': chamber.id,
            'floor_id': floor.id,
            'line_id': line.id,
            'pocket_id': pocket_a.id,
            'activate': True,
        })
        slot_b = self.env['cold.storage.master.setup'].create({
            'chamber_id': chamber.id,
            'floor_id': floor.id,
            'line_id': line.id,
            'pocket_id': pocket_b.id,
            'activate': True,
        })

        inward = self.Inward.create({
            'partner_id': self.customer.id,
            'season_id': self.season.id,
            'product_name': 'Potato Batch 6',
            'bag_quantity': 10,
            'date_start': self.today,
            'date_end': self.today + timedelta(days=30),
            'allocation_ids': [
                (0, 0, {'slot_id': slot_a.id, 'quantity': 10}),
            ],
        })

        # Same slot error
        with self.assertRaises(ValidationError):
            self.env['cold.storage.inward.plotting'].create({
                'inward_id': inward.id,
                'from_slot_id': slot_a.id,
                'to_slot_id': slot_a.id,
                'quantity': 5,
            })

        # Over-transfer error (15 > 10)
        with self.assertRaises(ValidationError):
            self.env['cold.storage.inward.plotting'].create({
                'inward_id': inward.id,
                'from_slot_id': slot_a.id,
                'to_slot_id': slot_b.id,
                'quantity': 15,
            })
