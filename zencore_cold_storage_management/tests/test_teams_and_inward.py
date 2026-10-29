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
            'product_name': 'Potato 10 Bags',
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

        # Check allowed_from_slot_ids strictly matches allocated slots (Slot A and B, not C)
        test_draft = self.env['cold.storage.inward.plotting'].new({'inward_id': inward.id})
        self.assertEqual(set(test_draft.allowed_from_slot_ids.ids), {slot_a.id, slot_b.id})
        self.assertNotIn(slot_c.id, test_draft.allowed_from_slot_ids.ids)

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

    def test_14_scrap_creation_and_auto_deduction(self):
        """Test scrap creation, sequence generation, auto-deduction, and inward quantities."""
        chamber = self.env['cold.storage.chamber'].create({'name': 'Chamber 7'})
        floor = self.env['cold.storage.floor'].create({'name': 'Floor 7'})
        line = self.env['cold.storage.line'].create({'name': 'Line 7'})
        pocket_a = self.env['cold.storage.pocket'].create({'name': 'Pocket 7A'})
        pocket_b = self.env['cold.storage.pocket'].create({'name': 'Pocket 7B'})

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
            'product_name': 'Potato Batch 7',
            'bag_quantity': 50,
            'date_start': self.today,
            'date_end': self.today + timedelta(days=30),
            'allocation_ids': [
                (0, 0, {'slot_id': slot_a.id, 'quantity': 20}),
                (0, 0, {'slot_id': slot_b.id, 'quantity': 30}),
            ],
        })

        self.assertEqual(inward.scrapped_quantity, 0)
        self.assertEqual(inward.remaining_quantity, 50)
        self.assertEqual(inward.scrap_count, 0)

        # Create scrap of 8 bags from slot_a
        scrap = self.env['cold.storage.inward.scrap'].create({
            'inward_id': inward.id,
            'slot_id': slot_a.id,
            'quantity': 8,
            'reason': 'Rotten due to moisture',
        })

        self.assertTrue(scrap.name.startswith('SCP/'))
        self.assertEqual(scrap.available_quantity, 12)  # Available after deduction
        self.assertEqual(inward.scrap_count, 1)
        self.assertEqual(inward.scrapped_quantity, 8)
        self.assertEqual(inward.remaining_quantity, 42)

        line_a = inward.allocation_ids.filtered(lambda a: a.slot_id == slot_a)
        line_b = inward.allocation_ids.filtered(lambda a: a.slot_id == slot_b)
        self.assertEqual(line_a.quantity, 12)
        self.assertEqual(line_b.quantity, 30)

    def test_15_scrap_exact_deduction_and_unlink(self):
        """Test that scrapping all bags in a slot unlinks the allocation line."""
        chamber = self.env['cold.storage.chamber'].create({'name': 'Chamber 8'})
        floor = self.env['cold.storage.floor'].create({'name': 'Floor 8'})
        line = self.env['cold.storage.line'].create({'name': 'Line 8'})
        pocket_a = self.env['cold.storage.pocket'].create({'name': 'Pocket 8A'})

        slot_a = self.env['cold.storage.master.setup'].create({
            'chamber_id': chamber.id,
            'floor_id': floor.id,
            'line_id': line.id,
            'pocket_id': pocket_a.id,
            'activate': True,
        })

        inward = self.Inward.create({
            'partner_id': self.customer.id,
            'season_id': self.season.id,
            'product_name': 'Potato Batch 8',
            'bag_quantity': 15,
            'date_start': self.today,
            'date_end': self.today + timedelta(days=30),
            'allocation_ids': [
                (0, 0, {'slot_id': slot_a.id, 'quantity': 15}),
            ],
        })

        # Scrap entire 15 bags
        self.env['cold.storage.inward.scrap'].create({
            'inward_id': inward.id,
            'slot_id': slot_a.id,
            'quantity': 15,
            'reason': 'Total loss in transit',
        })

        line_a = inward.allocation_ids.filtered(lambda a: a.slot_id == slot_a)
        self.assertFalse(line_a)
        self.assertEqual(inward.scrapped_quantity, 15)
        self.assertEqual(inward.remaining_quantity, 0)

    def test_16_scrap_validation_constraints(self):
        """Test over-scrap and non-positive quantity validation errors."""
        chamber = self.env['cold.storage.chamber'].create({'name': 'Chamber 9'})
        floor = self.env['cold.storage.floor'].create({'name': 'Floor 9'})
        line = self.env['cold.storage.line'].create({'name': 'Line 9'})
        pocket_a = self.env['cold.storage.pocket'].create({'name': 'Pocket 9A'})
        pocket_b = self.env['cold.storage.pocket'].create({'name': 'Pocket 9B'})

        slot_a = self.env['cold.storage.master.setup'].create({
            'chamber_id': chamber.id,
            'floor_id': floor.id,
            'line_id': line.id,
            'pocket_id': pocket_a.id,
            'activate': True,
        })
        slot_unallocated = self.env['cold.storage.master.setup'].create({
            'chamber_id': chamber.id,
            'floor_id': floor.id,
            'line_id': line.id,
            'pocket_id': pocket_b.id,
            'activate': True,
        })

        inward = self.Inward.create({
            'partner_id': self.customer.id,
            'season_id': self.season.id,
            'product_name': 'Potato Batch 9',
            'bag_quantity': 10,
            'date_start': self.today,
            'date_end': self.today + timedelta(days=30),
            'allocation_ids': [
                (0, 0, {'slot_id': slot_a.id, 'quantity': 10}),
            ],
        })

        # Non-positive quantity
        with self.assertRaises(ValidationError):
            self.env['cold.storage.inward.scrap'].create({
                'inward_id': inward.id,
                'slot_id': slot_a.id,
                'quantity': 0,
                'reason': 'Invalid zero scrap',
            })

        # Over-scrap (12 > 10)
        with self.assertRaises(ValidationError):
            self.env['cold.storage.inward.scrap'].create({
                'inward_id': inward.id,
                'slot_id': slot_a.id,
                'quantity': 12,
                'reason': 'More than available',
            })

        # Unallocated slot
        with self.assertRaises(ValidationError):
            self.env['cold.storage.inward.scrap'].create({
                'inward_id': inward.id,
                'slot_id': slot_unallocated.id,
                'quantity': 5,
                'reason': 'Slot not allocated',
            })

    def test_17_release_wizard_immediate_payment(self):
        """Test release wizard, slot deduction, customer invoice creation, and payment reconciliation."""
        chamber = self.env['cold.storage.chamber'].create({'name': 'Chamber 10'})
        floor = self.env['cold.storage.floor'].create({'name': 'Floor 10'})
        line = self.env['cold.storage.line'].create({'name': 'Line 10'})
        pocket_a = self.env['cold.storage.pocket'].create({'name': 'Pocket 10A'})
        pocket_b = self.env['cold.storage.pocket'].create({'name': 'Pocket 10B'})

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
            'product_name': 'Potato Batch 10',
            'bag_quantity': 50,
            'bag_rate': 50.00,
            'date_start': self.today,
            'date_end': self.today + timedelta(days=30),
            'allocation_ids': [
                (0, 0, {'slot_id': slot_a.id, 'quantity': 20}),
                (0, 0, {'slot_id': slot_b.id, 'quantity': 30}),
            ],
        })

        self.assertEqual(inward.released_quantity, 0)
        self.assertEqual(inward.remaining_quantity, 50)
        self.assertEqual(inward.release_count, 0)
        self.assertEqual(inward.invoice_count, 0)

        journal = self.env['account.journal'].search([('type', 'in', ['cash', 'bank'])], limit=1)

        # Launch wizard and pre-populate
        wizard = self.env['cold.storage.inward.release.wizard'].with_context(
            default_inward_id=inward.id
        ).create({
            'inward_id': inward.id,
            'receiver_name': 'Driver Kalam',
            'vehicle_no': 'Dhaka Metro-Ta 11-2233',
        })

        self.assertEqual(len(wizard.line_ids), 2)
        # Set 10 bags from slot_a
        line_a = wizard.line_ids.filtered(lambda l: l.slot_id == slot_a)
        line_a.quantity = 10

        self.assertEqual(wizard.total_release_quantity, 10)
        self.assertEqual(wizard.total_amount, 500.00)

        # Confirm release
        action = wizard.action_confirm_release()
        self.assertEqual(action.get('type'), 'ir.actions.act_window_close')

        release = self.env['cold.storage.inward.release'].search([('inward_id', '=', inward.id)], limit=1)
        self.assertTrue(release)
        self.assertTrue(release.name.startswith('REL/'))
        self.assertEqual(release.quantity, 10)
        self.assertEqual(release.total_amount, 500.00)
        self.assertTrue(release.move_id)
        self.assertEqual(release.move_id.move_type, 'out_invoice')
        # Invoice created in Draft state
        self.assertEqual(release.move_id.state, 'draft')

        # Check slot deduction
        alloc_a = inward.allocation_ids.filtered(lambda a: a.slot_id == slot_a)
        alloc_b = inward.allocation_ids.filtered(lambda a: a.slot_id == slot_b)
        self.assertEqual(alloc_a.quantity, 10)
        self.assertEqual(alloc_b.quantity, 30)

        # Check inward stock & counts
        self.assertEqual(inward.released_quantity, 10)
        self.assertEqual(inward.remaining_quantity, 40)
        self.assertEqual(inward.release_count, 1)
        self.assertEqual(inward.invoice_count, 1)

        # Smart button action test: strictly filtered to this lot's invoice
        inv_action = inward.action_view_invoices()
        self.assertEqual(inv_action['name'], f"Invoices - Lot {inward.name}")
        self.assertIn(release.move_id.id, inv_action['domain'][0][2])

        # Validate / Confirm invoice manually
        release.move_id.action_post()
        self.assertEqual(release.move_id.state, 'posted')
        self.assertEqual(inward.payment_status, 'due')
        self.assertEqual(inward.due_amount, 500.00)

        # Register payment via standard Odoo payment register
        payment_register = self.env['account.payment.register'].with_context(
            active_model='account.move',
            active_ids=release.move_id.ids,
        ).create({
            'journal_id': journal.id,
            'amount': 500.00,
            'payment_date': self.today,
        })
        payment_register._create_payments()
        self.assertIn(release.move_id.payment_state, ('paid', 'in_payment'))
        self.assertEqual(inward.payment_status, 'paid')
        self.assertEqual(inward.due_amount, 0.0)

    def test_18_release_credit_due_invoice(self):
        """Test partial release creates draft customer invoice and remains due on post."""
        chamber = self.env['cold.storage.chamber'].create({'name': 'Chamber 11'})
        floor = self.env['cold.storage.floor'].create({'name': 'Floor 11'})
        line = self.env['cold.storage.line'].create({'name': 'Line 11'})
        pocket_a = self.env['cold.storage.pocket'].create({'name': 'Pocket 11A'})

        slot_a = self.env['cold.storage.master.setup'].create({
            'chamber_id': chamber.id,
            'floor_id': floor.id,
            'line_id': line.id,
            'pocket_id': pocket_a.id,
            'activate': True,
        })

        inward = self.Inward.create({
            'partner_id': self.customer.id,
            'season_id': self.season.id,
            'product_name': 'Potato Batch 11',
            'bag_quantity': 25,
            'bag_rate': 60.00,
            'date_start': self.today,
            'date_end': self.today + timedelta(days=30),
            'allocation_ids': [
                (0, 0, {'slot_id': slot_a.id, 'quantity': 25}),
            ],
        })

        wizard = self.env['cold.storage.inward.release.wizard'].with_context(
            default_inward_id=inward.id
        ).create({
            'inward_id': inward.id,
            'receiver_name': 'Farmer Jamal',
        })

        wizard.line_ids[0].quantity = 5
        self.assertEqual(wizard.total_amount, 300.00)

        action = wizard.action_confirm_release()
        self.assertEqual(action.get('type'), 'ir.actions.act_window_close')
        release = self.env['cold.storage.inward.release'].search([('inward_id', '=', inward.id)], limit=1)

        self.assertEqual(release.move_id.state, 'draft')
        release.move_id.action_post()
        self.assertEqual(release.move_id.state, 'posted')
        self.assertEqual(release.move_id.payment_state, 'not_paid')
        self.assertEqual(inward.released_quantity, 5)
        self.assertEqual(inward.remaining_quantity, 20)
        self.assertEqual(inward.due_amount, 300.00)
        self.assertEqual(inward.payment_status, 'due')

    def test_19_release_full_depletion_unlinks_slot(self):
        """Test that releasing all bags in a slot unlinks the allocation line."""
        chamber = self.env['cold.storage.chamber'].create({'name': 'Chamber 12'})
        floor = self.env['cold.storage.floor'].create({'name': 'Floor 12'})
        line = self.env['cold.storage.line'].create({'name': 'Line 12'})
        pocket_a = self.env['cold.storage.pocket'].create({'name': 'Pocket 12A'})

        slot_a = self.env['cold.storage.master.setup'].create({
            'chamber_id': chamber.id,
            'floor_id': floor.id,
            'line_id': line.id,
            'pocket_id': pocket_a.id,
            'activate': True,
        })

        inward = self.Inward.create({
            'partner_id': self.customer.id,
            'season_id': self.season.id,
            'product_name': 'Potato Batch 12',
            'bag_quantity': 10,
            'bag_rate': 50.00,
            'date_start': self.today,
            'date_end': self.today + timedelta(days=30),
            'allocation_ids': [
                (0, 0, {'slot_id': slot_a.id, 'quantity': 10}),
            ],
        })

        wizard = self.env['cold.storage.inward.release.wizard'].with_context(
            default_inward_id=inward.id
        ).create({
            'inward_id': inward.id,
            'receiver_name': 'Farmer Jamal',
        })
        wizard.line_ids[0].quantity = 10

        wizard.action_confirm_release()

        alloc_a = inward.allocation_ids.filtered(lambda a: a.slot_id == slot_a)
        self.assertFalse(alloc_a)
        self.assertEqual(inward.remaining_quantity, 0)
        self.assertEqual(inward.released_quantity, 10)

    def test_20_release_validation_errors(self):
        """Test over-release and zero-quantity validation errors."""
        chamber = self.env['cold.storage.chamber'].create({'name': 'Chamber 13'})
        floor = self.env['cold.storage.floor'].create({'name': 'Floor 13'})
        line = self.env['cold.storage.line'].create({'name': 'Line 13'})
        pocket_a = self.env['cold.storage.pocket'].create({'name': 'Pocket 13A'})

        slot_a = self.env['cold.storage.master.setup'].create({
            'chamber_id': chamber.id,
            'floor_id': floor.id,
            'line_id': line.id,
            'pocket_id': pocket_a.id,
            'activate': True,
        })

        inward = self.Inward.create({
            'partner_id': self.customer.id,
            'season_id': self.season.id,
            'product_name': 'Potato Batch 13',
            'bag_quantity': 10,
            'bag_rate': 50.00,
            'date_start': self.today,
            'date_end': self.today + timedelta(days=30),
            'allocation_ids': [
                (0, 0, {'slot_id': slot_a.id, 'quantity': 10}),
            ],
        })

        # Zero quantity error
        wizard_zero = self.env['cold.storage.inward.release.wizard'].with_context(
            default_inward_id=inward.id
        ).create({
            'inward_id': inward.id,
            'receiver_name': 'Receiver',
        })
        wizard_zero.line_ids[0].quantity = 0
        with self.assertRaises(ValidationError):
            wizard_zero.action_confirm_release()

        # Over-release error (15 > 10)
        wizard_over = self.env['cold.storage.inward.release.wizard'].with_context(
            default_inward_id=inward.id
        ).create({
            'inward_id': inward.id,
            'receiver_name': 'Receiver',
        })
        wizard_over.line_ids[0].quantity = 15
        with self.assertRaises(ValidationError):
            wizard_over.action_confirm_release()


