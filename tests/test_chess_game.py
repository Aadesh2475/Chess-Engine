import unittest

import chess

from chess_game import create_pgn, play_move


class ChessGameTests(unittest.TestCase):
    def test_play_move_updates_board_and_returns_san(self) -> None:
        board = chess.Board()

        san = play_move(
            board, chess.parse_square("e2"), chess.parse_square("e4")
        )

        self.assertEqual(san, "e4")
        self.assertEqual(board.peek().uci(), "e2e4")

    def test_illegal_move_does_not_change_board(self) -> None:
        board = chess.Board()
        original_fen = board.fen()

        with self.assertRaises(ValueError):
            play_move(
                board, chess.parse_square("e2"), chess.parse_square("e5")
            )

        self.assertEqual(board.fen(), original_fen)

    def test_pawn_promotion_uses_selected_piece(self) -> None:
        board = chess.Board("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")

        san = play_move(
            board,
            chess.parse_square("a7"),
            chess.parse_square("a8"),
            promotion="n",
        )

        self.assertEqual(san, "a8=N")
        self.assertEqual(board.piece_at(chess.parse_square("a8")).symbol(), "N")

    def test_pgn_export_includes_current_moves(self) -> None:
        board = chess.Board()
        play_move(board, chess.parse_square("e2"), chess.parse_square("e4"))

        pgn = create_pgn(board, "Player", "Stockfish")

        self.assertIn('[White "Player"]', pgn)
        self.assertIn("1. e4 *", pgn)


if __name__ == "__main__":
    unittest.main()
