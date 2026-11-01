import io
from typing import Any

import chess
import chess.pgn

MAX_CONTEXT_PLIES = 2


def parse_san_sequence(moves_san: str | list[str]) -> list[str]:
    if isinstance(moves_san, list):
        if not moves_san or any(not isinstance(move, str) for move in moves_san):
            raise ValueError("The game has no valid SAN move sequence.")
        board = chess.Board()
        moves: list[str] = []
        for san in moves_san:
            move = board.parse_san(san)
            moves.append(board.san(move))
            board.push(move)
        return moves

    if not isinstance(moves_san, str) or not moves_san.strip():
        raise ValueError("The game has no SAN move sequence.")

    game = chess.pgn.read_game(io.StringIO(f'[Event "Dataset game"]\n\n{moves_san}'))
    if game is None:
        raise ValueError("The move sequence could not be parsed as PGN.")
    if game.errors:
        raise ValueError(f"Invalid PGN move sequence: {game.errors[0]}")

    board = game.board()
    moves: list[str] = []
    for move in game.mainline_moves():
        moves.append(board.san(move))
        board.push(move)
    if not moves:
        raise ValueError("The game has no legal moves.")
    return moves


def new_policy() -> dict[str, Any]:
    return {"version": 2, "max_context_plies": MAX_CONTEXT_PLIES, "counts": {}}


def add_game_to_policy(policy: dict[str, Any], moves: list[str]) -> None:
    counts = policy.setdefault("counts", {})
    max_context = int(policy.get("max_context_plies", MAX_CONTEXT_PLIES))
    for index, move in enumerate(moves):
        context_sizes = range(1, min(max_context, index) + 1)
        if index == 0:
            context_sizes = range(0, 1)
        for context_size in context_sizes:
            context = " ".join(moves[index - context_size : index])
            next_moves = counts.setdefault(context, {})
            next_moves[move] = int(next_moves.get(move, 0)) + 1


def continuation_candidates(
    policy: dict[str, Any],
    history: list[str],
    board: chess.Board,
    limit: int = 5,
) -> tuple[str, list[tuple[str, int, float]]]:
    counts = policy.get("counts", {})
    max_context = int(policy.get("max_context_plies", MAX_CONTEXT_PLIES))
    minimum_context = 1 if history else 0

    for context_size in range(
        min(max_context, len(history)), minimum_context - 1, -1
    ):
        context = " ".join(history[-context_size:]) if context_size else ""
        candidates = counts.get(context, {})
        total = sum(int(count) for count in candidates.values())
        if total == 0:
            continue
        legal_candidates = []
        for san, count in sorted(
            candidates.items(), key=lambda item: int(item[1]), reverse=True
        ):
            try:
                board.parse_san(san)
            except ValueError:
                continue
            legal_candidates.append((san, int(count), int(count) / total))
        if legal_candidates:
            return context, legal_candidates[: max(1, limit)]
    return "", []


def suggestion_candidates(
    policy: dict[str, Any],
    history: list[str],
    board: chess.Board,
    limit: int = 5,
) -> tuple[str, list[tuple[str, int, float]], bool]:
    context, candidates = continuation_candidates(policy, history, board, limit)
    if candidates or not history:
        return context, candidates, False

    context, candidates = continuation_candidates(policy, [], board, limit)
    return context, candidates, bool(candidates)


def predict_next_move(
    policy: dict[str, Any], history: list[str], board: chess.Board
) -> tuple[str, int, float] | None:
    _, candidates = continuation_candidates(policy, history, board, limit=1)
    return candidates[0] if candidates else None


def game_moves(game: chess.pgn.Game) -> list[str]:
    if game.errors:
        raise ValueError(f"Invalid PGN: {game.errors[0]}")

    board = game.board()
    moves: list[str] = []
    for move in game.mainline_moves():
        moves.append(board.san(move))
        board.push(move)
    return moves


def build_policy(
    records: Any, max_games: int
) -> tuple[dict[str, Any], int, int, int]:
    policy = new_policy()
    games_used = 0
    games_skipped = 0
    records_seen = 0

    for index, record in enumerate(records):
        if index >= max_games:
            break
        records_seen += 1
        try:
            moves = parse_san_sequence(record["moves_san"])
        except (KeyError, TypeError, ValueError):
            games_skipped += 1
            continue
        add_game_to_policy(policy, moves)
        games_used += 1

    return policy, games_used, games_skipped, records_seen
