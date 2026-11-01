import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from datasets import load_dataset

from policy import build_policy


def save_policy(policy: dict[str, Any], output: Path, games_used: int) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    policy["training"] = {
        "source": "angeluriot/chess_games",
        "games_used": games_used,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    temporary_path = output.with_suffix(output.suffix + ".tmp")
    try:
        temporary_path.write_text(
            json.dumps(policy, separators=(",", ":")), encoding="utf-8"
        )
        temporary_path.replace(output)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train a SAN continuation model from the public chess-games dataset."
    )
    parser.add_argument("--max-games", type=int, default=50_000)
    parser.add_argument("--output", type=Path, default=Path("data/move_policy.json"))
    args = parser.parse_args()
    if args.max_games < 1:
        parser.error("--max-games must be at least 1")

    print("Loading angeluriot/chess_games in streaming mode...")
    records = load_dataset(
        "angeluriot/chess_games", split="train", streaming=True
    )
    policy, games_used, games_skipped, records_seen = build_policy(
        records, args.max_games
    )
    if records_seen == 0:
        raise RuntimeError(
            "The dataset stream returned no records. Check Hugging Face connectivity "
            "and that the dataset is available."
        )
    if games_used == 0:
        raise RuntimeError("No valid games were found; the model was not written.")

    save_policy(policy, args.output, games_used)
    print(
        f"Trained on {games_used:,} games "
        f"({games_skipped:,} invalid or unusable records skipped)."
    )
    print(f"Saved continuation model to {args.output}.")
    print(
        "The model predicts frequent legal dataset continuations; "
        "it does not evaluate positions or guarantee the best move."
    )
    print("Stockfish can optionally provide position evaluation and best-move analysis.")


if __name__ == "__main__":
    main()
