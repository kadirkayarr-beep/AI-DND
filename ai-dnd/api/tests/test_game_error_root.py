"""The game's own errors share one root (desloppify: no_common_domain_error_root).

GameError is the root; GameInputError (a refused request, still a ValueError) and GameInfrastructureError (a failed
dependency) split it. Every old base stays, so no existing `except ValueError` / `except RuntimeError` catches more
or less than before.
"""
from __future__ import annotations
import unittest
import combat_lifecycle
import economic_actions
import equipment_economy
import game
from api.persistence.campaign_models import CampaignError, CampaignStorageError, InvalidDeathModeError
from game_errors import GameError, GameInfrastructureError, GameInputError
from incidents.commit import StaleCommit


class GameErrorRoot(unittest.TestCase):
    def test_every_domain_error_has_the_root_and_keeps_its_old_base(self):
        expected = {
            equipment_economy.EquipmentError: (GameInputError, ValueError),
            combat_lifecycle.CombatRequestError: (GameInputError, ValueError),
            InvalidDeathModeError: (CampaignError, ValueError),
            economic_actions.EconomicReceiptError: (GameError,),
            game.IntentInfrastructureError: (GameInfrastructureError,),
            StaleCommit: (GameInfrastructureError, RuntimeError),
            CampaignStorageError: (CampaignError,),
        }
        for error, bases in expected.items():
            with self.subTest(error.__name__):
                self.assertTrue(issubclass(error, GameError))
                for base in bases:
                    self.assertTrue(issubclass(error, base), base)

    def test_no_new_builtin_base_widens_an_old_catch(self):
        self.assertFalse(issubclass(GameError, (ValueError, RuntimeError, LookupError)))
        self.assertFalse(issubclass(GameInfrastructureError, (ValueError, RuntimeError)))
        for error in (economic_actions.EconomicReceiptError, game.IntentInfrastructureError, CampaignError):
            with self.subTest(error.__name__):
                self.assertFalse(issubclass(error, (ValueError, RuntimeError)))
        self.assertFalse(issubclass(StaleCommit, ValueError))


if __name__ == "__main__":
    unittest.main()
