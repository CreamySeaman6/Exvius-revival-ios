"""Gift rollover regression tests with synthetic state and no game-data download.

Run from the repository root:
    python3 -B -m unittest discover -s tests -p test_friend_gifts.py -v
Requires the server's existing PyYAML dependency. No save is loaded or written.
"""
import copy
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "source" / "server"))
import exvius_actions_shops as actions
import ffbe_friends
import ffbe_player
import player_state
from ffbe_state import State


class FriendGiftTests(unittest.TestCase):
    def setUp(self):
        self.player = player_state.PlayerState({
            "identity": {"user_id": "100", "handle_name": "Test Player"},
            "profile": {"gift_id": 10}, "rank": {"level": 1},
            "roster": [{"instance_id": "1", "master_id": "200", "level": 1}],
            "currencies": {"friend_point": 0},
            "progress": {"switches": {}},
        }, mode="ephemeral")
        self.midnight = int(datetime(2026, 1, 2, tzinfo=timezone.utc).timestamp())
        self.real_gmtime = time.gmtime
        friends = [{"friend_id": "300", "display_name": "Test Friend", "rank": 1,
                    "unit": {"master_id": "200", "level": 1}}]
        # Stub unrelated master-data lookups and full inventory projection;
        # gift send/claim validation, reward credit and retry guards are real.
        patches = [
            patch.object(State, "player", self.player),
            patch.object(ffbe_friends, "all_friends", return_value=friends),
            patch.object(ffbe_player, "_satisfied_quests", return_value=[]),
            patch.object(ffbe_player, "_daily_quests_for_action", return_value=[]),
            patch.object(player_state, "_load_ndjson", return_value={}),
            patch.object(actions, "_reply", side_effect=lambda spec: dict(spec)),
            patch.object(actions, "_define", return_value="0"),
            patch.object(actions, "_archive_rows", return_value=[]),
            patch.object(actions, "_point_rows", return_value=[]),
            patch.object(actions, "_service_master", side_effect=lambda name: {
                "10": {"YWF08vZS": "51", "6uIYE15X": "0", "Qy5EvcK1": "10"}
            } if name == "gifts" else {}),
        ]
        for mock in patches:
            mock.start()
            self.addCleanup(mock.stop)

    @contextmanager
    def clock(self, stamp):
        with patch.object(actions.time, "time", return_value=stamp), patch.object(
                actions.time, "gmtime", side_effect=lambda seconds=None:
                self.real_gmtime(stamp if seconds is None else seconds)):
            yield

    def send(self):
        return actions.gift_update({}, {"WSH38iMI": [{
            "2L0dxwuN": "300:10", "Utx8P1Qo": "10"}]})

    def outgoing(self, reply):
        return [row for row in reply["h5XGny0N"] if row["m94IYp6a"] == "100"]

    def test_reset_at_utc_midnight_preserves_pending_incoming_gift(self):
        with self.clock(self.midnight - 1):
            self.assertEqual(len(self.outgoing(self.send())), 1)
            before = copy.deepcopy(self.player.data)
            self.assertEqual(len(self.outgoing(self.send())), 1)
            self.assertEqual(self.player.data, before)
        with self.clock(self.midnight):
            menu = actions.serve_feature_state({}, reply_id="6H1R9WID")
            self.assertEqual(self.outgoing(menu), [])
            self.assertEqual(len(menu["h5XGny0N"]), 1)
            self.assertEqual(menu["h5XGny0N"][0]["Igd28KXq"], "0")
            self.assertEqual(self.player.data, before)
            reply = self.send()
            self.assertEqual(len(self.outgoing(reply)), 1)
            self.assertEqual(len(reply["h5XGny0N"]), 3)
            self.assertEqual(len(self.player.data["exvius_gift"]["receipts"]), 4)
            sent = copy.deepcopy(self.player.data)
            self.send()
            self.assertEqual(self.player.data, sent)

    def test_old_incoming_gift_can_be_claimed_only_once(self):
        with self.clock(self.midnight - 1):
            reply = self.send()
            incoming = next(row["2HqjK1F7"] for row in reply["h5XGny0N"]
                            if row["bUfq8BJ3"] == "100")
        claim = {"WSH38iMI": [{"9wXIbKq2": incoming, "Utx8P1Qo": "10"}]}
        with self.clock(self.midnight):
            reply = actions.gift_update({}, claim)
            self.assertEqual(self.player.currencies["friend_point"], 10)
            self.assertEqual(self.outgoing(reply), [])
            self.assertEqual(reply["h5XGny0N"][0]["Igd28KXq"], "1")
            actions.gift_update({}, claim)
            self.assertEqual(self.player.currencies["friend_point"], 10)

    def test_login_and_menu_replies_hide_old_outgoing_receipts(self):
        with self.clock(self.midnight - 1):
            self.send()
        before = copy.deepcopy(self.player.data)
        with self.clock(self.midnight):
            for reply_id in ("75fYdNxq", "X07iYtp5", "6H1R9WID", "u7Id4bMg",
                             "9KN5rcwj", "syKz34cE"):
                with self.subTest(reply_id=reply_id):
                    reply = actions.serve_feature_state({}, reply_id=reply_id)
                    self.assertEqual(self.outgoing(reply), [])
                    self.assertEqual(len(reply["h5XGny0N"]), 1)
        self.assertEqual(self.player.data, before)

    def test_refused_send_also_hides_old_outgoing_receipts(self):
        with self.clock(self.midnight - 1):
            self.send()
        before = copy.deepcopy(self.player.data)
        with self.clock(self.midnight):
            reply = actions.gift_update({}, {"WSH38iMI": [{
                "2L0dxwuN": "999:10", "Utx8P1Qo": "10"}]})
            self.assertEqual(self.outgoing(reply), [])
            self.assertEqual(len(reply["h5XGny0N"]), 1)
        self.assertEqual(self.player.data, before)

    def test_projection_returns_copies_without_modifying_saved_history(self):
        with self.clock(self.midnight - 1):
            self.send()
            before = copy.deepcopy(self.player.data)
            rows = actions.serve_feature_state({}, reply_id="6H1R9WID")["h5XGny0N"]
            rows[0]["Igd28KXq"] = "1"
            self.assertEqual(self.player.data, before)


if __name__ == "__main__":
    unittest.main()
