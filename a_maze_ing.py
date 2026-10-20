"""A-Maze-ing: terminal maze generator.

Usage::

    python3 a_maze_ing.py config.txt

The configuration file must contain one ``KEY=VALUE`` pair per line,
comments start with ``#``, and the following keys are mandatory:
``WIDTH``, ``HEIGHT``, ``ENTRY``, ``EXIT``, ``OUTPUT_FILE`` and ``PERFECT``.

Optional keys: ``SEED`` (integer) and ``ALGORITHM`` (``backtracker`` or
``prim``).  See ``README.md`` for the complete documentation.
"""

from __future__ import annotations

import argparse
import random
import sys
import termios
import tty
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from mazegen import NORTH, EAST, SOUTH, WEST
from mazegen import Cell, MazeError, MazeGenerator

REQUIRED_KEYS = (
    "WIDTH",
    "HEIGHT",
    "ENTRY",
    "EXIT",
    "OUTPUT_FILE",
    "PERFECT",
)
OPTIONAL_KEYS = ("SEED", "ALGORITHM")

_RESET = "\x1b[0m"
_WALL_COLORS = (
    "\x1b[96m",
    "\x1b[95m",
    "\x1b[93m",
    "\x1b[92m",
    "\x1b[94m",
    "\x1b[97m",
)
_WALL_COLOR_NAMES = ("cyan", "magenta", "yellow", "green", "blue", "white")
_ENTRY_COLOR = "\x1b[92m"
_EXIT_COLOR = "\x1b[91m"
_PATH_COLOR = "\x1b[93m"
_PATTERN_BRIGHT = "\x1b[95m"
_PATTERN_DIM = "\x1b[90m"


class ConfigError(Exception):
    """Raised when the configuration file is missing or invalid."""


@dataclass(frozen=True)
class Config:
    """Validated maze configuration."""

    width: int
    height: int
    entry: Cell
    exit: Cell
    output_file: Path
    perfect: bool
    seed: int | None = None
    algorithm: str = "backtracker"


def _parse_int(key: str, value: str, minimum: int | None = None) -> int:
    """Parse an integer configuration value."""
    try:
        number = int(value, 10)
    except ValueError as exc:
        raise ConfigError(
            f"{key} must be an integer, got {value!r}"
        ) from exc
    if minimum is not None and number < minimum:
        raise ConfigError(f"{key} must be at least {minimum}")
    return number


def _parse_bool(key: str, value: str) -> bool:
    """Parse a boolean configuration value."""
    truthy = {"true", "1", "yes", "on"}
    falsy = {"false", "0", "no", "off"}
    lowered = value.strip().lower()
    if lowered in truthy:
        return True
    if lowered in falsy:
        return False
    raise ConfigError(
        f"{key} must be True or False, got {value!r}"
    )


def _parse_cell(key: str, value: str) -> Cell:
    """Parse an ``x,y`` coordinate pair."""
    parts = value.split(",")
    if len(parts) != 2:
        raise ConfigError(
            f"{key} must use the x,y format, got {value!r}"
        )
    try:
        x = int(parts[0].strip(), 10)
        y = int(parts[1].strip(), 10)
    except ValueError as exc:
        raise ConfigError(
            f"{key} coordinates must be integers, got {value!r}"
        ) from exc
    return (x, y)


