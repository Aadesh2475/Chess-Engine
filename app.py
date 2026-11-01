import base64
import html
import json
import os
from pathlib import Path

import chess
import chess.engine
import streamlit as st

from chess_game import (
    analyze_position,
    create_pgn,
    play_engine_move,
    play_move,
    resolve_engine_path,
)
from policy import continuation_candidates

MODEL_PATH = Path(__file__).resolve().parent / "data" / "move_policy.json"
CHESS_ASSET_DIRECTORY = Path(__file__).resolve().parent / "assets" / "chess"

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
PIECE_SPRITE_COLUMNS = {"k": 0, "q": 1, "r": 2, "b": 3, "n": 4, "p": 5}
PROMOTION_PIECES = {
    "Queen": "q",
    "Rook": "r",
    "Bishop": "b",
    "Knight": "n",
}

st.set_page_config(page_title="Chess Studio", page_icon="♞", layout="wide")
st.markdown(
    """
    <style>
    .stApp { background: #101714; color: #eef4ed; }
    [data-testid="stSidebar"] { background: #17211c; }
    .game-card {
        background: #1a251f; border: 1px solid #2e4035; border-radius: 14px;
        padding: 16px 20px; margin: 8px 0 16px;
    }
    .muted { color: #a9b9ae; font-size: 0.92rem; }
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


@st.cache_data(show_spinner=False)
def load_chess_images(
    asset_directory: str, _modified_times: tuple[int, int]
) -> tuple[str, str]:
    directory = Path(asset_directory)
    board_image = base64.b64encode(
        (directory / "board-texture.png").read_bytes()
    ).decode("ascii")
    piece_sprites = base64.b64encode(
        (directory / "piece-sprites.png").read_bytes()
    ).decode("ascii")
    return (
        f"data:image/png;base64,{board_image}",
        f"data:image/png;base64,{piece_sprites}",
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
    if (
        st.session_state["game_mode"] == "Stockfish"
        and board.turn != st.session_state["game_player_color"]
    ):
        return

    if selected is not None:
        promotion = PROMOTION_PIECES[st.session_state["game_promotion_choice"]]
        try:
            san = play_move(board, selected, square, promotion)
        except ValueError:
            piece = board.piece_at(square)
            st.session_state["game_selected_square"] = (
                square if piece is not None and piece.color == board.turn else None
            )
            return

        st.session_state["game_moves"].append(san)
        st.session_state["game_last_san"] = san
        st.session_state["game_selected_square"] = None
        st.session_state["game_engine_error"] = None
        return

    piece = board.piece_at(square)
    if piece is not None and piece.color == board.turn:
        st.session_state["game_selected_square"] = square


def draw_board(board: chess.Board, flipped: bool) -> None:
    files = range(7, -1, -1) if flipped else range(8)
    ranks = range(8) if flipped else range(7, -1, -1)
    board_image_path = CHESS_ASSET_DIRECTORY / "board-texture.png"
    piece_sprite_path = CHESS_ASSET_DIRECTORY / "piece-sprites.png"
    board_image, piece_sprites = load_chess_images(
        str(CHESS_ASSET_DIRECTORY),
        (
            board_image_path.stat().st_mtime_ns,
            piece_sprite_path.stat().st_mtime_ns,
        ),
    )
    selected = st.session_state["game_selected_square"]
    legal_targets = {
        move.to_square
        for move in board.legal_moves
        if selected is not None and move.from_square == selected
    }
    rules = [
        ":root {"
        f"--chess-board-image: url('{board_image}');"
        f"--chess-piece-sprites: url('{piece_sprites}');"
        "}"
    ]
    for visual_row, rank in enumerate(ranks):
        for visual_column, file in enumerate(files):
            square = chess.square(file, rank)
            square_name = chess.square_name(square)
            piece = board.piece_at(square)
            background_images = []
            background_sizes = []
            background_positions = []
            if piece is not None:
                sprite_column = PIECE_SPRITE_COLUMNS[piece.symbol().lower()]
                sprite_row = 0 if piece.color == chess.WHITE else 1
                background_images.append("var(--chess-piece-sprites)")
                background_sizes.append("600% 200%")
                background_positions.append(
                    f"{sprite_column * 20}% {sprite_row * 100}%"
                )
            if square == selected:
                background_images.append(
                    "linear-gradient(rgba(246, 246, 105, .38), "
                    "rgba(246, 246, 105, .38))"
                )
                background_sizes.append("100% 100%")
                background_positions.append("0 0")
            board_position = (
                f"{visual_column * 100 / 7:.4f}% "
                f"{visual_row * 100 / 7:.4f}%"
            )
            background_images.append("var(--chess-board-image)")
            background_sizes.append("800% 800%")
            background_positions.append(board_position)
            rules.append(
                f".st-key-game-square-{square_name} button "
                "{ background-color: #6b432a !important; "
                f"background-image: {', '.join(background_images)} !important; "
                f"background-size: {', '.join(background_sizes)} !important; "
                f"background-position: {', '.join(background_positions)} !important; "
                "background-repeat: no-repeat !important; "
                "border: 0 !important; position: relative; overflow: hidden; "
                "border-radius: 0 !important; min-height: 0 !important; "
                "height: auto !important; aspect-ratio: 1 / 1; padding: 0 !important; "
                "font-size: clamp(24px, 5vw, 48px) !important; "
                "box-shadow: none !important; }"
                f".st-key-game-square-{square_name} button:hover "
                "{ filter: brightness(1.12); }"
            )
            if piece is not None:
                rules.append(
                    f".st-key-game-square-{square_name} button "
                    "{ color: transparent !important; text-shadow: none !important; "
                    "font-size: 0 !important; }"
                )
            if square in legal_targets and square != selected:
                rules.append(
                    f".st-key-game-square-{square_name} button "
                    "{ box-shadow: inset 0 0 0 4px #ddca66 !important; }"
                )
    st.markdown(f"<style>{''.join(rules)}</style>", unsafe_allow_html=True)

    for rank in ranks:
        row = st.columns([0.24] + [1] * 8, gap="small")
        with row[0]:
            st.markdown(
                f"<div style='height:40px;display:flex;align-items:center;"
                f"color:#a9b9ae'>{rank + 1}</div>",
                unsafe_allow_html=True,
            )
        for column, file in enumerate(files, start=1):
            square = chess.square(file, rank)
            piece = board.piece_at(square)
            label = PIECE_GLYPHS[piece.symbol()] if piece else " "
            if square in legal_targets and piece is None:
                label = "·"
            with row[column]:
                st.button(
                    label,
                    key=f"game-square-{chess.square_name(square)}",
                    on_click=on_square_click,
                    args=(chess.square_name(square),),
                    disabled=board.is_game_over(claim_draw=False),
                    use_container_width=True,
                )

    coordinates = st.columns([0.24] + [1] * 8, gap="small")
    for column, file in enumerate(files, start=1):
        with coordinates[column]:
            st.caption(chess.FILE_NAMES[file])


def game_status(board: chess.Board) -> tuple[str, str]:
    outcome = board.outcome(claim_draw=False)
    if outcome is not None:
        if outcome.winner is None:
            return "Draw", outcome.termination.name.replace("_", " ").title()
        winner = "White" if outcome.winner == chess.WHITE else "Black"
        return f"{winner} wins", outcome.termination.name.replace("_", " ").title()
    side_to_move = "White" if board.turn == chess.WHITE else "Black"
    return f"{side_to_move} to move", "Check" if board.is_check() else "In progress"


@st.cache_resource(show_spinner=False)
def load_move_model(model_path: str, modified_time: int) -> dict:
    del modified_time
    with Path(model_path).open(encoding="utf-8") as model_file:
        model = json.load(model_file)
    if model.get("version") != 2 or not isinstance(model.get("counts"), dict):
        raise ValueError("The saved move-frequency model has an unsupported format.")
    return model


def model_flow_svg(
    training_games: int,
    context: str,
    candidates: list[tuple[str, int, float]],
) -> str:
    escaped_context = html.escape(context or "Opening position")
    candidate_nodes = []
    connectors = [
        '<path d="M190 150 C225 150 240 150 275 150" fill="none" '
        'stroke="#79a77e" stroke-width="4"/>'
    ]
    visible_candidates = candidates[:5]
    if visible_candidates:
        for index, (san, count, share) in enumerate(visible_candidates):
            y = 31 + index * 55
            width = 2 + share * 8
            connectors.append(
                f'<path d="M485 150 C535 150 555 {y + 21} 610 {y + 21}" '
                f'fill="none" stroke="#79a77e" stroke-opacity=".72" '
                f'stroke-width="{width:.1f}"/>'
            )
            candidate_nodes.append(
                f'<rect x="610" y="{y}" width="205" height="43" rx="10" '
                'fill="#24352a" stroke="#517958"/>'
                f'<text x="627" y="{y + 19}" fill="#f3f5ed" '
                f'font-size="14" font-weight="700">{html.escape(san)}</text>'
                f'<text x="627" y="{y + 35}" fill="#b3c5b5" '
                f'font-size="10">{count:,} examples · {share:.1%}</text>'
            )
    else:
        connectors.append(
            '<path d="M485 150 C535 150 555 150 610 150" fill="none" '
            'stroke="#526157" stroke-width="2" stroke-dasharray="5 6"/>'
        )
        candidate_nodes.append(
            '<rect x="610" y="126" width="205" height="48" rx="10" '
            'fill="#202a24" stroke="#46554a"/>'
            '<text x="627" y="155" fill="#b3c5b5" font-size="12">'
            "No matching legal continuation</text>"
        )

    return (
        '<div style="background:#141e18;border:1px solid #2e4035;'
        'border-radius:12px;padding:8px;overflow:hidden">'
        '<svg viewBox="0 0 840 320" role="img" '
        'aria-label="Dataset move-frequency model flow" '
        'style="width:100%;height:auto;font-family:Arial,sans-serif">'
        + "".join(connectors)
        + '<rect x="20" y="110" width="170" height="80" rx="14" '
        'fill="#263b2b" stroke="#79a77e"/>'
        '<text x="38" y="142" fill="#f3f5ed" font-size="15" '
        'font-weight="700">Chess games</text>'
        f'<text x="38" y="166" fill="#b3c5b5" font-size="12">'
        f'{training_games:,} training games</text>'
        '<rect x="275" y="110" width="210" height="80" rx="14" '
        'fill="#263b2b" stroke="#79a77e"/>'
        '<text x="294" y="140" fill="#f3f5ed" font-size="14" '
        'font-weight="700">Recent SAN context</text>'
        f'<text x="294" y="165" fill="#b3c5b5" font-size="12">'
        f'{escaped_context[:24]}</text>'
        + "".join(candidate_nodes)
        + '<text x="20" y="302" fill="#a9b9ae" font-size="11">'
        "Edges show legal next-move frequencies · this is not a neural network"
        "</text></svg></div>"
    )


def neural_network_concept_svg() -> str:
    layers = [
        (70, [71, 125, 179, 233], "#83b78a"),
        (285, [56, 99, 142, 185, 228, 271], "#709cba"),
        (500, [71, 125, 179, 233], "#aa8bc1"),
        (715, [71, 125, 179, 233], "#d3b46e"),
    ]
    connections = []
    for (left_x, left_ys, _), (right_x, right_ys, _) in zip(
        layers, layers[1:]
    ):
        for left_y in left_ys:
            for right_y in right_ys:
                connections.append(
                    f'<line x1="{left_x}" y1="{left_y}" x2="{right_x}" '
                    f'y2="{right_y}" stroke="#597061" stroke-opacity=".48" '
                    'stroke-width="1.5"/>'
                )

    nodes = []
    for x, ys, color in layers:
        nodes.extend(
            f'<circle cx="{x}" cy="{y}" r="11" fill="{color}" '
            'stroke="#e9f1e7" stroke-width="1.5"/>'
            for y in ys
        )
    labels = [
        (70, "Board input", "64 squares"),
        (285, "Hidden layer 1", "learned features"),
        (500, "Hidden layer 2", "position patterns"),
        (715, "Move output", "legal move scores"),
    ]
    headings = "".join(
        f'<text x="{x}" y="25" text-anchor="middle" fill="#eef4ed" '
        f'font-size="13" font-weight="700">{title}</text>'
        f'<text x="{x}" y="310" text-anchor="middle" fill="#a9b9ae" '
        f'font-size="11">{description}</text>'
        for x, title, description in labels
    )
    return (
        '<div style="background:#141e18;border:1px solid #2e4035;'
        'border-radius:12px;padding:8px;overflow:hidden">'
        '<svg viewBox="0 0 785 330" role="img" '
        'aria-label="Illustrative feed-forward chess neural network" '
        'style="width:100%;height:auto;font-family:Arial,sans-serif">'
        + "".join(connections)
        + "".join(nodes)
        + headings
        + "</svg></div>"
    )


def render_engine_analysis(board: chess.Board, engine_path: str) -> None:
    if st.button("Analyze current position", type="primary"):
        try:
            st.session_state["current_engine_analysis"] = {
                "fen": board.fen(),
                "lines": analyze_position(engine_path, board),
            }
            st.session_state.pop("current_engine_error", None)
        except (
            FileNotFoundError,
            OSError,
            chess.engine.EngineError,
            ValueError,
        ) as error:
            st.session_state["current_engine_error"] = str(error)
            st.session_state.pop("current_engine_analysis", None)

    error = st.session_state.get("current_engine_error")
    if error:
        st.error(error)

    result = st.session_state.get("current_engine_analysis")
    if not result or result["fen"] != board.fen():
        return
    if not result["lines"]:
        st.info("The engine returned no principal variation for this position.")
        return

    best = result["lines"][0]
    score = best["score"]
    score_value = score.score(mate_score=100_000)
    score_label = (
        f"M{score.mate()}" if score.is_mate() else f"{score_value / 100:+.2f}"
    )
    st.metric("Stockfish evaluation · White perspective", score_label)
    white = best["white_win_probability"]
    draw = best["draw_probability"]
    black = best["black_win_probability"]
    st.markdown(
        f"""
        <div style="display:flex;width:100%;height:18px;border-radius:9px;
        overflow:hidden;margin:6px 0 4px">
          <div title="White {white:.1%}" style="width:{white * 100:.2f}%;
          background:#e9e5d5"></div>
          <div title="Draw {draw:.1%}" style="width:{draw * 100:.2f}%;
          background:#87a578"></div>
          <div title="Black {black:.1%}" style="width:{black * 100:.2f}%;
          background:#27352c"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        f"Estimated outcome · White {white:.1%} · Draw {draw:.1%} · Black {black:.1%}"
    )

    st.markdown("**Top engine lines**")
    for index, line in enumerate(result["lines"], start=1):
        line_score = line["score"]
        centipawns = line_score.score(mate_score=100_000)
        score_text = (
            f"M{line_score.mate()}"
            if line_score.is_mate()
            else f"{centipawns / 100:+.2f}"
        )
        st.markdown(f"**{index}. {line['move']}** · `{score_text}`")
        st.code(line["line"], language=None)


