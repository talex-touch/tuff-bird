# Changelog

All notable changes to tuff-bird are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [0.2.1] - 2026-10-23

Two fixes to what 0.2.0 draws.

### Fixed

- A chart with fewer panels than fit in a row spreads them across it, so a chart of one tag is
  as wide as its output and its smoothing slider sits over it, in a saved page and in Jupyter.
- A figure's caption says that the steps stop where the shortest run stops only when steps were
  dropped. `Summary.truncated` is now true only then, and `Summary.disjoint` tells when the runs
  share no steps.

## [0.2.0] - 2026-10-23

Figures for papers, and the board's chart outside the board: in one HTML file and live in Jupyter.

### Added

- `tuffbird.load(logdir)` reads a log directory back as an `Experiment`: its runs, tags and
  scalars, and its curves, with runs grouped as the board groups them, by config keys, by a
  function, or not at all.
- `Experiment.plot()` and `tuff-bird plot`: a matplotlib figure with a panel per tag. Each curve
  is the mean across its runs with a 95% bootstrap confidence interval, over the steps every run
  reached; the interquartile mean, the median and other bands are options. PDF and SVG files keep
  their text editable, and the figure comes with a caption that says what it shows. Needs
  `tuff-bird[plot]`.
- `Experiment.chart()`: the board's interactive chart, with a smoothing slider, in one HTML file
  that opens offline (`tuff-bird plot -o chart.html`) or as a notebook output.
- `Experiment.show()`: in Jupyter, the chart follows the runs while they write, then turns into
  the saved chart, with a picture inside for places that run no scripts. Needs
  `tuff-bird[notebook]`.
- The board: a button on each chart copies the Python that draws it with the board's settings.
- The optional extras `[plot]` (matplotlib and numpy) and `[notebook]` (anywidget, with
  `[plot]`). The package itself still has no dependencies.

## [0.1.1] - 2026-10-21

The project is renamed to tuff-bird. The tuff-rl 0.1.0 release stays on PyPI as it was
published; install tuff-bird from here on.

### Changed

- The package, the import name, the command and the environment variables take the new name:
  `pip install tuff-bird`, `import tuffbird`, `tuff-bird board`, and `TUFFBIRD_*` in place of
  `TUFFRL_*`. The state directory is now `.tuffbird`.
- The repository moved to `talex-touch/tuff-bird`; the old links redirect.

## [0.1.0] - 2026-10-21

The first release, published under the name tuff-rl.

### Added

- `tuffrl.init()` and `Run`: write metrics, config, printed output and system metrics of a
  run into TensorBoard event files, with no dependencies.
- `tuffrl.SummaryWriter`: a stand-in for PyTorch's, covering `add_scalar`, `add_scalars`,
  `add_text`, `add_hparams`, `flush` and `close`.
- The board: a local web page that follows a log directory as it grows, with scalar charts,
  groups merged into mean and spread, a config comparison, printed output and system metrics.
  It also opens directories written by TensorBoard, tensorboardX and PyTorch.
- One board per log directory, started by the first training script and joined by the rest;
  over SSH it prints the port-forwarding command instead of opening a browser.
- `tuff-rl board` and `tuff-rl stop` on the command line.
- `examples/cartpole.py`: REINFORCE on CartPole in plain Python, six runs in parallel.

[0.2.1]: https://github.com/talex-touch/tuff-bird/releases/tag/v0.2.1
[0.2.0]: https://github.com/talex-touch/tuff-bird/releases/tag/v0.2.0
[0.1.1]: https://github.com/talex-touch/tuff-bird/releases/tag/v0.1.1
[0.1.0]: https://github.com/talex-touch/tuff-bird/releases/tag/v0.1.0
