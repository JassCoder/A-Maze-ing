"""Reusable, dependency-free maze generator.

This single-file module provides :class:`MazeGenerator`, a standalone
implementation that can be imported by any Python project and installed
with ``pip`` after building the ``mazegen`` wheel.

Features
--------
* Rectangular mazes with cells addressed as ``(x, y)``.
* Two generation algorithms: randomized depth-first search (``backtracker``)
  and randomized Prim (``prim``).
* Perfect mazes (a single path between any two cells) or playable,
  braided boards with loops and no dead ends.
* Reproducible output through an optional seed.
* The optional ``42`` pattern, drawn with fully closed cells.
* Shortest-path solving and serialisation to the A-Maze-ing hexadecimal
  output format.

Basic usage
-----------
::

    from mazegen import MazeGenerator

    maze = MazeGenerator(
        width=20,
        height=15,
        entry=(0, 0),
        exit=(19, 14),
        perfect=True,
        seed=42,
    )
    maze.generate()

    walls = maze.cells          # cells[y][x] -> wall bitmask
    path = maze.solve()         # [(x, y), ...] from entry to exit
    route = maze.path_directions()  # "EESSW..."
    print(maze.to_output())     # hexadecimal A-Maze-ing format

Wall bitmask
------------
Each cell stores four bits, one per cardinal direction.  A set bit means
that the wall is closed::

    1 = North, 2 = East, 4 = South, 8 = West

The same encoding is used by the A-Maze-ing output file.
"""

from __future__ import annotations

import random
from collections import deque
from pathlib import Path

NORTH = 1
EAST = 2
SOUTH = 4
WEST = 8

Cell = tuple[int, int]

DIRECTIONS: dict[int, tuple[int, int]] = {
    NORTH: (0, -1),
    EAST: (1, 0),
    SOUTH: (0, 1),
    WEST: (-1, 0),
}

OPPOSITE: dict[int, int] = {
    NORTH: SOUTH,
    EAST: WEST,
    SOUTH: NORTH,
    WEST: EAST,
}

PATTERN_ROWS: tuple[str, ...] = (
    "#..#.###",
    "#..#...#",
    "####.###",
    "...#.#..",
    "...#.###",
)
_PATTERN_WIDTH = len(PATTERN_ROWS[0])
_PATTERN_HEIGHT = len(PATTERN_ROWS)


class MazeError(ValueError):
    """Raised when maze parameters are invalid or generation fails."""


def _is_cell(value: object) -> bool:
    """Return ``True`` when *value* looks like an ``(x, y)`` tuple."""
    return (
        isinstance(value, tuple)
        and len(value) == 2
        and all(isinstance(item, int) for item in value)
    )


