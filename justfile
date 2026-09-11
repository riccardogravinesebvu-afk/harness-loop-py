default:
    @just --list

sync:
    uv sync --group dev

lint:
    uv run ruff check . --fix && uv run ruff format .

test:
    uv run pytest -q

evals seed="42":
    uv run python -m evals.run --seed {{seed}}
