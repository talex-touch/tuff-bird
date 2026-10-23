# Contributing

Issues and pull requests are welcome. For anything larger than a fix, open an issue first so
the approach can be agreed before the work.

## Setting up

The board page and the chart script are Vue apps in `web/`. They are built into
`src/tuffbird/board/static/` and `src/tuffbird/charts/static/`, which are not committed, so
build them once before installing:

```bash
cd web
pnpm install
pnpm build        # type-checks, then builds into ../src/tuffbird/board/static and ../src/tuffbird/charts/static
cd ..
pip install -e ".[dev,system,plot,notebook]"
```

Without the build the board still serves its API, and the page says that it has not been
built; saving a chart fails with a message that says to build it. The tests do not need the
build.

While working on the page, `pnpm dev` in `web/` serves it with hot reload and forwards `/api`
to a board on port 6066 (`tuff-bird board <logdir>`; set `TUFFBIRD_BOARD_URL` for another one).

## Checks

```bash
python -m pytest     # the writer, the reader, TensorBoard compatibility, the board process, figures and charts
uvx ruff check .
pnpm build           # in web/, when the page changed
```

CI runs the same checks on Python 3.10 to 3.13. A change to the page also needs a look in a
real browser, in both the light and the dark theme, and a change to the chart, a look in
JupyterLab too.

## Commits

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/), for
example `fix(board): keep the zoom window when new points arrive`.

## Releasing

1. Update `__version__` in `src/tuffbird/__init__.py` and add the version to `CHANGELOG.md`.
2. Merge that to `main`.
3. Push a tag `v<version>`. The release workflow checks that the tag matches the version,
   builds the page and the package, publishes to PyPI through trusted publishing and creates
   the GitHub release from the changelog.
