# Changelog

All notable changes to tuff-bird are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

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

[0.1.1]: https://github.com/talex-touch/tuff-bird/releases/tag/v0.1.1
[0.1.0]: https://github.com/talex-touch/tuff-bird/releases/tag/v0.1.0
