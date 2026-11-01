import html
import io
import json
import os
import shutil
from pathlib import Path
from typing import Any

import chess
import chess.engine
import chess.pgn
import streamlit as st

from chess_game import create_pgn, play_engine_move, play_move
from policy import add_game_to_policy, game_moves, new_policy, suggestion_candidates

ROOT = Path(__file__).resolve().parent
POLICY_PATH = ROOT / "data" / "move_policy.json"
PIECE_GLYPHS = {
    "K": "♔",
    "Q": "♕",
    "R": "♖",
    "B": "♗",
    "N": "♘",
    "P": "♙",
    "k": "♚",
    "q": "♛",
    "r": "♜",
    "b": "♝",
    "n": "♞",
    "p": "♟",
}

st.set_page_config(page_title="Chess Study", page_icon="♞", layout="wide")
st.markdown(
    """
    <style>
    .stApp { background: #101714; color: #eef4ed; }
    [data-testid="stSidebar"] { background: #17211c; }
    .study-card {
        background: #1a251f; border: 1px solid #2e4035; border-radius: 14px;
        padding: 18px 20px; margin: 8px 0 16px;
    }
    .muted { color: #a9b9ae; font-size: 0.92rem; }
    .board {
        display: grid; grid-template-columns: repeat(8, 1fr);
        width: min(100%, 520px); aspect-ratio: 1; border: 5px solid #28372f;
        border-radius: 6px; overflow: hidden;
    }
    .square { display: flex; align-items: center; justify-content: center;
        font-size: clamp(25px, 5vw, 48px); line-height: 1; }
    .light { background: #e8e4d8; }
    .dark { background: #75936f; }
    .white-piece { color: #fff; text-shadow: 0 2px 2px #354339, 0 0 2px #354339; }
    .black-piece { color: #202a24; }
    </style>
    """,
    unsafe_allow_html=True,
)


def new_game() -> None:
    st.session_state["game_board"] = chess.Board()
    st.session_state["game_moves"] = []
    st.session_state["game_selected_square"] = None
    st.session_state["game_engine_error"] = None
    st.session_state["game_last_san"] = None
    st.session_state["game_mode"] = st.session_state["game_mode_setting"]
    st.session_state["game_player_color"] = (
        chess.WHITE
        if st.session_state["game_player_color_setting"] == "White"
        else chess.BLACK
    )


def undo_turn() -> None:
    board = st.session_state["game_board"]
    move_count = 2 if st.session_state["game_mode"] == "Stockfish" else 1
    for _ in range(min(move_count, len(board.move_stack))):
        board.pop()
        st.session_state["game_moves"].pop()
    st.session_state["game_selected_square"] = None
    st.session_state["game_engine_error"] = None
    st.session_state["game_last_san"] = None


def on_square_click(square_name: str) -> None:
    board = st.session_state["game_board"]
    square = chess.parse_square(square_name)
    selected = st.session_state["game_selected_square"]
    mode = st.session_state["game_mode"]
    player_color = st.session_state["game_player_color"]

    if mode == "Stockfish" and board.turn != player_color:
        return

    if selected is not None:
        promotion = {
            "Queen": "q",
            "Rook": "r",
            "Bishop": "b",
            "Knight": "n",
        }[st.session_state["game_promotion_choice"]]
        try:
            san = play_move(board, selected, square, promotion)
        except ValueError:
            piece = board.piece_at(square)
            if piece is not None and piece.color == board.turn:
                st.session_state["game_selected_square"] = square
            else:
                st.session_state["game_selected_square"] = None
            return

        st.session_state["game_moves"].append(san)
        st.session_state["game_last_san"] = san
        st.session_state["game_selected_square"] = None
        st.session_state["game_engine_error"] = None
        return

    piece = board.piece_at(square)
    if piece is not None and piece.color == board.turn:
        st.session_state["game_selected_square"] = square


