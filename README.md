# Chess-Engine Studio

A local chess game with a clickable board, legal move validation, a trained
move-model opponent, optional Stockfish analysis, PGN export, and a local
two-player mode. It does not capture screens or connect to chess.com.

## Setup

```powershell
python -m pip install -r requirements.txt
```

The trained move model can play as an opponent and provide move suggestions.
Stockfish is optional and supplies position evaluation and best-move analysis.
Install Stockfish separately from
[stockfishchess.org/download](https://stockfishchess.org/download/) and set
`STOCKFISH_PATH` to its executable, or enter the path in the app sidebar.

## Train the continuation model

The dataset trainer streams the dataset and uses at most 50,000 games by
default. The resulting move-frequency model can play as an opponent and suggest
common legal continuations. It does not evaluate positions or guarantee the
best move; use optional Stockfish analysis for engine-ranked moves:

```powershell
python train_model.py
```

Choose another limit with `--max-games`:

```powershell
python train_model.py --max-games 100000
```

The model is written to `data/move_policy.json`.

## Run

```powershell
python -m streamlit run app.py
```

Click a piece, then a highlighted legal square. Choose the trained model,
Stockfish, or local two-player mode in the sidebar; settings apply to the next
game. Live games show learned move suggestions. Completed games can be
downloaded as PGN.

The interactive board uses the PNG board texture and piece sprites in
`assets/chess/`.

The game panel includes a data-backed view of the move-frequency model and
optional Stockfish position analysis with evaluation, candidate lines, and
estimated outcomes. The neural-network architecture illustration is only a
concept and is not used by the app.

Review a previous game by uploading its PGN in the separate study interface.
It shows the model's top learned move for each selected position and can
optionally request Stockfish analysis:

```powershell
python -m streamlit run study_app.py
```