if "game_board" not in st.session_state:
    st.session_state["game_mode_setting"] = "Stockfish"
    st.session_state["game_player_color_setting"] = "White"
    st.session_state["game_skill_level"] = 10
    st.session_state["game_promotion_choice"] = "Queen"
    new_game()

st.title("♞ Chess Studio")
st.caption("Play a complete game against Stockfish or another person.")

with st.sidebar:
    st.subheader("New game")
    st.selectbox(
        "Opponent",
        ["Stockfish", "Two players"],
        key="game_mode_setting",
        help="Stockfish is a chess engine. The dataset model is not used as an opponent.",
    )
    st.selectbox(
        "Play as",
        ["White", "Black"],
        key="game_player_color_setting",
        disabled=st.session_state["game_mode_setting"] == "Two players",
    )
    st.slider("Stockfish strength", 1, 20, key="game_skill_level")
    st.selectbox(
        "Pawn promotion",
        list(PROMOTION_PIECES),
        key="game_promotion_choice",
    )
    stockfish_path = st.text_input(
        "Stockfish executable path",
        value=os.environ.get("STOCKFISH_PATH", "stockfish"),
        help="Install Stockfish separately, then enter its executable name or full path.",
    )
    if st.session_state["game_mode_setting"] == "Stockfish":
        try:
            resolve_engine_path(stockfish_path.strip())
        except FileNotFoundError:
            st.warning(
                "Stockfish was not found. Install it and set its path, or select "
                "Two players."
            )
    st.button(
        "Start new game",
        on_click=new_game,
        type="primary",
        use_container_width=True,
    )
    if st.session_state["game_board"].move_stack:
        st.button("Undo last turn", on_click=undo_turn, use_container_width=True)
    st.caption("Opponent and color changes apply when you start a new game.")

