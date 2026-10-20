"""Tests for the A-Maze-ing generator, output format and configuration."""

from __future__ import annotations

from pathlib import Path

import pytest

from a_maze_ing import ConfigError, parse_config
from mazegen import EAST, NORTH, SOUTH, WEST, Cell
from mazegen import MazeError, MazeGenerator

DIRECTIONS = {
    "N": (0, -1),
    "E": (1, 0),
    "S": (0, 1),
    "W": (-1, 0),
}

WALL_STEPS = {
    NORTH: (0, -1),
    EAST: (1, 0),
    SOUTH: (0, 1),
    WEST: (-1, 0),
}


def _assert_coherent(maze: MazeGenerator) -> None:
    """Check that shared walls are encoded identically by both cells."""
    for y in range(maze.height):
        for x in range(maze.width):
            walls = maze.cells[y][x]
            if x + 1 < maze.width:
                assert bool(walls & EAST) == bool(
                    maze.cells[y][x + 1] & WEST
                )
            if y + 1 < maze.height:
                assert bool(walls & SOUTH) == bool(
                    maze.cells[y + 1][x] & NORTH
                )


def _has_open_3x3(maze: MazeGenerator) -> bool:
    """Return True when a 3x3 block has no internal walls."""
    for top in range(maze.height - 2):
        for left in range(maze.width - 2):
            open_block = True
            for y in range(top, top + 3):
                for x in range(left, left + 3):
                    if x < left + 2 and maze.cells[y][x] & EAST:
                        open_block = False
                    if y < top + 2 and maze.cells[y][x] & SOUTH:
                        open_block = False
            if open_block:
                return True
    return False


def _follow(maze: MazeGenerator, route: str) -> Cell:
    """Follow a NESW route from the entry and return the final cell."""
    x, y = maze.entry
    for letter in route:
        dx, dy = DIRECTIONS[letter]
        x += dx
        y += dy
    return (x, y)


def test_seed_is_reproducible() -> None:
    """The same seed must produce exactly the same maze."""
    first = MazeGenerator(12, 10, (0, 0), (11, 9), seed=7)
    second = MazeGenerator(12, 10, (0, 0), (11, 9), seed=7)
    first.generate()
    second.generate()
    assert first.cells == second.cells
    assert first.pattern_cells == second.pattern_cells


def test_perfect_maze_has_single_path() -> None:
    """A perfect maze is connected and contains no loop."""
    maze = MazeGenerator(
        12, 10, (0, 0), (11, 9), perfect=True, seed=3, draw_pattern=False
    )
    maze.generate()
    assert maze.is_perfect()
    assert maze.is_connected()
    assert maze.loop_count() == 0
    assert maze.solve()[0] == maze.entry
    assert maze.solve()[-1] == maze.exit
    _assert_coherent(maze)


def _is_forced_dead_end(maze: MazeGenerator, cell: Cell) -> bool:
    """Return True when a dead end cannot be braided any further."""
    x, y = cell
    for wall, (dx, dy) in WALL_STEPS.items():
        if not maze.cells[y][x] & wall:
            continue
        neighbour = (x + dx, y + dy)
        inside = (
            0 <= neighbour[0] < maze.width
            and 0 <= neighbour[1] < maze.height
        )
        if inside and neighbour not in maze.pattern_cells:
            return False
    return True


def test_playable_maze_is_braided() -> None:
    """Default mode has loops, no 3x3 open area and only forced dead ends."""
    maze = MazeGenerator(20, 15, (0, 0), (19, 14), seed=42)
    maze.generate()
    assert maze.is_connected()
    assert maze.loop_count() >= 2
    assert not _has_open_3x3(maze)
    for y in range(maze.height):
        for x in range(maze.width):
            cell = (x, y)
            if cell in maze.pattern_cells:
                continue
            if maze.open_degree(cell) == 1:
                assert _is_forced_dead_end(maze, cell)
    _assert_coherent(maze)


def test_braided_maze_without_pattern_has_no_dead_end() -> None:
    """Without the 42 glyph, braiding removes every dead end."""
    maze = MazeGenerator(
        14, 10, (0, 0), (13, 9), seed=8, draw_pattern=False
    )
    maze.generate()
    assert maze.is_connected()
    assert maze.loop_count() >= 2
    for y in range(maze.height):
        for x in range(maze.width):
            assert maze.open_degree((x, y)) != 1
    assert not _has_open_3x3(maze)


def test_42_pattern_is_closed() -> None:
    """Pattern cells must be fully closed and avoid entry and exit."""
    maze = MazeGenerator(20, 15, (0, 0), (19, 14), seed=42)
    maze.generate()
    assert maze.pattern_cells
    assert not maze.pattern_skipped
    for cell in maze.pattern_cells:
        x, y = cell
        assert maze.cells[y][x] == 15
    assert maze.entry not in maze.pattern_cells
    assert maze.exit not in maze.pattern_cells