def draw_playable_board(
    board: chess.Board, flipped: bool, selected_square: int | None
) -> None:
    files = range(7, -1, -1) if flipped else range(8)
    ranks = range(8) if flipped else range(7, -1, -1)
    legal_targets = {
        move.to_square
        for move in board.legal_moves
        if move.from_square == selected_square
    }

    rules = []
    for rank in ranks:
        for file in files:
            square = chess.square(file, rank)
            square_name = chess.square_name(square)
            square_color = "#769656" if (file + rank) % 2 else "#eeeed2"
            if square == selected_square:
                square_color = "#f6f669"
            rules.append(
                f".st-key-game-square-{square_name} button "
                f"{{ background: {square_color} !important; "
                "border: 0 !important; border-radius: 0 !important; "
                "min-height: 56px !important; height: min(10vw, 72px) !important; "
                "padding: 0 !important; font-size: clamp(24px, 5vw, 48px) !important; "
                "color: #202a24 !important; box-shadow: none !important; }"
                f".st-key-game-square-{square_name} button:hover "
                "{ filter: brightness(1.12); }"
            )
            if square in legal_targets and square != selected_square:
                rules.append(
                    f".st-key-game-square-{square_name} button "
                    "{ box-shadow: inset 0 0 0 4px #ddca66 !important; }"
                )
    st.markdown(f"<style>{''.join(rules)}</style>", unsafe_allow_html=True)

    for rank in ranks:
        row = st.columns([0.24] + [1] * 8, gap="small")
        with row[0]:
            st.markdown(
                f"<div style='height:56px;display:flex;align-items:center;"
                f"color:#a9b9ae'>{rank + 1}</div>",
                unsafe_allow_html=True,
            )
        for column, file in enumerate(files, start=1):
            square = chess.square(file, rank)
            piece = board.piece_at(square)
            glyph = PIECE_GLYPHS[piece.symbol()] if piece else ""
            if square in legal_targets and piece is None:
                glyph = "·"
            with row[column]:
                st.button(
                    glyph or " ",
                    key=f"game-square-{chess.square_name(square)}",
                    on_click=on_square_click,
                    args=(chess.square_name(square),),
                    disabled=board.is_game_over(claim_draw=False),
                    use_container_width=True,
                )

    labels = st.columns([0.24] + [1] * 8, gap="small")
    for column, file in enumerate(files, start=1):
        with labels[column]:
            st.caption(chess.FILE_NAMES[file])


def format_game_status(board: chess.Board) -> tuple[str, str]:
    outcome = board.outcome(claim_draw=False)
    if outcome is not None:
        if outcome.winner is None:
            return "Draw", outcome.termination.name.replace("_", " ").title()
        winner = "White" if outcome.winner == chess.WHITE else "Black"
        return f"{winner} wins", outcome.termination.name.replace("_", " ").title()
    if board.is_check():
        return f"{'White' if board.turn else 'Black'} to move", "Check"
    return f"{'White' if board.turn else 'Black'} to move", "Game in progress"


def load_policy() -> dict[str, Any]:
    if not POLICY_PATH.exists():
        return new_policy()
    with POLICY_PATH.open(encoding="utf-8") as policy_file:
        policy = json.load(policy_file)
    if (
        not isinstance(policy, dict)
        or policy.get("version") != 2
        or not isinstance(policy.get("counts"), dict)
    ):
        raise ValueError(f"The continuation model at {POLICY_PATH} has an invalid format.")
    return policy


def save_policy(policy: dict[str, Any]) -> None:
    POLICY_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = POLICY_PATH.with_suffix(".tmp")
    try:
        temporary_path.write_text(
            json.dumps(policy, separators=(",", ":")), encoding="utf-8"
        )
        temporary_path.replace(POLICY_PATH)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def draw_board(board: chess.Board) -> str:
    squares: list[str] = []
    for row in range(7, -1, -1):
        for col in range(8):
            square = chess.square(col, row)
            piece = board.piece_at(square)
            color = "light" if (row + col) % 2 else "dark"
            glyph = PIECE_GLYPHS[piece.symbol()] if piece else ""
            piece_class = (
                "white-piece" if piece and piece.color == chess.WHITE else "black-piece"
            )
            squares.append(
                f'<div class="square {color} {piece_class}">{glyph}</div>'
            )
    return '<div class="board">' + "".join(squares) + "</div>"


