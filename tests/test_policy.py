import unittest

import chess

from policy import (
    add_game_to_policy,
    build_policy,
    continuation_candidates,
    new_policy,
    parse_san_sequence,
    predict_next_move,
    suggestion_candidates,
)


class PolicyTests(unittest.TestCase):
    def test_parse_san_sequence(self) -> None:
        self.assertEqual(
            parse_san_sequence("1. e4 e5 2. Nf3 Nc6 1-0"),
            ["e4", "e5", "Nf3", "Nc6"],
        )
        self.assertEqual(
            parse_san_sequence(["e4", "e5", "Nf3"]),
            ["e4", "e5", "Nf3"],
        )

    def test_predicts_only_legal_moves(self) -> None:
        policy = new_policy()
        add_game_to_policy(policy, ["e4", "e5", "Nf3"])
        policy["counts"][""] = {"e5": 50, "e4": 4}

        prediction = predict_next_move(policy, [], chess.Board())

        self.assertEqual(prediction, ("e4", 4, 4 / 54))

    def test_recent_context_is_preferred(self) -> None:
        policy = new_policy()
        add_game_to_policy(policy, ["e4", "e5", "Nf3"])
        add_game_to_policy(policy, ["e4", "e5", "Bc4"])
        board = chess.Board()
        for san in ("e4", "e5"):
            board.push_san(san)

        context, candidates = continuation_candidates(
            policy, ["e4", "e5"], board
        )
        self.assertEqual(context, "e4 e5")
        self.assertEqual(candidates, [("Nf3", 1, 0.5), ("Bc4", 1, 0.5)])
        self.assertEqual(predict_next_move(policy, ["e4", "e5"], board), candidates[0])

    def test_nonopening_positions_do_not_use_global_move_frequencies(self) -> None:
        policy = new_policy()
        add_game_to_policy(policy, ["e4", "e5", "Nf3"])
        board = chess.Board()
        board.push_san("d4")

        self.assertIsNone(predict_next_move(policy, ["d4"], board))

    def test_suggestion_uses_global_legal_move_when_context_is_unknown(self) -> None:
        policy = new_policy()
        policy["counts"][""] = {"e4": 100, "Nf6": 3}
        board = chess.Board()
        board.push_san("d4")

        context, candidates, used_fallback = suggestion_candidates(
            policy, ["d4"], board
        )

        self.assertEqual(context, "")
        self.assertEqual(candidates, [("Nf6", 3, 3 / 103)])
        self.assertTrue(used_fallback)

    def test_suggestion_prefers_matching_context_over_global_fallback(self) -> None:
        policy = new_policy()
        policy["counts"][""] = {"Nf6": 100}
        policy["counts"]["e4"] = {"e5": 3}
        board = chess.Board()
        board.push_san("e4")

        context, candidates, used_fallback = suggestion_candidates(
            policy, ["e4"], board
        )

        self.assertEqual(context, "e4")
        self.assertEqual(candidates, [("e5", 3, 1.0)])
        self.assertFalse(used_fallback)

    def test_invalid_san_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parse_san_sequence("1. e4 e5 2. Nxf6")

    def test_build_policy_from_dataset_records(self) -> None:
        policy, games_used, games_skipped, records_seen = build_policy(
            [{"moves_san": ["e4", "e5", "Nf3"]}], max_games=10
        )

        self.assertEqual((games_used, games_skipped, records_seen), (1, 0, 1))
        self.assertEqual(policy["counts"]["e4 e5"], {"Nf3": 1})


if __name__ == "__main__":
    unittest.main()