board = st.session_state["game_board"]
mode = st.session_state["game_mode"]
player_color = st.session_state["game_player_color"]
status, detail = game_status(board)
board_column, info_column = st.columns([1.7, 0.8], gap="large")

with board_column:
    status_color = "#efba61" if detail == "Check" else "#a9b9ae"
    st.markdown(
        f'<div class="game-card"><strong style="font-size:1.15rem">'
        f'{html.escape(status)}</strong><span class="muted"> · '
        f'<span style="color:{status_color}">{html.escape(detail)}</span></span></div>',
        unsafe_allow_html=True,
    )
    draw_board(
        board,
        flipped=mode == "Stockfish" and player_color == chess.BLACK,
    )
    if st.session_state["game_last_san"]:
        st.caption(f"Last move: **{st.session_state['game_last_san']}**")
    st.download_button(
        "Download game as PGN",
        data=create_pgn(
            board,
            (
                "Player"
                if mode == "Stockfish" and player_color == chess.WHITE
                else "Stockfish"
                if mode == "Stockfish"
                else "Player 1"
            ),
            (
                "Player"
                if mode == "Stockfish" and player_color == chess.BLACK
                else "Stockfish"
                if mode == "Stockfish"
                else "Player 2"
            ),
        ),
        file_name="chess-game.pgn",
        mime="application/x-chess-pgn",
        use_container_width=True,
    )