def analyze_position(engine_path: str, board: chess.Board) -> list[dict[str, Any]]:
    executable = shutil.which(engine_path)
    if executable is None and Path(engine_path).is_file():
        executable = engine_path
    if executable is None:
        raise FileNotFoundError(
            f"Stockfish executable not found: {engine_path}. "
            "Install Stockfish and enter its executable path."
        )

    engine = chess.engine.SimpleEngine.popen_uci(executable)
    try:
        lines = engine.analyse(
            board, chess.engine.Limit(time=1.5), multipv=3
        )
        if isinstance(lines, dict):
            lines = [lines]
        results = []
        for info in lines:
            pv = info.get("pv", [])
            if not pv:
                continue
            score = info["score"].pov(chess.WHITE)
            wdl = score.wdl(model="sf", ply=board.ply())
            total = wdl.wins + wdl.draws + wdl.losses
            white_win_probability = (wdl.wins + wdl.draws / 2) / total
            line_board = board.copy()
            san_line = []
            for move in pv[:8]:
                san_line.append(line_board.san(move))
                line_board.push(move)
            results.append(
                {
                    "move": board.san(pv[0]),
                    "line": " ".join(san_line),
                    "score": score,
                    "white_win_probability": white_win_probability,
                    "draw_probability": wdl.draws / total,
                    "black_win_probability": wdl.losses / total,
                }
            )
        return results
    finally:
        engine.quit()


st.title("♞ Chess PGN Review")
st.caption(
    "Review an imported game after it ends. Dataset continuations are educational "
    "patterns, not engine-ranked best moves."
)

try:
    policy = load_policy()
except (OSError, json.JSONDecodeError, ValueError) as error:
    st.error(f"Could not load the local move model: {error}")
    st.stop()

with st.sidebar:
    st.subheader("Study model")
    training = policy.get("training", {})
    local_games_added = int(policy.get("local_games_added", 0))
    if training:
        st.success(f"Trained on {training.get('games_used', 0):,} dataset games")
        if local_games_added:
            st.caption(f"Updated with {local_games_added:,} local completed games")
    elif local_games_added:
        st.success(f"Learned from {local_games_added:,} local completed games")
    else:
        st.info("No dataset model found.")
        st.code("python train_model.py --max-games 50000", language="powershell")
    st.markdown(
        '<p class="muted">The model learns common SAN continuations. '
        "Stockfish is optional and supplies engine evaluations.</p>",
        unsafe_allow_html=True,
    )
    stockfish_path = st.text_input(
        "Stockfish executable path",
        value=os.environ.get("STOCKFISH_PATH", "stockfish"),
        help="Install Stockfish separately, then enter its executable name or full path.",
    )

uploaded_file = st.file_uploader(
    "Import a completed game (PGN)",
    type=["pgn"],
    help="This study tool only analyzes a game file you choose; it does not monitor a live board.",
)

if uploaded_file is None:
    st.markdown(
        '<div class="study-card"><h3>Start with a PGN</h3>'
        '<p class="muted">Export a finished game as PGN and upload it here. '
        "You can step through the moves, see a learned continuation, and request "
        "an optional Stockfish evaluation for the selected position.</p></div>",
        unsafe_allow_html=True,
    )
    st.stop()

try:
    game = chess.pgn.read_game(io.StringIO(uploaded_file.getvalue().decode("utf-8-sig")))
    if game is None:
        raise ValueError("No PGN game was found in the uploaded file.")
    moves = game_moves(game)
except (UnicodeDecodeError, ValueError) as error:
    st.error(f"Could not read this PGN: {error}")
    st.stop()

headers = game.headers
white_name = headers.get("White", "White")
black_name = headers.get("Black", "Black")
st.markdown(
    f'<div class="study-card"><strong>{html.escape(white_name)} '
    f'vs {html.escape(black_name)}</strong> '
    f'<span class="muted"> · Result: {html.escape(headers.get("Result", "*"))}'
    f" · {len(moves)} plies</span></div>",
    unsafe_allow_html=True,
)

