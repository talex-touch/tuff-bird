# tuff-rl

**把训练日志写成 TensorBoard 事件文件，再用一块跟着文件实时刷新的面板来看。**

[English](https://github.com/talex-touch/tuff-rl/blob/main/README.md) · [简体中文](https://github.com/talex-touch/tuff-rl/blob/main/README.zh.md)

[![PyPI](https://img.shields.io/pypi/v/tuff-rl)](https://pypi.org/project/tuff-rl/)
[![Python](https://img.shields.io/pypi/pyversions/tuff-rl)](https://pypi.org/project/tuff-rl/)
[![CI](https://github.com/talex-touch/tuff-rl/actions/workflows/ci.yml/badge.svg)](https://github.com/talex-touch/tuff-rl/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](https://github.com/talex-touch/tuff-rl/blob/main/LICENSE)

![面板实时跟随六个正在训练的 CartPole 运行](https://raw.githubusercontent.com/talex-touch/tuff-rl/main/docs/images/board-live.gif)

训练脚本里调用一次，这次运行的所有内容就写进 `logs/` 下的 TensorBoard 事件文件：指标、配置、
脚本打印的输出，以及用到的 CPU、内存和 GPU。同一次调用还会在浏览器里打开一块面板，跟着这些
文件实时刷新。`tensorboard --logdir logs` 能直接打开同一批文件；反过来，TensorBoard、
tensorboardX 和 PyTorch 写的目录，面板也能打开。这个包没有任何依赖。

## 安装

```bash
pip install tuff-rl
pip install "tuff-rl[system]"   # 通过 psutil 增加 CPU 和内存指标
```

## 快速开始

```python
import tuffrl

run = tuffrl.init(logdir="logs", group="cartpole/lr-0.5", name="seed-0", config={"lr": 0.5, "gamma": 0.99})
for step in range(10_000):
    ...
    run.log({"train": {"loss": loss, "return": episode_return}}, step=step)
run.finish()
```

第一个启动的脚本会在 <http://127.0.0.1:6066> 打开面板，之后启动的脚本直接加入，所以多进程的
参数扫描共用一块面板。运行因异常结束会标记为失败，用 Ctrl-C 停下会标记为已中断。在
`torch.distributed` 下只有 rank 0 会启动面板。

已经在用 PyTorch `SummaryWriter` 的代码，只要改一行 import：

```python
from tuffrl import SummaryWriter
```

这个兼容层支持 `add_scalar`、`add_scalars`、`add_text`、`add_hparams`、`flush` 和 `close`。

## 跑一下演示

```bash
pip install "tuff-rl[system]"
curl -O https://raw.githubusercontent.com/talex-touch/tuff-rl/main/examples/cartpole.py
python cartpole.py
```

纯 Python 写的 CartPole + REINFORCE：两种学习率各三个种子，六个进程并行，大约 35 秒跑完。

## 面板

| | |
| --- | --- |
| ![两种学习率，各自画成三个种子的均值，带一条表示离散程度的色带](https://raw.githubusercontent.com/talex-touch/tuff-rl/main/docs/images/board-groups.png) | ![六个运行的配置并排对比，两个不同的参数被标出](https://raw.githubusercontent.com/talex-touch/tuff-rl/main/docs/images/board-config.png) |
| 同一目录下的运行组成一组。合并显示时，一组画成均值曲线，色带表示组内各次运行的离散程度。 | 所有运行的配置并排对比，不同的参数会被标出。 |
| ![一次运行的打印输出，stderr 标红](https://raw.githubusercontent.com/talex-touch/tuff-rl/main/docs/images/board-output.png) | ![各运行的 CPU 和内存曲线](https://raw.githubusercontent.com/talex-touch/tuff-rl/main/docs/images/board-system.png) |
| 每次运行打印的内容，stdout 和 stderr 按时间排好，可以搜索，并跟随新输出。 | 训练机器和进程的 CPU、内存，以及 `nvidia-smi` 能看到的 GPU。 |

曲线用指数滑动平均平滑，也可以显示原始值、切换对数横轴。在图上拖动可以放大，双击恢复。
面板跟随系统的浅色或深色主题。

## 在另一台机器上训练

通过 SSH 训练时，面板在训练机上启动，不会打开浏览器，而是打印把端口转发到你本机的命令：

```text
[tuffrl] board: http://127.0.0.1:6066  (logdir /data/logs)
[tuffrl] from your own machine: ssh -N -L 6066:127.0.0.1:6066 you@gpu-box  then open http://127.0.0.1:6066
```

面板没有登录。除非用 `TUFFRL_BOARD_HOST` 指定别的地址，它只监听 127.0.0.1；监听其他地址时，
能访问到这个端口的人都能看到你的日志和配置。

## 命令行与设置

```bash
tuff-rl board logs   # 打开一个日志目录的面板，TensorBoard 写的目录也可以
tuff-rl stop logs    # 停掉服务这个目录的面板
```

| 环境变量 | 作用 |
| --- | --- |
| `TUFFRL_BOARD=0` | 训练脚本不启动面板。 |
| `TUFFRL_OPEN_BROWSER=0` | 启动面板，但不打开浏览器。 |
| `TUFFRL_BOARD_PORT` | 优先使用的端口（默认 6066），被占用时顺延到下一个空闲端口。 |
| `TUFFRL_BOARD_HOST` | 监听地址（默认 127.0.0.1）。 |

## 工作原理

- **事件文件。** 写入端按 TFRecord 的方式分帧（长度、CRC32C、数据、CRC32C），并手写编码
  `Event` 和 `Summary` 两个 protobuf 消息，所以不需要 TensorFlow，也不需要 protobuf。指标是
  标量摘要，打印的输出用文本插件，配置写成 HParams 会话，所以 TensorBoard 的 HParams 页能
  列出这些运行，并按 `group` 分组。
- **面板。** 一个只用标准库的 HTTP 服务从上次读到的位置继续读每个事件文件；页面先拿一份快照，
  再通过服务器推送事件（SSE）接收新增的点。页面是用
  [TuffEx](https://www.npmjs.com/package/@talex-touch/tuffex) 写的 Vue 应用，随 wheel 一起发布。
- **一个日志目录一块面板。** `logs/.tuffrl/board.json` 记录哪块面板在服务这个目录。同时启动
  的多个脚本会商定由其中一个来启动它；训练结束后面板继续运行，直到执行 `tuff-rl stop`。

## 状态

0.1 是 alpha 版本。面板已经能读取图片和音频，但还不会显示；这件事和其他计划都在
[roadmap issues](https://github.com/talex-touch/tuff-rl/issues?q=is%3Aissue+label%3Aroadmap) 里。

## 开发

```bash
cd web && pnpm install && pnpm build && cd ..   # 把面板页面构建到 src/tuffrl/board/static
pip install -e ".[dev,system]"
python -m pytest
uvx ruff check .
```

其余内容（包括怎么发布新版本）见 [CONTRIBUTING.md](https://github.com/talex-touch/tuff-rl/blob/main/CONTRIBUTING.md)。

## 许可证

[MIT](https://github.com/talex-touch/tuff-rl/blob/main/LICENSE)
