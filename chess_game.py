import shutil
from pathlib import Path
from typing import Any

import chess
import chess.engine
import chess.pgn


def resolve_engine_path(engine_path: str) -> str:
    executable = shutil.which(engine_path)
    if executable is None and Path(engine_path).is_file():
        executable = engine_path
    if executable is None:
        raise FileNotFoundError(
            f"Stockfish executable not found: {engine_path}. "
            "Install Stockfish and enter its executable path."
        )
    return executable


def play_move(
    board: chess.Board,
    from_square: chess.Square,
    to_square: chess.Square,
    promotion: str = "q",
) -> str:
    promotion_piece = chess.PIECE_SYMBOLS.index(promotion.lower())
    for move in board.legal_moves:
        if move.from_square == from_square and move.to_square == to_square:
            if move.promotion is None or move.promotion == promotion_piece:
                san = board.san(move)
                board.push(move)
                return san
    raise ValueError("That move is not legal in the current position.")


def play_engine_move(
    engine_path: str, board: chess.Board, skill_level: int
) -> str:
    executable = resolve_engine_path(engine_path)
    engine = chess.engine.SimpleEngine.popen_uci(executable)
    try:
        engine.configure({"Skill Level": skill_level})
        result = engine.play(board, chess.engine.Limit(time=0.25 + skill_level * 0.04))
        if result.move is None:
            raise chess.engine.EngineError("Stockfish did not return a move.")
        san = board.san(result.move)
        board.push(result.move)
        return san
    finally:
        engine.quit()


def analyze_position(engine_path: str, board: chess.Board) -> list[dict[str, Any]]:
    executable = resolve_engine_path(engine_path)
    engine = chess.engine.SimpleEngine.popen_uci(executable)
    try:
        analysis = engine.analyse(
            board, chess.engine.Limit(time=1.5), multipv=3
        )
        lines = [analysis] if isinstance(analysis, dict) else analysis
        results = []
        for info in lines:
            principal_variation = info.get("pv", [])
            if not principal_variation:
                continue
            score = info["score"].pov(chess.WHITE)
            wdl = score.wdl(model="sf", ply=board.ply())
            total = wdl.wins + wdl.draws + wdl.losses
            line_board = board.copy()
            san_line = []
            for move in principal_variation[:8]:
                san_line.append(line_board.san(move))
                line_board.push(move)
            results.append(
                {
                    "move": board.san(principal_variation[0]),
                    "line": " ".join(san_line),
                    "score": score,
                    "white_win_probability": (wdl.wins + wdl.draws / 2) / total,
                    "draw_probability": wdl.draws / total,
                    "black_win_probability": wdl.losses / total,
                }
            )
        return results
    finally:
        engine.quit()


def create_pgn(
    board: chess.Board, white_name: str, black_name: str
) -> str:
    game = chess.pgn.Game.from_board(board)
    game.headers["White"] = white_name
    game.headers["Black"] = black_name
    game.headers["Result"] = board.result(claim_draw=False)
    exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=False)
    return game.accept(exporter)