selected_ply = st.slider(
    "Move",
    min_value=0,
    max_value=len(moves),
    value=max(0, len(moves) - 1),
)
board = game.board()
history: list[str] = []
for san in moves[:selected_ply]:
    move = board.parse_san(san)
    history.append(san)
    board.push(move)

board_column, insight_column = st.columns([1.05, 0.95], gap="large")
with board_column:
    st.components.v1.html(draw_board(board), height=535, scrolling=False)
    st.caption(f"Position after {selected_ply} half-moves · FEN: `{board.fen()}`")

with insight_column:
    st.subheader("Smart move suggestion")
    _, suggestions, used_fallback = suggestion_candidates(
        policy, history, board, limit=3
    )
    if not suggestions:
        st.info("No legal learned move was found for this position.")
    else:
        san, occurrences, share = suggestions[0]
        st.markdown(
            f'<div class="study-card"><h3>Top learned move: '
            f'{html.escape(san)}</h3>'
            f'<p class="muted">Most frequent legal dataset move for this '
            f"context · {occurrences:,} examples · {share:.1%} of matching samples</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        for candidate, count, candidate_share in suggestions[1:]:
            st.markdown(
                f"- `{candidate}` · {count:,} examples · {candidate_share:.1%}"
            )
        if selected_ply < len(moves):
            played_move = moves[selected_ply]
            if played_move == san:
                st.success(f"The game played the top learned move: {played_move}.")
            else:
                st.caption(
                    f"The game played **{played_move}** here; the top learned "
                    f"suggestion was **{san}**."
                )
        if used_fallback:
            st.caption(
                "No recent-move context matched; suggestions use the most "
                "frequent legal moves across the training games."
            )
        st.caption(
            "These are learned move frequencies, not engine-ranked best moves."
        )

    st.subheader("Engine evaluation")
    st.caption("Evaluation and win/draw estimates are available when Stockfish is installed.")
    if st.button("Analyze selected position", type="primary"):
        try:
            st.session_state["engine_result"] = {
                "fen": board.fen(),
                "lines": analyze_position(stockfish_path.strip(), board),
            }
            st.session_state.pop("engine_error", None)
        except (FileNotFoundError, OSError, chess.engine.EngineError, ValueError) as error:
            st.session_state["engine_error"] = str(error)
            st.session_state.pop("engine_result", None)

    engine_error = st.session_state.get("engine_error")
    if engine_error:
        st.error(engine_error)
    engine_result = st.session_state.get("engine_result")
    if engine_result and engine_result["fen"] == board.fen():
        if not engine_result["lines"]:
            st.info("The engine did not return a principal variation for this position.")
        for index, line in enumerate(engine_result["lines"], start=1):
            score_text = line["score"].score(mate_score=100_000)
            score_label = f"M{line['score'].mate()}" if line["score"].is_mate() else f"{score_text / 100:+.2f}"
            st.markdown(
                f"**{index}. {line['move']}** · evaluation {score_label} "
                f"(White perspective)"
            )
            st.code(line["line"], language=None)
            white_pct = line["white_win_probability"] * 100
            draw_pct = line["draw_probability"] * 100
            black_pct = line["black_win_probability"] * 100
            st.caption(
                f"Estimated outcome: White {white_pct:.1f}% · "
                f"Draw {draw_pct:.1f}% · Black {black_pct:.1f}%"
            )

    st.divider()
    st.subheader("Learn from this finished game")
    if headers.get("Result") not in {"1-0", "0-1", "1/2-1/2"}:
        st.caption("A completed-game result is required before adding this game to the local model.")
    elif st.button("Add completed game to local model"):
        add_game_to_policy(policy, moves)
        policy["local_games_added"] = int(policy.get("local_games_added", 0)) + 1
        try:
            save_policy(policy)
        except OSError as error:
            st.error(f"Could not save the updated local model: {error}")
        else:
            st.success("Added this game to the local continuation model.")
