# Chess-Engine Studio

A local chess game with a clickable board, legal move validation, Stockfish
opponent, adjustable engine strength, PGN export, and a local two-player mode.
It does not capture screens or connect to chess.com.

## Setup

```powershell
python -m pip install -r requirements.txt
```

Install Stockfish separately from [stockfishchess.org/download](https://stockfishchess.org/download/)
to play against the engine. Set `STOCKFISH_PATH` to its executable, or enter
the path in the app sidebar. Without Stockfish, you can still play a local
two-player game.

## Train the continuation model

The optional dataset trainer streams the dataset and uses at most 50,000 games
by default. It builds a move-continuation model for study; Stockfish, not this
dataset model, provides engine play:

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

Click a piece, then a highlighted legal square. Choose your side and engine
strength in the sidebar; settings apply to the next game. Completed games can
be downloaded as PGN.

The interactive board uses the PNG board texture and piece sprites in
`assets/chess/`.

The game panel includes an optional illustration of a neural-network
architecture (concept only; it is not used by the app), a data-backed view of
the actual move-frequency model, and Stockfish position analysis with
evaluation, candidate lines, and estimated outcomes.

The previous PGN study interface remains available separately:

```powershell
python -m streamlit run study_app.py
```
