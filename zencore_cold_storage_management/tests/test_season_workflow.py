# -*- coding: utf-8 -*-
from datetime import date, timedelta
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestSeasonWorkflow(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Season = cls.env['cold.storage.season']
        cls.today = date.today()

    def test_01_create_season_success(self):
        """Test successful season creation in draft state."""
        season = self.Season.create({
            'name': 'Potato Season 2026-27',
            'date_start': self.today,
            'date_end': self.today + timedelta(days=180),
            'default_bag_rate': 120.50,
            'team': 'Operations Team Alpha',
            'season_manager': 'Manager Rahim',
        })
        self.assertEqual(season.state, 'draft')
        self.assertEqual(season.default_bag_rate, 120.50)
        self.assertEqual(season.team, 'Operations Team Alpha')

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
