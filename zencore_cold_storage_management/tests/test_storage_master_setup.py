# -*- coding: utf-8 -*-
from psycopg2 import IntegrityError
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


class TestStorageMasterSetup(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Chamber = cls.env['cold.storage.chamber']
        cls.Floor = cls.env['cold.storage.floor']
        cls.Line = cls.env['cold.storage.line']
        cls.Pocket = cls.env['cold.storage.pocket']
        cls.MasterSetup = cls.env['cold.storage.master.setup']

        cls.chamber_1 = cls.Chamber.create({'name': 'Chamber 1'})
        cls.floor_1 = cls.Floor.create({'name': '1st Floor'})
        cls.line_a = cls.Line.create({'name': 'Line A'})
        cls.pocket_101 = cls.Pocket.create({'name': 'Pocket 101'})

    def test_01_create_slot_computed_name_and_default_activate(self):
        """Test master slot creation, computed name, and activate default False."""
        slot = self.MasterSetup.create({
            'chamber_id': self.chamber_1.id,
            'floor_id': self.floor_1.id,
            'line_id': self.line_a.id,
            'pocket_id': self.pocket_101.id,
        })
        self.assertFalse(slot.activate, "Default activate must be False as required.")
        expected_name = f"{self.chamber_1.name} / {self.floor_1.name} / {self.line_a.name} / {self.pocket_101.name}"
        self.assertEqual(slot.name, expected_name, "Computed slot name must format properly.")

    def test_02_duplicate_slot_constraint(self):
        """Test that duplicate Chamber+Floor+Line+Pocket combination raises IntegrityError."""
        self.MasterSetup.create({
            'chamber_id': self.chamber_1.id,
            'floor_id': self.floor_1.id,
            'line_id': self.line_a.id,
            'pocket_id': self.pocket_101.id,
        })
        with mute_logger('odoo.sql_db'):
            with self.assertRaises(Exception):
                with self.cr.savepoint():
                    self.MasterSetup.create({
                        'chamber_id': self.chamber_1.id,
                        'floor_id': self.floor_1.id,
                        'line_id': self.line_a.id,
                        'pocket_id': self.pocket_101.id,
                    })
