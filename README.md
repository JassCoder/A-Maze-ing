*This project has been created as part of the 42 curriculum by saini.*

# A-Maze-ing

## Description

A-Maze-ing is a maze generator written in Python. It reads a plain-text
configuration file, generates a rectangular maze, writes it to a file using
the mandatory hexadecimal wall encoding and displays it in the terminal.

Two modes are supported:

- **Perfect** (`PERFECT=True`): exactly one path exists between any two
  cells, so the entry-to-exit route is unique.
- **Playable** (`PERFECT=False`): the maze is braided into a Pac-Man-like
  board. Every corridor is reachable, the four corners and the centre stay
  open, there are several independent routes (loops), and dead ends are
  removed whenever the geometry allows it.

When the maze is large enough, a visible **42** is drawn with fully closed
cells in the middle of the board. If the maze is too small to fit the
pattern (or too small to fit it while keeping the centre open in playable
mode), the pattern is omitted and a warning is printed.

The generation logic lives in a reusable, dependency-free module called
`mazegen`, which is also shipped as a pip-installable wheel at the root of
the repository.

## Instructions

### Requirements

- Python 3.10 or later (standard library only at runtime)
- `flake8`, `mypy` and `pytest` for development checks
- `build` to rebuild the reusable package

Using a virtual environment is recommended:

```sh
python3 -m venv .venv
source .venv/bin/activate
make install
```

### Run

```sh
python3 a_maze_ing.py config.txt
```

The configuration file is the only required argument. The generated maze is
written to the file named by `OUTPUT_FILE`, then displayed in the terminal.
Running the program in a non-interactive terminal (for example in a pipe)
prints one frame and exits cleanly, which is convenient for automated tests.

### Makefile

| Target | Description |
| --- | --- |
| `make install` | Install the development tools (`build`, `flake8`, `mypy`, `pytest`) |
| `make run` | Run the generator with the default `config.txt` |
| `make debug` | Run the generator under `pdb` |
| `make clean` | Remove caches and build artifacts |
| `make lint` | Run `flake8 .` and the mandatory `mypy` command |
| `make lint-strict` | Run `flake8 .` and `mypy . --strict` |
| `make test` | Run the test suite |
| `make package` | Build the `mazegen` wheel and copy it to the repository root |

### Terminal controls

The interactive display supports:

| Key | Action |
| --- | --- |
| `r` | Regenerate a new maze and update the output file |
| `p` | Show or hide the shortest entry-to-exit path |
| `c` | Cycle through wall colours |
| `4` | Highlight or dim the `42` pattern |
| `q` / `Esc` | Quit |

Entry is shown as `S`, exit as `E`, the solution as `*`, and the `42` blocks
as `###`.

## Configuration file format

The configuration file contains one `KEY=VALUE` pair per line. Empty lines
and lines starting with `#` are ignored. Inline comments starting with `#`
are also accepted.

| Key | Mandatory | Description | Example |
| --- | --- | --- | --- |
| `WIDTH` | yes | Maze width in cells | `WIDTH=20` |
| `HEIGHT` | yes | Maze height in cells | `HEIGHT=15` |
| `ENTRY` | yes | Entry coordinates `x,y` | `ENTRY=0,0` |
| `EXIT` | yes | Exit coordinates `x,y` | `EXIT=19,14` |
| `OUTPUT_FILE` | yes | Output filename | `OUTPUT_FILE=maze.txt` |
| `PERFECT` | yes | `True` for a perfect maze, `False` for a playable board | `PERFECT=True` |
| `SEED` | no | Integer seed for reproducible generation | `SEED=42` |
| `ALGORITHM` | no | `backtracker` (default) or `prim` | `ALGORITHM=prim` |

Coordinates are zero-based: `(0, 0)` is the top-left cell and
`(WIDTH-1, HEIGHT-1)` the bottom-right one. Entry and exit must be different
and inside the maze.

Example (`config.txt` in this repository):

```ini
# A-Maze-ing default configuration
WIDTH=20
HEIGHT=15
ENTRY=0,0
EXIT=19,14
OUTPUT_FILE=maze.txt
PERFECT=False

SEED=42
ALGORITHM=backtracker
```

### Output file format

- One hexadecimal digit per cell, row by row, one row per line.
- Bits encode closed walls: `1` North, `2` East, `4` South, `8` West.
- After an empty line: entry coordinates, exit coordinates and the shortest
  path using `N`, `E`, `S` and `W`.
- Every line ends with `\n`.

Example:

```text
F3F3...
...
0,0
19,14
EESSW...
```

## Maze generation

### Algorithms

- **Randomized depth-first search / recursive backtracker** (default):
  iterative, starts at the entry, carves a corridor to a random unvisited
  neighbour and backtracks when stuck.
- **Randomized Prim**: grows the maze from the entry by repeatedly choosing
  a random wall on the frontier of the visited region.

Both algorithms produce a spanning tree over all open cells, which is exactly
a perfect maze.

### Why these algorithms

The recursive backtracker is simple, iterative (no recursion-limit issues),
fast, and produces long winding corridors, which look good in the terminal.
Prim was added as a second, contrasting algorithm: it creates shorter
branches and demonstrates that the generator is not tied to one strategy.
Both are seeded with `random.Random(seed)`, so a given seed always produces
the same maze.

### Playable mode

`PERFECT=False` starts from a perfect maze and then *braids* it: every dead
end (cell with a single opening) gets an extra wall removed to connect it to
another corridor. This creates loops and removes dead ends. The braiding code
refuses to create a fully open 3x3 block, so corridors stay at most two cells
wide. A final pass guarantees at least two independent loops when the maze is
large enough. The playable mode also keeps the four corners and the centre
passable, as required for a Pac-Man-like board.

