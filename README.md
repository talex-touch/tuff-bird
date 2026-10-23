# tuff-bird

**Training logs as TensorBoard event files, a live board that follows them, and figures and charts made from them.**

[English](https://github.com/talex-touch/tuff-bird/blob/main/README.md) · [简体中文](https://github.com/talex-touch/tuff-bird/blob/main/README.zh.md)

[![PyPI](https://img.shields.io/pypi/v/tuff-bird)](https://pypi.org/project/tuff-bird/)
[![Python](https://img.shields.io/pypi/pyversions/tuff-bird)](https://pypi.org/project/tuff-bird/)
[![CI](https://github.com/talex-touch/tuff-bird/actions/workflows/ci.yml/badge.svg)](https://github.com/talex-touch/tuff-bird/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](https://github.com/talex-touch/tuff-bird/blob/main/LICENSE)

![The board following six CartPole runs while they train](https://raw.githubusercontent.com/talex-touch/tuff-bird/main/docs/images/board-live.gif)

One call in a training script writes everything about the run into TensorBoard event files
under `logs/`: the metrics, the config, what the script prints, and the CPU, memory and GPU
it used. The same call starts a board in your browser that follows those files as they grow.
`tensorboard --logdir logs` opens the same files, and the board opens directories that
TensorBoard, tensorboardX or PyTorch wrote. The package has no dependencies; figures for papers
and charts in notebooks come with optional extras.

## Install

```bash
pip install tuff-bird
pip install "tuff-bird[system]"     # adds CPU and memory metrics, through psutil
pip install "tuff-bird[plot]"       # adds figures for papers, through matplotlib
pip install "tuff-bird[notebook]"   # adds the live chart in Jupyter, through anywidget; includes [plot]
```

## Quick start

```python
import tuffbird

run = tuffbird.init(logdir="logs", group="cartpole/lr-0.5", name="seed-0", config={"lr": 0.5, "gamma": 0.99})
for step in range(10_000):
    ...
    run.log({"train": {"loss": loss, "return": episode_return}}, step=step)
run.finish()
```

The first script to start opens the board at <http://127.0.0.1:6066>; scripts started later
join it, so a sweep of many processes shares one board. A run that ends with an exception is
marked failed, and one stopped with Ctrl-C is marked stopped. Under `torch.distributed`, only
rank 0 starts the board.

Code that already uses PyTorch's `SummaryWriter` changes only its import:

```python
from tuffbird import SummaryWriter
```

The shim covers `add_scalar`, `add_scalars`, `add_text`, `add_hparams`, `flush` and `close`.

## Try the demo

```bash
pip install "tuff-bird[system]"
curl -O https://raw.githubusercontent.com/talex-touch/tuff-bird/main/examples/cartpole.py
python cartpole.py
```

REINFORCE on CartPole in plain Python: two learning rates, three seeds each, six processes
in parallel. It takes about 35 seconds.

## The board

| | |
| --- | --- |
| ![Two learning rates, each drawn as the mean of three seeds with a band for their spread](https://raw.githubusercontent.com/talex-touch/tuff-bird/main/docs/images/board-groups.png) | ![The config of six runs side by side, with the two differing keys marked](https://raw.githubusercontent.com/talex-touch/tuff-bird/main/docs/images/board-config.png) |
| Runs in one directory form a group. Merged, a group is drawn as its mean with a band for the spread of its runs. | The config of every run side by side, with the keys that differ marked. |
| ![The printed output of one run, with stderr in red](https://raw.githubusercontent.com/talex-touch/tuff-bird/main/docs/images/board-output.png) | ![CPU and memory charts for the runs](https://raw.githubusercontent.com/talex-touch/tuff-bird/main/docs/images/board-system.png) |
| What each run printed, stdout and stderr in order, searchable, following new lines. | CPU and memory of the training machine and process, and the GPUs that `nvidia-smi` reports. |

Charts smooth with an exponential moving average and can also show the raw values and a log
x-axis. Drag across a chart to zoom in, and double-click it to zoom back out. The board
follows the system's light or dark theme. The code button on a chart copies the Python that
draws it with the board's settings, as a figure for a paper and as an HTML file.

## Figures for papers

```python
import tuffbird

exp = tuffbird.load("logs")
fig = exp.plot("eval/return")   # a matplotlib figure
fig.savefig("return.pdf")
print(fig.tuffbird_caption)
```

Runs in one directory are seeds of one configuration, as on the board. Each curve is their
mean with a 95% bootstrap confidence interval, the interval estimate that
[Agarwal et al. (2021)](https://arxiv.org/abs/2108.13264) recommend reporting; their
interquartile mean is `estimator="iqm"`. A curve stops where its shortest run stops, so its
end is not an average of fewer runs than its start. `fig.tuffbird_caption` describes the
figure for its caption:

```text
Lines: mean across runs (n = 3 per curve). Shaded: 95% bootstrap confidence interval of the mean
(2,000 resamples). Each run is smoothed with a debiased exponential moving average (weight 0.6)
before aggregating. Steps stop where the shortest run stops.
```

| Option | Default | Other values |
| --- | --- | --- |
| `group_by` | the runs in one directory | a config key such as `"lr"`, a list of keys, a function of a run, or `None` for one curve per run |
| `estimator` | `"mean"` | `"iqm"` (interquartile mean) or `"median"` |
| `band` | `"ci"`, a 95% interval | `"std"`, `"se"`, `"minmax"` or `"none"`; `confidence` sets the interval |
| `smoothing` | `0.6` | the board's moving-average weight, from 0 to 0.999 |
| `truncate` | `True` | `False` keeps the steps after the shortest run stops |
| `raw` | `False` | `True` also draws the values as logged, faintly |
| `ax` | a new figure | your own axes, one per tag |

PDF files embed their fonts as TrueType and SVG files keep their text as text, so both stay
editable; PNG files are 300 dpi. The command line draws the same figure and prints its caption:

```bash
tuff-bird plot logs -t eval/return -o return.pdf
tuff-bird plot logs -t eval/return -t train/loss --group-by lr --estimator iqm   # writes eval-return_train-loss.pdf
```

## Interactive charts

```python
exp.chart("eval/return").save("return.html")   # the board's chart in one file
exp.show("eval/return")                         # in a notebook, live while the runs write
```

A chart is the board's own: hover for values, click a legend entry to hide its curve, and
move the smoothing slider. A saved file carries the chart's script (about 110 KB) and its
data, so it opens offline in any browser. `tuff-bird plot logs -t eval/return -o return.html`
writes the same file.

In a notebook, `show()` follows the runs while they write. A widget updates every second from
a background thread, so training can run in the same kernel. Once every run has stopped for
30 seconds, the widget is replaced by the saved chart, which holds a picture of itself for
places that run no scripts, such as an untrusted notebook. A notebook saved after that keeps
the interactive chart without a kernel. When no run is writing, `show()` shows the saved
chart at once. Pass `live=True` to follow runs that have not started yet, and call `.stop()`
on what `show()` returns to save the chart as it is.

Notebook charts are tested in JupyterLab 4.6; VS Code, Colab and GitHub's notebook view are
not tested yet. Known limits:

- Only the page that showed the chart receives the saved chart. A page opened or reloaded
  later keeps the live widget, which says so; run `show()` again to save the chart in the
  notebook.
- While a cell is running, a reloaded page shows "Loading widget..." until the cell finishes,
  because JupyterLab restores widgets through the kernel.
- The kernel keeps every point the widget has drawn until the cell runs again or the kernel
  restarts.

## Training on another machine

Over SSH the board starts on the training machine and does not open a browser. Instead it
prints the command that forwards its port to your own machine:

```text
[tuffbird] board: http://127.0.0.1:6066  (logdir /data/logs)
[tuffbird] from your own machine: ssh -N -L 6066:127.0.0.1:6066 you@gpu-box  then open http://127.0.0.1:6066
```

The board has no login. It listens on 127.0.0.1 unless `TUFFBIRD_BOARD_HOST` says otherwise;
listening on another address shows your logs and config to anyone who can reach that port.

## Command line and settings

```bash
tuff-bird board logs                      # serve a log directory, including one TensorBoard wrote
tuff-bird stop logs                       # stop the board serving it
tuff-bird plot logs -t loss -o loss.pdf   # a figure; -o loss.html writes the interactive chart
```

| Variable | Effect |
| --- | --- |
| `TUFFBIRD_BOARD=0` | Training scripts do not start the board. |
| `TUFFBIRD_OPEN_BROWSER=0` | The board starts but no browser opens. |
| `TUFFBIRD_BOARD_PORT` | Port to try first (default 6066); the next free one is used when it is taken. |
| `TUFFBIRD_BOARD_HOST` | Address to listen on (default 127.0.0.1). |

## How it works

- **Event files.** The writer frames records the way TFRecord does (length, CRC32C, data,
  CRC32C) and encodes the `Event` and `Summary` protobufs by hand, so neither TensorFlow nor
  protobuf is needed. Metrics are scalar summaries, printed output uses the text plugin, and
  the config is an HParams session, so TensorBoard's HParams tab lists the runs and groups
  them by `group`.
- **The board.** A standard-library HTTP server reads each event file from where it stopped,
  and the page receives a snapshot followed by a stream of new points (server-sent events).
  The page is a Vue app built on [TuffEx](https://www.npmjs.com/package/@talex-touch/tuffex)
  and ships inside the wheel.
- **One board per log directory.** `logs/.tuffbird/board.json` records which board serves the
  directory. Scripts starting at the same moment agree on one of them to launch it, and the
  board keeps running after training ends until `tuff-bird stop`.
- **Figures and charts.** `tuffbird.load()` reads a log directory with the board's reader and
  groups runs as the board does. Figures are drawn with matplotlib. A saved chart is the
  board's chart (Vue and TuffEx) built as one ES module and packed into the page with the
  chart's data; in a notebook, the same module runs as an anywidget.

## Status

0.2 is an alpha. The board reads images and audio but does not show them yet; that and the
rest of the plan are in the [roadmap issues](https://github.com/talex-touch/tuff-bird/issues?q=is%3Aissue+label%3Aroadmap).

## Development

```bash
cd web && pnpm install && pnpm build && cd ..   # builds the board page and the chart script into src/tuffbird
pip install -e ".[dev,system,plot,notebook]"
python -m pytest
uvx ruff check .
```

See [CONTRIBUTING.md](https://github.com/talex-touch/tuff-bird/blob/main/CONTRIBUTING.md) for the rest, including how a release is made.

## License

[MIT](https://github.com/talex-touch/tuff-bird/blob/main/LICENSE)