def parse_config(path: Path) -> Config:
    """Read and validate a configuration file."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigError(
            f"configuration file not found: {path}"
        ) from exc
    except OSError as exc:
        raise ConfigError(
            f"cannot read configuration file {path}: {exc.strerror}"
        ) from exc

    text = text.lstrip("\ufeff")
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if "=" not in line:
            raise ConfigError(
                f"line {line_number}: expected KEY=VALUE, got {raw_line!r}"
            )
        key, value = line.split("=", 1)
        key = key.strip().upper()
        value = value.strip()
        if not key:
            raise ConfigError(f"line {line_number}: empty key")
        if not value:
            raise ConfigError(
                f"line {line_number}: empty value for {key}"
            )
        if key in values:
            raise ConfigError(f"duplicate key {key} on line {line_number}")
        values[key] = value

    missing = [key for key in REQUIRED_KEYS if key not in values]
    if missing:
        raise ConfigError(
            "missing mandatory key(s): " + ", ".join(missing)
        )

    for key in values:
        if key not in REQUIRED_KEYS and key not in OPTIONAL_KEYS:
            print(
                f"Warning: ignoring unknown configuration key {key!r}",
                file=sys.stderr,
            )

    width = _parse_int("WIDTH", values["WIDTH"], minimum=1)
    height = _parse_int("HEIGHT", values["HEIGHT"], minimum=1)
    if width * height < 2:
        raise ConfigError(
            "the maze must contain at least two cells "
            "so entry and exit can differ"
        )

    entry = _parse_cell("ENTRY", values["ENTRY"])
    exit_cell = _parse_cell("EXIT", values["EXIT"])
    for label, cell in (("ENTRY", entry), ("EXIT", exit_cell)):
        x, y = cell
        if not (0 <= x < width and 0 <= y < height):
            raise ConfigError(
                f"{label} {cell} is outside the {width}x{height} maze"
            )
    if entry == exit_cell:
        raise ConfigError("ENTRY and EXIT must be different cells")

    output_file = Path(values["OUTPUT_FILE"])
    perfect = _parse_bool("PERFECT", values["PERFECT"])
    if not perfect and (
        width < 2 or height < 2 or width * height < 6
    ):
        raise ConfigError(
            "PERFECT=False requires a maze of at least 2x3 cells so "
            "that two independent routes can exist"
        )

    seed: int | None = None
    if "SEED" in values:
        seed = _parse_int("SEED", values["SEED"])

    algorithm = "backtracker"
    if "ALGORITHM" in values:
        algorithm = values["ALGORITHM"].strip().lower()
        if algorithm not in {"backtracker", "prim"}:
            raise ConfigError(
                "ALGORITHM must be 'backtracker' or 'prim', "
                f"got {values['ALGORITHM']!r}"
            )

    return Config(
        width=width,
        height=height,
        entry=entry,
        exit=exit_cell,
        output_file=output_file,
        perfect=perfect,
        seed=seed,
        algorithm=algorithm,
    )


def _paint(text: str, color: str, enabled: bool = True) -> str:
    """Wrap *text* in an ANSI colour, or return it unchanged."""
    if not enabled:
        return text
    return f"{color}{text}{_RESET}"


def _build_generator(
    config: Config,
    seed: int | None,
) -> MazeGenerator:
    """Create a generator from a validated configuration."""
    return MazeGenerator(
        width=config.width,
        height=config.height,
        entry=config.entry,
        exit=config.exit,
        perfect=config.perfect,
        seed=seed,
        algorithm=config.algorithm,
    )


class MazeApp:
    """Own the generator, its output file and the terminal display."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._seed = config.seed
        self._generator = _build_generator(config, self._seed)
        self._show_path = True
        self._wall_color = 0
        self._pattern_highlight = True
        self._message = ""

    def start(self) -> None:
        """Generate the first maze, save it, then display it."""
        self._generate(new_seed=False)
        self._write_output()
        self._print_summary()
        self._run_display()

    def _generate(self, new_seed: bool) -> None:
        """Generate a maze, optionally with a fresh random seed."""
        if new_seed:
            self._seed = random.randrange(1, 2**31)
        self._generator = _build_generator(self._config, self._seed)
        self._generator.generate()

    def _write_output(self) -> None:
        """Write the current maze to the configured output file."""
        try:
            self._generator.write_output(self._config.output_file)
        except OSError as exc:
            raise OSError(
                f"cannot write {self._config.output_file}: {exc.strerror}"
            ) from exc

    def _print_summary(self) -> None:
        """Print a short generation summary."""
        mode = "perfect" if self._config.perfect else "playable"
        print(f"Maze written to {self._config.output_file}")
        print(
            f"Size: {self._config.width}x{self._config.height} | "
            f"mode: {mode} | algorithm: {self._config.algorithm} | "
            f"seed: {self._seed}"
        )
        if self._generator.pattern_skipped:
            print(
                "Warning: the maze is too small to draw the 42 pattern.",
                file=sys.stderr,
            )
        steps = len(self._generator.solve()) - 1
        print(f"Shortest path: {steps} steps")
        print()

    def _regenerate(self) -> None:
        """Regenerate a maze after a user interaction."""
        try:
            self._generate(new_seed=True)
            self._write_output()
        except (MazeError, OSError) as exc:
            self._message = f"Error: {exc}"
            return
        self._message = f"New maze generated (seed {self._seed})."
        if self._generator.pattern_skipped:
            self._message += " 42 pattern omitted (maze too small)."

    def _run_display(self) -> None:
        """Run the interactive loop, or print one frame when not a TTY."""
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            print(self._render(color=False))
            return

        descriptor = sys.stdin.fileno()
        previous = termios.tcgetattr(descriptor)
        try:
            tty.setcbreak(descriptor)
            sys.stdout.write("\x1b[?25l")
            while True:
                self._draw()
                key = sys.stdin.read(1)
                if not key or key in ("q", "Q", "\x1b"):
                    break
                if key in ("r", "R"):
                    self._regenerate()
                elif key in ("p", "P"):
                    self._show_path = not self._show_path
                elif key in ("c", "C"):
                    self._wall_color = (
                        self._wall_color + 1
                    ) % len(_WALL_COLORS)
                elif key == "4":
                    self._pattern_highlight = not self._pattern_highlight
        finally:
            termios.tcsetattr(
                descriptor, termios.TCSADRAIN, previous
            )
            sys.stdout.write("\x1b[?25h\n")
            sys.stdout.flush()

    def _draw(self) -> None:
        """Redraw the whole terminal frame."""
        frame = "\x1b[2J\x1b[H"
        frame += self._render(color=True)
        frame += "\n\n" + self._status_line()
        frame += "\n" + self._help_line()
        if self._message:
            frame += "\n" + self._message
        sys.stdout.write(frame + "\n")
        sys.stdout.flush()
        self._message = ""

    def _status_line(self) -> str:
        """Return the interactive status line."""
        mode = "perfect" if self._config.perfect else "playable"
        path_state = "ON" if self._show_path else "OFF"
        pattern_state = (
            "highlighted" if self._pattern_highlight else "dim"
        )
        colour = _WALL_COLOR_NAMES[self._wall_color]
        return (
            f"A-Maze-ing | {self._config.width}x{self._config.height} | "
            f"{mode} | seed {self._seed} | path {path_state} | "
            f"walls {colour} | 42 {pattern_state}"
        )

    @staticmethod
    def _help_line() -> str:
        """Return the keyboard help line."""
        return (
            "[r] regenerate  [p] show/hide path  [c] wall colour  "
            "[4] 42 colour  [q] quit"
        )

    def _render(self, color: bool) -> str:
        """Render the maze as ASCII art, optionally with ANSI colours."""
        generator = self._generator
        wall = _WALL_COLORS[self._wall_color] if color else ""
        reset = _RESET if color else ""
        path: set[Cell] = (
            set(generator.solve()) if self._show_path else set()
        )
        lines: list[str] = []
        for y in range(generator.height):
            if y == 0:
                top: list[str] = []
                for x in range(generator.width):
                    top.append(wall + "+")
                    if generator.cells[y][x] & NORTH:
                        top.append(wall + "---")
                    else:
                        top.append("   ")
                top.append(wall + "+" + reset)
                lines.append("".join(top))

            middle: list[str] = []
            for x in range(generator.width):
                if generator.cells[y][x] & WEST:
                    middle.append(wall + "|")
                else:
                    middle.append(" ")
                middle.append(self._cell_text(x, y, path, color))
            last_x = generator.width - 1
            if generator.cells[y][last_x] & EAST:
                middle.append(wall + "|")
            else:
                middle.append(" ")
            middle.append(reset)
            lines.append("".join(middle))

            bottom: list[str] = []
            for x in range(generator.width):
                bottom.append(wall + "+")
                if generator.cells[y][x] & SOUTH:
                    bottom.append(wall + "---")
                else:
                    bottom.append("   ")
            bottom.append(wall + "+" + reset)
            lines.append("".join(bottom))
        return "\n".join(lines)

    def _cell_text(
        self,
        x: int,
        y: int,
        path: set[Cell],
        color: bool,
    ) -> str:
        """Return the coloured content of one cell."""
        cell = (x, y)
        if cell in self._generator.pattern_cells:
            pattern_color = (
                _PATTERN_BRIGHT
                if self._pattern_highlight
                else _PATTERN_DIM
            )
            return _paint("###", pattern_color, color)
        if cell == self._generator.entry:
            return _paint(" S ", _ENTRY_COLOR, color)
        if cell == self._generator.exit:
            return _paint(" E ", _EXIT_COLOR, color)
        if cell in path:
            return _paint(" * ", _PATH_COLOR, color)
        return "   "


def main(argv: Sequence[str] | None = None) -> int:
    """Program entry point."""
    parser = argparse.ArgumentParser(
        prog="a_maze_ing.py",
        description="Generate and display a maze from a configuration file.",
    )
    parser.add_argument(
        "config",
        type=Path,
        help="path to the configuration file",
    )
    arguments = parser.parse_args(argv)

    try:
        config = parse_config(arguments.config)
        MazeApp(config).start()
    except (ConfigError, MazeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except MemoryError:
        print(
            "Error: the requested maze is too large to fit in memory",
            file=sys.stderr,
        )
        return 1
    except KeyboardInterrupt:
        print()
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
