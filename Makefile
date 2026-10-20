PYTHON ?= python3

.PHONY: install run debug clean lint lint-strict test package

install:
	$(PYTHON) -m pip install --upgrade build flake8 mypy pytest

run:
	$(PYTHON) a_maze_ing.py config.txt

debug:
	$(PYTHON) -m pdb a_maze_ing.py config.txt

clean:
	rm -rf __pycache__ */__pycache__ .mypy_cache .pytest_cache
	rm -rf build dist *.egg-info

lint:
	flake8 .
	mypy . --warn-return-any --warn-unused-ignores --ignore-missing-imports --disallow-untyped-defs --check-untyped-defs

lint-strict:
	flake8 .
	mypy . --strict

test:
	$(PYTHON) -m pytest -q

package:
	$(PYTHON) -m build --wheel
	cp dist/mazegen-*.whl .