with info_column:
    st.subheader("Game")
    if mode == "Stockfish":
        side = "White" if player_color == chess.WHITE else "Black"
        st.markdown(f"Playing **{side}** against Stockfish")
    else:
        st.markdown("Local two-player game")
    st.caption(f"Move {board.fullmove_number}")
    st.caption("Click a piece, then click one of its highlighted legal squares.")

    if board.is_game_over(claim_draw=False):
        if board.is_checkmate():
            st.success(f"Checkmate — {status}.")
        else:
            st.info(f"{status} by {detail.lower()}.")

    st.subheader("Moves")
    sans = st.session_state["game_moves"]
    if not sans:
        st.caption("Your game moves will appear here.")
    else:
        move_rows = []
        for index in range(0, len(sans), 2):
            black_move = sans[index + 1] if index + 1 < len(sans) else "…"
            move_rows.append(f"{index // 2 + 1}. {sans[index]}  {black_move}")
        st.code("\n".join(move_rows[-18:]), language=None)

    with st.expander("Move model visualization", expanded=False):
        st.caption(
            "This is the trained SAN continuation model, not a neural network. "
            "It counts legal next moves seen after recent move sequences."
        )
        with st.expander("Neural network architecture concept"):
            st.caption(
                "Illustration only: this neural network is not implemented or "
                "used to choose moves in this app."
            )
            st.markdown(neural_network_concept_svg(), unsafe_allow_html=True)
        if st.button("Visualize learned move patterns", key="visualize_move_model"):
            st.session_state["show_move_model"] = True
        if st.session_state.get("show_move_model") and MODEL_PATH.exists():
            try:
                move_model = load_move_model(
                    str(MODEL_PATH), MODEL_PATH.stat().st_mtime_ns
                )
                context, candidates = continuation_candidates(
                    move_model, sans, board, limit=5
                )
                st.markdown(
                    model_flow_svg(
                        int(move_model.get("training", {}).get("games_used", 0)),
                        context,
                        candidates,
                    ),
                    unsafe_allow_html=True,
                )
            except (OSError, json.JSONDecodeError, ValueError) as error:
                st.error(f"Could not load the move model visualization: {error}")
        elif not MODEL_PATH.exists():
            st.info(
                "Train the continuation model to show game-derived move frequencies."
            )
        else:
            st.caption("Select “Visualize learned move patterns” to load the local model.")

    with st.expander("Stockfish position analysis", expanded=True):
        st.caption(
            "Analyze the current board with Stockfish. Outcome bars are engine estimates, "
            "not guarantees."
        )
        render_engine_analysis(board, stockfish_path.strip())

    engine_error = st.session_state.get("game_engine_error")
    if engine_error:
        st.error(f"Stockfish could not make a move: {engine_error}")
        st.caption("Check its executable path in the sidebar, then start a new game.")

if (
    mode == "Stockfish"
    and not board.is_game_over(claim_draw=False)
    and board.turn != player_color
    and not st.session_state.get("game_engine_error")
):
    with st.spinner("Stockfish is thinking…"):
        try:
            san = play_engine_move(
                stockfish_path.strip(),
                board,
                st.session_state["game_skill_level"],
            )
            st.session_state["game_moves"].append(san)
            st.session_state["game_last_san"] = san
            st.session_state["game_selected_square"] = None
            st.rerun()
        except (
            FileNotFoundError,
            OSError,
            chess.engine.EngineError,
            ValueError,
        ) as error:
            st.session_state["game_engine_error"] = str(error)
            st.rerun()