def test_playable_center_and_corners_are_open() -> None:
    """Playable boards keep the centre and four corners passable."""
    maze = MazeGenerator(20, 15, (0, 0), (19, 14), seed=5)
    maze.generate()
    corners = {
        (0, 0),
        (maze.width - 1, 0),
        (0, maze.height - 1),
        (maze.width - 1, maze.height - 1),
    }
    center = (maze.width // 2, maze.height // 2)
    assert center not in maze.pattern_cells
    assert not (corners & maze.pattern_cells)


def test_small_maze_skips_pattern() -> None:
    """Mazes smaller than the pattern skip it without failing."""
    maze = MazeGenerator(4, 3, (0, 0), (3, 2), seed=1)
    maze.generate()
    assert maze.pattern_skipped
    assert maze.pattern_cells == set()
    assert maze.solve()


def test_playable_maze_keeps_center_open() -> None:
    """A board too small for the pattern keeps the centre open."""
    maze = MazeGenerator(7, 7, (0, 0), (6, 6), seed=0)
    maze.generate()
    center = (maze.width // 2, maze.height // 2)
    assert center not in maze.pattern_cells
    assert maze.pattern_skipped


def test_prim_algorithm_generates_valid_maze() -> None:
    """The alternative Prim algorithm produces a coherent perfect maze."""
    maze = MazeGenerator(
        9,
        7,
        (0, 0),
        (8, 6),
        perfect=True,
        seed=11,
        algorithm="prim",
        draw_pattern=False,
    )
    maze.generate()
    assert maze.is_perfect()
    _assert_coherent(maze)


def test_output_format() -> None:
    """The output file follows the mandatory hexadecimal format."""
    maze = MazeGenerator(8, 6, (0, 0), (7, 5), perfect=True, seed=9)
    maze.generate()
    lines = maze.to_output().splitlines()
    assert len(lines) == maze.height + 4
    assert lines[maze.height] == ""
    assert lines[maze.height + 1] == "0,0"
    assert lines[maze.height + 2] == "7,5"
    route = lines[maze.height + 3]
    assert set(route) <= set("NESW")
    assert _follow(maze, route) == maze.exit
    for row in lines[: maze.height]:
        assert len(row) == maze.width
        assert all(character in "0123456789ABCDEF" for character in row)


def test_write_output(tmp_path: Path) -> None:
    """Writing to disk produces a file ending with a newline."""
    maze = MazeGenerator(6, 5, (0, 0), (5, 4), seed=2)
    maze.generate()
    target = tmp_path / "maze.txt"
    maze.write_output(target)
    text = target.read_text(encoding="utf-8")
    assert text == maze.to_output()
    assert text.endswith("\n")


def test_invalid_parameters() -> None:
    """Invalid constructor arguments raise MazeError."""
    with pytest.raises(MazeError):
        MazeGenerator(0, 5, (0, 0), (0, 1))
    with pytest.raises(MazeError):
        MazeGenerator(5, 5, (0, 0), (0, 0))
    with pytest.raises(MazeError):
        MazeGenerator(5, 5, (0, 0), (5, 4))
    with pytest.raises(MazeError):
        MazeGenerator(5, 5, (0, 0), (4, 4), algorithm="unknown")


def test_parse_config(tmp_path: Path) -> None:
    """A valid configuration is parsed into the expected values."""
    path = tmp_path / "config.txt"
    path.write_text(
        "# comment\n"
        "WIDTH=8\n"
        "HEIGHT=6\n"
        "ENTRY=0,0\n"
        "EXIT=7,5\n"
        "OUTPUT_FILE=out.txt\n"
        "PERFECT=True\n"
        "SEED=123\n"
        "ALGORITHM=prim\n",
        encoding="utf-8",
    )
    config = parse_config(path)
    assert config.width == 8
    assert config.height == 6
    assert config.entry == (0, 0)
    assert config.exit == (7, 5)
    assert config.output_file == Path("out.txt")
    assert config.perfect is True
    assert config.seed == 123
    assert config.algorithm == "prim"


def test_parse_config_errors(tmp_path: Path) -> None:
    """Missing keys, bad values and out-of-bounds cells are rejected."""
    missing = tmp_path / "missing.txt"
    missing.write_text(
        "WIDTH=5\nHEIGHT=5\nENTRY=0,0\nEXIT=4,4\nOUTPUT_FILE=x.txt\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        parse_config(missing)

    outside = tmp_path / "outside.txt"
    outside.write_text(
        "WIDTH=5\nHEIGHT=5\nENTRY=0,0\nEXIT=9,4\n"
        "OUTPUT_FILE=x.txt\nPERFECT=False\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        parse_config(outside)

    bad_bool = tmp_path / "bad_bool.txt"
    bad_bool.write_text(
        "WIDTH=5\nHEIGHT=5\nENTRY=0,0\nEXIT=4,4\n"
        "OUTPUT_FILE=x.txt\nPERFECT=maybe\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        parse_config(bad_bool)

    too_thin = tmp_path / "too_thin.txt"
    too_thin.write_text(
        "WIDTH=1\nHEIGHT=6\nENTRY=0,0\nEXIT=0,5\n"
        "OUTPUT_FILE=x.txt\nPERFECT=False\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        parse_config(too_thin)


def test_missing_config_file(tmp_path: Path) -> None:
    """A missing configuration file gives a clear ConfigError."""
    with pytest.raises(ConfigError):
        parse_config(tmp_path / "does-not-exist.txt")
