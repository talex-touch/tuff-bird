# tuff-rl

**Training logs as TensorBoard event files, and a live board that follows them.**

[English](https://github.com/talex-touch/tuff-rl/blob/main/README.md) · [简体中文](https://github.com/talex-touch/tuff-rl/blob/main/README.zh.md)

[![PyPI](https://img.shields.io/pypi/v/tuff-rl)](https://pypi.org/project/tuff-rl/)
[![Python](https://img.shields.io/pypi/pyversions/tuff-rl)](https://pypi.org/project/tuff-rl/)
[![CI](https://github.com/talex-touch/tuff-rl/actions/workflows/ci.yml/badge.svg)](https://github.com/talex-touch/tuff-rl/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](https://github.com/talex-touch/tuff-rl/blob/main/LICENSE)

![The board following six CartPole runs while they train](https://raw.githubusercontent.com/talex-touch/tuff-rl/main/docs/images/board-live.gif)

One call in a training script writes everything about the run into TensorBoard event files
under `logs/`: the metrics, the config, what the script prints, and the CPU, memory and GPU
it used. The same call starts a board in your browser that follows those files as they grow.
`tensorboard --logdir logs` opens the same files, and the board opens directories that
TensorBoard, tensorboardX or PyTorch wrote. The package has no dependencies.

## Install

```bash
pip install tuff-rl
pip install "tuff-rl[system]"   # adds CPU and memory metrics, through psutil
```

## Quick start

```python
import tuffrl

run = tuffrl.init(logdir="logs", group="cartpole/lr-0.5", name="seed-0", config={"lr": 0.5, "gamma": 0.99})
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
from tuffrl import SummaryWriter
```

The shim covers `add_scalar`, `add_scalars`, `add_text`, `add_hparams`, `flush` and `close`.

## Try the demo

```bash
pip install "tuff-rl[system]"
curl -O https://raw.githubusercontent.com/talex-touch/tuff-rl/main/examples/cartpole.py
python cartpole.py
```

REINFORCE on CartPole in plain Python: two learning rates, three seeds each, six processes
in parallel. It takes about 35 seconds.

## The board

| | |
| --- | --- |
| ![Two learning rates, each drawn as the mean of three seeds with a band for their spread](https://raw.githubusercontent.com/talex-touch/tuff-rl/main/docs/images/board-groups.png) | ![The config of six runs side by side, with the two differing keys marked](https://raw.githubusercontent.com/talex-touch/tuff-rl/main/docs/images/board-config.png) |
| Runs in one directory form a group. Merged, a group is drawn as its mean with a band for the spread of its runs. | The config of every run side by side, with the keys that differ marked. |
| ![The printed output of one run, with stderr in red](https://raw.githubusercontent.com/talex-touch/tuff-rl/main/docs/images/board-output.png) | ![CPU and memory charts for the runs](https://raw.githubusercontent.com/talex-touch/tuff-rl/main/docs/images/board-system.png) |
| What each run printed, stdout and stderr in order, searchable, following new lines. | CPU and memory of the training machine and process, and the GPUs that `nvidia-smi` reports. |

Charts smooth with an exponential moving average and can also show the raw values and a log
x-axis. Drag across a chart to zoom in, and double-click it to zoom back out. The board
follows the system's light or dark theme.

## Training on another machine

Over SSH the board starts on the training machine and does not open a browser. Instead it
prints the command that forwards its port to your own machine:

```text
[tuffrl] board: http://127.0.0.1:6066  (logdir /data/logs)
[tuffrl] from your own machine: ssh -N -L 6066:127.0.0.1:6066 you@gpu-box  then open http://127.0.0.1:6066
```

The board has no login. It listens on 127.0.0.1 unless `TUFFRL_BOARD_HOST` says otherwise;
listening on another address shows your logs and config to anyone who can reach that port.

## Command line and settings

```bash
tuff-rl board logs   # serve a log directory, including one TensorBoard wrote
tuff-rl stop logs    # stop the board serving it
```

| Variable | Effect |
| --- | --- |
| `TUFFRL_BOARD=0` | Training scripts do not start the board. |
| `TUFFRL_OPEN_BROWSER=0` | The board starts but no browser opens. |
| `TUFFRL_BOARD_PORT` | Port to try first (default 6066); the next free one is used when it is taken. |
| `TUFFRL_BOARD_HOST` | Address to listen on (default 127.0.0.1). |

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
- **One board per log directory.** `logs/.tuffrl/board.json` records which board serves the
  directory. Scripts starting at the same moment agree on one of them to launch it, and the
  board keeps running after training ends until `tuff-rl stop`.

## Status

0.1 is an alpha. The board reads images and audio but does not show them yet; that and the
rest of the plan are in the [roadmap issues](https://github.com/talex-touch/tuff-rl/issues?q=is%3Aissue+label%3Aroadmap).

## Development

```bash
cd web && pnpm install && pnpm build && cd ..   # builds the board page into src/tuffrl/board/static
pip install -e ".[dev,system]"
python -m pytest
uvx ruff check .
```

See [CONTRIBUTING.md](https://github.com/talex-touch/tuff-rl/blob/main/CONTRIBUTING.md) for the rest, including how a release is made.

## License

[MIT](https://github.com/talex-touch/tuff-rl/blob/main/LICENSE)
