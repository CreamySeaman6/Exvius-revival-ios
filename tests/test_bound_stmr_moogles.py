"""Bound STMR fusion regression tests with synthetic unit masters and state.

Run from the repository root:
    python3 -B -m unittest discover -s tests -p test_bound_stmr_moogles.py -v
No downloaded game data or player save is required or written.
"""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "source" / "server"))
import player_state

BASE = "400000007"
BOUND = "906000001"
GENERIC = "906000105"
ORDINARY_LOW_RARITY = "400000003"
TMR_MOOGLE = "904000001"
STMR = "21:300000001:1:1000:0:0:0"
TMR = "22:500000001:1:1000:0:0:0"
REWARD = {"kind": 21, "id": 300000001, "count": 1}


def unit(instance, master, points=("0", "0"), info=None):
    row = {"instance_id": str(instance), "master_id": master, "level": 1, "exp": 0,
           "affinity_points": list(points), "affinity_reward_claimed": []}
    if info is not None:
        row["affinity_info"] = list(info)
    return row


class BoundStmrTests(unittest.TestCase):
    def setUp(self):
        self.masters = {
            BASE: {"9fW0TePj": "7", "C74EmZ1I": STMR, "9mu4boy7": TMR},
            BOUND: {"9fW0TePj": "3"},
            GENERIC: {"9fW0TePj": "3"},
            ORDINARY_LOW_RARITY: {"9fW0TePj": "3", "C74EmZ1I": STMR},
            TMR_MOOGLE: {"9fW0TePj": "1"},
        }
        mock = patch.object(player_state, "unit_mst", side_effect=lambda mid: self.masters.get(str(mid)))
        mock.start()
        self.addCleanup(mock.stop)
        self.player = player_state.PlayerState({
            "roster": [], "party": {"decks": []},
            "inventory": {"equipment": [], "items": []},
        }, mode="ephemeral")
        self.base = unit(1, BASE)
        self.bound = unit(2, BOUND, ("0", "1000"), ("", STMR))

    def test_matching_bound_moogle_reaches_mastery_and_plans_reward(self):
        before = copy.deepcopy([self.base, self.bound])
        points, claimed, rewards = self.player._plan_trust_fusion(self.base, [self.bound])
        self.assertEqual(points, ["0", "1000"])
        self.assertEqual(claimed, ["1:21:300000001:1"])
        self.assertEqual(rewards, [REWARD])
        self.assertEqual([self.base, self.bound], before)

    def test_wrong_unit_bound_moogle_does_not_grant_progress(self):
        self.bound["affinity_info"][1] = "21:300000002:1:1000:0:0:0"
        self.assertEqual(self.player._plan_trust_fusion(self.base, [self.bound]),
                         (["0", "0"], [], []))

    def test_generic_stmr_moogle_still_works(self):
        donor = unit(2, GENERIC, ("0", "1000"), ("", "70:0:0:1000:0:0:0"))
        self.assertEqual(self.player._plan_trust_fusion(self.base, [donor])[2], [REWARD])

    def test_other_low_rarity_units_still_cannot_donate_stmr(self):
        donor = unit(2, ORDINARY_LOW_RARITY, ("0", "1000"))
        self.assertEqual(self.player._plan_trust_fusion(self.base, [donor]),
                         (["0", "0"], [], []))

    def test_low_rarity_target_still_cannot_gain_stmr(self):
        self.masters[BASE]["9fW0TePj"] = "6"
        self.assertEqual(self.player._plan_trust_fusion(self.base, [self.bound]),
                         (["0", "0"], [], []))

    def test_trust_caps_and_existing_reward_claim_is_respected(self):
        self.base["affinity_points"][1] = "750"
        self.base["affinity_reward_claimed"] = ["1:21:300000001:1"]
        points, claimed, rewards = self.player._plan_trust_fusion(self.base, [self.bound])
        self.assertEqual(points[1], "1000")
        self.assertEqual(claimed, ["1:21:300000001:1"])
        self.assertEqual(rewards, [])

    def test_already_mastered_unit_gets_no_second_reward(self):
        self.base["affinity_points"][1] = "1000"
        points, _, rewards = self.player._plan_trust_fusion(self.base, [self.bound])
        self.assertEqual(points[1], "1000")
        self.assertEqual(rewards, [])

    def test_regular_tmr_moogle_behavior_is_unchanged(self):
        donor = unit(2, TMR_MOOGLE, ("100", "0"), (TMR, ""))
        points, _, rewards = self.player._plan_trust_fusion(self.base, [donor])
        self.assertEqual(points, ["100", "0"])
        self.assertEqual(rewards, [])

    def test_real_fusion_consumes_donor_and_grants_one_owned_equipment(self):
        self.player.data["roster"] = [self.base, self.bound]
        # EXP calculations are unrelated to trust and need downloaded growth tables.
        # Keep actual donor removal, trust planning, reward routing and ownership.
        with patch.object(player_state, "unit_mix_exp", return_value=0), \
                patch.object(player_state, "unit_mix_lb_exp", return_value=0), \
                patch.object(self.player, "add_unit_exp"):
            result = self.player.mix_units("1", ["2", "2"])
            self.assertEqual(result["removed"], ["2"])
            self.assertEqual(result["trust_rewards"], [REWARD])
            self.assertEqual(self.base["affinity_points"], ["0", "1000"])
            self.assertEqual(self.player.data["inventory"]["equipment"],
                             [{"item_id": 300000001, "count": 1}])
            self.assertIsNone(self.player.mix_units("1", ["2"]))
            self.player.data["roster"].append(unit(3, BOUND, ("0", "1000"), ("", STMR)))
            result = self.player.mix_units("1", ["3"])
            self.assertEqual(result["trust_rewards"], [])
            self.assertEqual(self.player.data["inventory"]["equipment"][0]["count"], 1)


if __name__ == "__main__":
    unittest.main()
