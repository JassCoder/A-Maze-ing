*This project has been created as part of the 42 curriculum by JassCoder.*

# A-Maze-ing

## Description
A-Maze-ing is a Python maze generator project. Its goal is to generate valid mazes from a configuration file, export the maze in the required hexadecimal wall format, compute a shortest path between entry and exit, and provide a visual representation.

The project supports two generation modes:
- **PERFECT=True**: a perfect maze (single unique path between any two cells).
- **PERFECT=False**: a playable Pac-Man-like board with loops and mostly low dead-end density.

## Instructions

### Requirements
- Python **3.10+**

### Run
```bash
python3 a_maze_ing.py config.txt
```

### Expected Makefile targets
The project Makefile should provide:
- `install`
- `run`
- `debug`
- `clean`
- `lint` (`flake8 .` and required `mypy` flags)
- `lint-strict` (optional)

## Configuration File Format
The configuration file uses one `KEY=VALUE` per line.

Rules:
- Lines beginning with `#` are comments.
- Mandatory keys:
  - `WIDTH`
  - `HEIGHT`
  - `ENTRY` (`x,y`)
  - `EXIT` (`x,y`)
  - `OUTPUT_FILE`
  - `PERFECT` (`True`/`False`)
- Optional keys may include `SEED`, algorithm selection, and display mode.

Example:
```txt
# Minimal config
WIDTH=20
HEIGHT=15
ENTRY=0,0
EXIT=19,14
OUTPUT_FILE=maze.txt
PERFECT=True
SEED=42
```

## Generation Algorithm
Suggested baseline algorithm:
- Use a randomized depth-first search (recursive backtracker) to build a spanning tree over the grid.
- This naturally produces a perfect maze (`PERFECT=True`).
- For non-perfect mode, open additional selected walls to create multiple independent routes while preserving full connectivity and maze validity constraints.

## Why This Algorithm
- Simple to implement and reason about.
- Produces coherent cell-to-cell wall consistency by construction.
- Deterministic reproducibility is easy to support through a random seed.
- Provides a clean base for both perfect and non-perfect generation modes.

## Reusable Code
Maze generation must be implemented as a dedicated reusable class (e.g. `MazeGenerator`) that can be imported in future projects.

Reusable module expectations:
- Constructor accepts maze dimensions and optional generation settings (e.g. seed, mode).
- Public API exposes:
  - generated maze structure,
  - entry/exit coordinates,
  - at least one valid shortest solution path.
- Packaging artifacts should be buildable from repository sources and produce a `mazegen-*` package (`.whl` and/or `.tar.gz`).

## Team and Project Management
### Roles
- **JassCoder**: architecture, implementation, testing, packaging, and documentation.

### Initial plan
1. Parse/validate config and define data model.
2. Implement maze generator with deterministic seed support.
3. Implement pathfinding and output exporter.
4. Add visual rendering and interactions.
5. Add reusable package and project documentation.

### Evolution
- Documentation-first setup was used to lock requirements and expected interfaces before implementation.
- Validation requirements (format, coherence, and mode behavior) were prioritized to reduce rework.

### What worked well
- Clear separation between generation, analysis/pathfinding, and rendering.
- Requirement checklist in README to keep scope explicit.

### What can be improved
- Add automated unit tests earlier for edge cases (small grids, invalid configs, mode constraints).
- Expand CI checks as implementation grows.

### Tools used
- Python 3.10+
- flake8
- mypy
- (optional) pytest for local validation

## Resources
- Python documentation: https://docs.python.org/3/
- PEP 257 docstrings: https://peps.python.org/pep-0257/
- Graph theory and spanning trees (maze generation background)
- Recursive backtracker overview: https://en.wikipedia.org/wiki/Maze_generation_algorithm

### AI usage
AI was used to:
- structure the project documentation,
- convert specification constraints into checklist form,
- draft readable README sections and examples.

All generated content was manually reviewed and adjusted to keep it aligned with project requirements.
