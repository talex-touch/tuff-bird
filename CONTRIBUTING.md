# Contributing

Issues and pull requests are welcome. For anything larger than a fix, open an issue first so
the approach can be agreed before the work.

## Setting up

The board page is a Vue app in `web/`. It is built into `src/tuffrl/board/static/`, which is
not committed, so build it once before installing:

```bash
cd web
pnpm install
pnpm build        # type-checks, then builds into ../src/tuffrl/board/static
cd ..
pip install -e ".[dev,system]"
```

Without the build the board still serves its API, and the page says that it has not been
built.

While working on the page, `pnpm dev` in `web/` serves it with hot reload and forwards `/api`
to a board on port 6066 (`tuff-rl board <logdir>`; set `TUFFRL_BOARD_URL` for another one).

## Checks

```bash
python -m pytest     # the writer, the reader, TensorBoard compatibility and the board process
uvx ruff check .
pnpm build           # in web/, when the page changed
```

CI runs the same checks on Python 3.10 to 3.13. A change to the page also needs a look in a
real browser, in both the light and the dark theme.

## Commits

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/), for
example `fix(board): keep the zoom window when new points arrive`.

## Releasing

1. Update `__version__` in `src/tuffrl/__init__.py` and add the version to `CHANGELOG.md`.
2. Merge that to `main`.
3. Push a tag `v<version>`. The release workflow checks that the tag matches the version,
   builds the page and the package, publishes to PyPI through trusted publishing and creates
   the GitHub release from the changelog.