### The 42 pattern

The pattern is defined as a small bitmap (`PATTERN_ROWS` in `mazegen.py`).
The generator tries several placements around the centre and keeps the first
one that:

1. does not cover the entry or exit,
2. does not cover the corners,
3. keeps the centre open in playable mode,
4. does not split the remaining open cells into disconnected regions.

The selected cells are initialized with all four walls closed and are never
carved, so they are fully closed cells in the output.

## Reusable module

The complete generator is the single file `mazegen.py`. It is documented with
a module docstring and PEP 257 docstrings, has no third-party dependency, and
is typed so it passes `mypy --strict`.

### Use it

```python
from mazegen import MazeGenerator

maze = MazeGenerator(
    width=20,
    height=15,
    entry=(0, 0),
    exit=(19, 14),
    perfect=True,       # or False for a playable board
    seed=42,            # optional, for reproducibility
    algorithm="backtracker",
)
maze.generate()

# Access the structure: cells[y][x] is a bitmask of closed walls
for row in maze.cells:
    print("".join(format(cell, "X") for cell in row))

# Access a solution
path = maze.solve()                  # [(x, y), ...]
directions = maze.path_directions()  # "EESSW..."
print(directions)
print(maze.to_output())              # full A-Maze-ing output
maze.write_output("maze.txt")
```

Useful public attributes and methods:

- `cells`: the wall bitmasks (`cells[y][x]`).
- `pattern_cells`: the cells occupied by the `42`.
- `pattern_skipped`: `True` when the pattern could not be placed.
- `open_degree(cell)`, `loop_count()`, `is_connected()`, `is_perfect()`.
- `solve()`, `path_directions()`, `to_hex_rows()`, `to_output()`,
  `write_output(path)`.

### Install the packaged module

A ready-to-install wheel is provided at the repository root:

```sh
python3 -m pip install mazegen-1.0.0-py3-none-any.whl
```

Rebuild it from the sources with:

```sh
python3 -m build --wheel
cp dist/mazegen-*.whl .
```

The package sources are `mazegen.py` plus `pyproject.toml`. The module is
distributed under the MIT license (see `LICENSE.md`), which explicitly allows
reuse and redistribution in later projects.

## Tests

The `tests/` directory contains unit tests for:

- seed reproducibility,
- coherent wall encoding between neighbours,
- perfect-maze properties (single path, no loop),
- playable-board properties (loops, no avoidable dead ends, no 3x3 open area),
- the `42` pattern and small-maze fallback,
- hexadecimal output format and path validity,
- configuration parsing and error handling.

Run them with:

```sh
make test
```

## Bonuses implemented

- A second generation algorithm (`ALGORITHM=prim`).
- A braided playable board with multiple loops and no avoidable dead ends.
- Coloured terminal rendering with a hide/show solution path and a
  highlighted/dimmed `42` pattern.
- Keyboard-driven regeneration without restarting the program.

## Resources

- Jamis Buck, *Mazes for Programmers* and his article series
  “Maze Generation: Algorithm Recap”
  <https://weblog.jamisbuck.org/2011/2/7/maze-generation-algorithm-recap.html>
- Wikipedia, “Maze generation algorithm”
  <https://en.wikipedia.org/wiki/Maze_generation_algorithm>
- Red Blob Games, “Introduction to A*” and grid pathfinding notes
  <https://www.redblobgames.com/pathfinding/a-star/introduction.html>
- Python documentation, `random`, `collections.deque`, `argparse`, `termios`
  <https://docs.python.org/3/library/>
- 42 A-Maze-ing subject (version 2.3) and the provided `maze_analyzer.py`
  description.

### AI usage

AI was used as a development assistant for:

- drafting the initial project structure and the `mazegen` API,
- reviewing algorithm choices (backtracker vs. Prim) and the braiding rules,
- suggesting edge cases for the tests (small mazes, wall coherence,
  perfect/playable validation),
- drafting this README and the packaging metadata.

All generated content was reviewed, executed and tested locally. The
algorithm implementations, the 3x3 open-area guard, the pattern placement
rules and the terminal interactions were checked with the unit tests and
with several maze sizes and seeds. No AI-generated code was submitted
without being understood and verified.

## Team and project management

### Roles

This is a solo project.

- **Developer**: maze generation, braiding, pattern placement, output format.
- **Tester**: unit tests, property checks across sizes/seeds, linting and
  type checking.
- **Documentation and packaging**: README, license, `pyproject.toml`, wheel.

### Planning and how it evolved

The first plan was a single script with a recursive backtracker and a simple
ASCII renderer. While implementing the mandatory parts, the plan grew to:

1. separate the reusable `mazegen` module from the CLI,
2. add the playable braided mode and the 3x3 open-area guard,
3. make pattern placement connectivity-aware,
4. add type hints, tests and packaging,
5. add a second algorithm and richer terminal controls as bonuses.

The main adjustment was the `42` placement: on short boards the pattern and
the open-centre requirement conflict, so the generator now prefers the
playable-board constraint and omits the pattern with a warning.

### What worked well

- Separating the generator from the display made both easier to test.
- Seeded generation made bugs reproducible.
- Property tests across many sizes caught the pattern/border dead-end cases.
- The iterative backtracker avoids recursion limits on large mazes.

### What could be improved

- A graphical MiniLibX renderer could complement the terminal display.
- Generation animation could make the carving process visible.
- A stronger braiding heuristic could remove the few remaining dead ends
  that are forced by the shape of the `42` and the borders.

### Tools

Python 3, `flake8`, `mypy`, `pytest`, `build`/`setuptools`, Git, a terminal
with ANSI colours, and AI assistance as described above.