class MazeGenerator:
    """Generate, solve and export a rectangular maze.

    Parameters
    ----------
    width:
        Number of cells horizontally (must be positive).
    height:
        Number of cells vertically (must be positive).
    entry:
        Entry cell as ``(x, y)``.
    exit:
        Exit cell as ``(x, y)``; it must differ from *entry*.
    perfect:
        When ``True`` the maze has exactly one path between any two cells.
        When ``False`` the maze is braided into a Pac-Man-like board with
        loops and (when possible) no dead ends.
    seed:
        Optional seed used to make generation reproducible.
    algorithm:
        ``"backtracker"`` (default) or ``"prim"``.
    draw_pattern:
        When ``True`` (default) the ``42`` pattern is drawn whenever the
        maze is large enough.

    Attributes
    ----------
    cells:
        ``cells[y][x]`` holds the wall bitmask of a cell.  Empty until
        :meth:`generate` has been called.
    pattern_cells:
        Cells occupied by the ``42`` pattern (fully closed cells).
    pattern_skipped:
        ``True`` when the pattern was requested but the maze is too small
        (or the pattern could not be placed without splitting the maze).
    """

    def __init__(
        self,
        width: int,
        height: int,
        entry: Cell,
        exit: Cell,
        perfect: bool = False,
        seed: int | None = None,
        algorithm: str = "backtracker",
        draw_pattern: bool = True,
    ) -> None:
        if not isinstance(width, int) or not isinstance(height, int):
            raise MazeError("maze dimensions must be integers")
        if width < 1 or height < 1:
            raise MazeError("maze dimensions must be positive")
        if not _is_cell(entry) or not _is_cell(exit):
            raise MazeError("entry and exit must be (x, y) tuples")
        if entry == exit:
            raise MazeError("entry and exit must be different cells")
        for label, cell in (("entry", entry), ("exit", exit)):
            x, y = cell
            if not (0 <= x < width and 0 <= y < height):
                raise MazeError(
                    f"{label} {cell} is outside the maze "
                    f"({width}x{height})"
                )
        normalized = algorithm.strip().lower()
        aliases = {
            "dfs": "backtracker",
            "recursive-backtracker": "backtracker",
            "randomized-prim": "prim",
        }
        normalized = aliases.get(normalized, normalized)
        if normalized not in {"backtracker", "prim"}:
            raise MazeError(
                "algorithm must be 'backtracker' or 'prim', "
                f"got {algorithm!r}"
            )
        if seed is not None and not isinstance(seed, int):
            raise MazeError("seed must be an integer or None")

        self.width = width
        self.height = height
        self.entry = entry
        self.exit = exit
        self.perfect = bool(perfect)
        self.seed = seed
        self.algorithm = normalized
        self.draw_pattern = bool(draw_pattern)

        self.cells: list[list[int]] = []
        self.pattern_cells: set[Cell] = set()
        self.pattern_skipped = False

        self._passable: set[Cell] = set()
        self._rng = random.Random(seed)
        self._solution: list[Cell] | None = None

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------
    def generate(self) -> None:
        """Generate a new maze, replacing any previous one."""
        self._rng = random.Random(self.seed)
        self.pattern_cells = self._place_pattern()
        self.pattern_skipped = (
            self.draw_pattern and not bool(self.pattern_cells)
        )
        self._passable = self._all_cells() - self.pattern_cells
        if self.entry not in self._passable:
            raise MazeError("entry cell is blocked by the 42 pattern")
        if self.exit not in self._passable:
            raise MazeError("exit cell is blocked by the 42 pattern")

        self.cells = [
            [NORTH | EAST | SOUTH | WEST for _ in range(self.width)]
            for _ in range(self.height)
        ]
        self._solution = None

        if self.algorithm == "backtracker":
            self._generate_backtracker()
        else:
            self._generate_prim()

        if len(self._passable) > 1 and not self.is_connected():
            raise MazeError("generated maze is not fully connected")

        if not self.perfect:
            self._braid()
            self._ensure_loops(2)

    def _generate_backtracker(self) -> None:
        """Carve a perfect maze with an iterative randomized DFS."""
        start = self.entry
        visited = {start}
        stack = [start]
        while stack:
            current = stack[-1]
            options = [
                (wall, neighbour)
                for wall, neighbour in self._neighbours(current)
                if neighbour not in visited
            ]
            if not options:
                stack.pop()
                continue
            _, neighbour = self._rng.choice(options)
            self._open(current, neighbour)
            visited.add(neighbour)
            stack.append(neighbour)

    def _generate_prim(self) -> None:
        """Carve a perfect maze with randomized Prim's algorithm."""
        start = self.entry
        visited = {start}
        frontier: list[tuple[Cell, Cell]] = [
            (start, neighbour)
            for _, neighbour in self._neighbours(start)
        ]
        while frontier:
            index = self._rng.randrange(len(frontier))
            current, neighbour = frontier.pop(index)
            if neighbour in visited:
                continue
            self._open(current, neighbour)
            visited.add(neighbour)
            for _, candidate in self._neighbours(neighbour):
                if candidate not in visited:
                    frontier.append((neighbour, candidate))

    def _braid(self) -> None:
        """Remove dead ends by opening extra walls, creating loops."""
        max_rounds = self.width * self.height + 10
        for _ in range(max_rounds):
            dead_ends = [
                cell
                for cell in sorted(self._passable)
                if self.open_degree(cell) <= 1
            ]
            if not dead_ends:
                return
            progressed = False
            self._rng.shuffle(dead_ends)
            for cell in dead_ends:
                if self.open_degree(cell) != 1:
                    continue
                x, y = cell
                options = [
                    neighbour
                    for wall, neighbour in self._neighbours(cell)
                    if self.cells[y][x] & wall
                ]
                self._rng.shuffle(options)
                for neighbour in options:
                    if self._try_open(cell, neighbour):
                        progressed = True
                        break
            if not progressed:
                return

    def _ensure_loops(self, minimum: int) -> None:
        """Open extra walls until the maze has *minimum* independent loops."""
        while self.loop_count() < minimum:
            candidates: list[tuple[Cell, Cell]] = []
            for cell in sorted(self._passable):
                x, y = cell
                for wall, neighbour in self._neighbours(cell):
                    if self.cells[y][x] & wall:
                        candidates.append((cell, neighbour))
            if not candidates:
                return
            self._rng.shuffle(candidates)
            opened = False
            for first, second in candidates:
                if self._try_open(first, second):
                    opened = True
                    break
            if not opened:
                return

    # ------------------------------------------------------------------
    # Wall helpers
    # ------------------------------------------------------------------
    def _open(self, first: Cell, second: Cell) -> None:
        """Remove the wall between two adjacent cells."""
        direction = self._direction(first, second)
        first_x, first_y = first
        second_x, second_y = second
        self.cells[first_y][first_x] &= ~direction
        self.cells[second_y][second_x] &= ~OPPOSITE[direction]

    def _close(self, first: Cell, second: Cell) -> None:
        """Put the wall between two adjacent cells back."""
        direction = self._direction(first, second)
        first_x, first_y = first
        second_x, second_y = second
        self.cells[first_y][first_x] |= direction
        self.cells[second_y][second_x] |= OPPOSITE[direction]

    def _try_open(self, first: Cell, second: Cell) -> bool:
        """Open a wall unless it would create a forbidden 3x3 open area."""
        direction = self._direction(first, second)
        first_x, first_y = first
        if not self.cells[first_y][first_x] & direction:
            return False
        self._open(first, second)
        if self._has_open_3x3(first, second):
            self._close(first, second)
            return False
        return True

    def _has_open_3x3(self, first: Cell, second: Cell) -> bool:
        """Return ``True`` if the last opening created a 3x3 open area."""
        if self.width < 3 or self.height < 3:
            return False
        min_left = max(0, max(first[0], second[0]) - 2)
        max_left = min(self.width - 3, min(first[0], second[0]))
        min_top = max(0, max(first[1], second[1]) - 2)
        max_top = min(self.height - 3, min(first[1], second[1]))
        for left in range(min_left, max_left + 1):
            for top in range(min_top, max_top + 1):
                if self._block_is_open(left, top):
                    return True
        return False

    def _block_is_open(self, left: int, top: int) -> bool:
        """Return ``True`` when a 3x3 block has no internal walls."""
        for y in range(top, top + 3):
            for x in range(left, left + 3):
                if x < left + 2 and self.cells[y][x] & EAST:
                    return False
                if y < top + 2 and self.cells[y][x] & SOUTH:
                    return False
        return True

    @staticmethod
    def _direction(first: Cell, second: Cell) -> int:
        """Return the wall bit separating two adjacent cells."""
        delta = (second[0] - first[0], second[1] - first[1])
        for wall, offset in DIRECTIONS.items():
            if delta == offset:
                return wall
        raise MazeError(f"cells {first} and {second} are not adjacent")

    def _neighbours(self, cell: Cell) -> list[tuple[int, Cell]]:
        """Return ``(wall, neighbour)`` pairs for passable neighbours."""
        x, y = cell
        result: list[tuple[int, Cell]] = []
        for wall, (dx, dy) in DIRECTIONS.items():
            neighbour = (x + dx, y + dy)
            if neighbour in self._passable:
                result.append((wall, neighbour))
        return result

    # ------------------------------------------------------------------
    # Inspection and solving
    # ------------------------------------------------------------------
    def open_degree(self, cell: Cell) -> int:
        """Return how many walls of *cell* are open (0 to 4)."""
        self._require_generated()
        x, y = cell
        degree = 0
        for wall in DIRECTIONS:
            if not self.cells[y][x] & wall:
                degree += 1
        return degree

    def solve(self) -> list[Cell]:
        """Return the shortest entry-to-exit path as a list of cells."""
        self._require_generated()
        if self._solution is not None:
            return list(self._solution)

        start = self.entry
        goal = self.exit
        previous: dict[Cell, Cell | None] = {start: None}
        queue: deque[Cell] = deque([start])

        while queue:
            current = queue.popleft()
            if current == goal:
                break
            x, y = current
            for wall, neighbour in self._neighbours(current):
                if self.cells[y][x] & wall:
                    continue
                if neighbour in previous:
                    continue
                previous[neighbour] = current
                queue.append(neighbour)

        if goal not in previous:
            raise MazeError("exit is not reachable from entry")

        path: list[Cell] = []
        cursor: Cell | None = goal
        while cursor is not None:
            path.append(cursor)
            cursor = previous[cursor]
        path.reverse()
        self._solution = path
        return list(path)

    def path_directions(self) -> str:
        """Return the shortest path as a string of ``N``/``E``/``S``/``W``."""
        path = self.solve()
        letters: list[str] = []
        for first, second in zip(path, path[1:]):
            dx = second[0] - first[0]
            dy = second[1] - first[1]
            if dy == -1:
                letters.append("N")
            elif dx == 1:
                letters.append("E")
            elif dy == 1:
                letters.append("S")
            elif dx == -1:
                letters.append("W")
            else:
                raise MazeError("shortest path contains non-adjacent cells")
        return "".join(letters)

    def loop_count(self) -> int:
        """Return the number of independent loops in the maze."""
        self._require_generated()
        edges = 0
        for y in range(self.height):
            for x in range(self.width):
                walls = self.cells[y][x]
                if not walls & EAST and x + 1 < self.width:
                    edges += 1
                if not walls & SOUTH and y + 1 < self.height:
                    edges += 1
        return edges - len(self._passable) + 1

    def is_connected(self) -> bool:
        """Return ``True`` when every passable cell can be reached."""
        self._require_generated()
        return self._region_connected(self._passable)

    def is_perfect(self) -> bool:
        """Return ``True`` when the maze is connected and has no loop."""
        return self.is_connected() and self.loop_count() == 0

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------
    def to_hex_rows(self) -> list[str]:
        """Return one hexadecimal string per maze row."""
        self._require_generated()
        return [
            "".join(format(walls, "X") for walls in row)
            for row in self.cells
        ]

    def to_output(self) -> str:
        """Return the complete A-Maze-ing output file content."""
        self._require_generated()
        rows = self.to_hex_rows()
        entry = f"{self.entry[0]},{self.entry[1]}"
        exit_cell = f"{self.exit[0]},{self.exit[1]}"
        lines = rows + ["", entry, exit_cell, self.path_directions()]
        return "\n".join(lines) + "\n"

    def write_output(self, path: str | Path) -> None:
        """Write the A-Maze-ing output format to *path*."""
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(self.to_output())

    # ------------------------------------------------------------------
    # 42 pattern
    # ------------------------------------------------------------------
    def _place_pattern(self) -> set[Cell]:
        """Choose the best placement for the 42 pattern, if possible."""
        if not self.draw_pattern:
            return set()
        if self.width < _PATTERN_WIDTH or self.height < _PATTERN_HEIGHT:
            return set()

        base_left = (self.width - _PATTERN_WIDTH) // 2
        base_top = (self.height - _PATTERN_HEIGHT) // 2
        positions: list[tuple[int, int]] = []
        seen: set[tuple[int, int]] = set()
        for dy in range(-(_PATTERN_HEIGHT + 1), _PATTERN_HEIGHT + 2):
            for dx in range(-(_PATTERN_WIDTH + 1), _PATTERN_WIDTH + 2):
                left = base_left + dx
                top = base_top + dy
                if not (
                    0 <= left <= self.width - _PATTERN_WIDTH
                    and 0 <= top <= self.height - _PATTERN_HEIGHT
                ):
                    continue
                position = (left, top)
                if position not in seen:
                    seen.add(position)
                    positions.append(position)
        positions.sort(
            key=lambda item: (
                abs(item[0] - base_left) + abs(item[1] - base_top),
                item[1],
                item[0],
            )
        )

        center = (self.width // 2, self.height // 2)
        corners = {
            (0, 0),
            (self.width - 1, 0),
            (0, self.height - 1),
            (self.width - 1, self.height - 1),
        }
        all_cells = self._all_cells()
        # In playable mode the centre must stay open, so do not fall back
        # to a placement that covers it.  If no such placement exists the
        # pattern is omitted (the maze is too small for both constraints).
        require_center = not self.perfect

        for left, top in positions:
            pattern = self._pattern_at(left, top)
            if self.entry in pattern or self.exit in pattern:
                continue
            if pattern & corners:
                continue
            if require_center and center in pattern:
                continue
            region = all_cells - pattern
            if not self._region_connected(region):
                continue
            return pattern
        return set()

    @staticmethod
    def _pattern_at(left: int, top: int) -> set[Cell]:
        """Return the cells covered by the pattern at a position."""
        cells: set[Cell] = set()
        for offset_y, row in enumerate(PATTERN_ROWS):
            for offset_x, value in enumerate(row):
                if value == "#":
                    cells.add((left + offset_x, top + offset_y))
        return cells

    # ------------------------------------------------------------------
    # Internal utilities
    # ------------------------------------------------------------------
    def _all_cells(self) -> set[Cell]:
        """Return every cell in the grid."""
        return {
            (x, y)
            for y in range(self.height)
            for x in range(self.width)
        }

    @staticmethod
    def _region_connected(region: set[Cell]) -> bool:
        """Return ``True`` when all cells of *region* are connected."""
        if not region:
            return True
        start = next(iter(region))
        seen = {start}
        stack = [start]
        while stack:
            x, y = stack.pop()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                neighbour = (x + dx, y + dy)
                if neighbour in region and neighbour not in seen:
                    seen.add(neighbour)
                    stack.append(neighbour)
        return len(seen) == len(region)

    def _require_generated(self) -> None:
        """Raise an error when the maze has not been generated yet."""
        if not self.cells:
            raise MazeError("call generate() before using the maze")
