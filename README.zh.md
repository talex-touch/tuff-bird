# tuff-bird

**把训练日志写成 TensorBoard 事件文件，用一块跟着文件实时刷新的面板来看，还能从中出论文图和交互图。**

[English](https://github.com/talex-touch/tuff-bird/blob/main/README.md) · [简体中文](https://github.com/talex-touch/tuff-bird/blob/main/README.zh.md)

[![PyPI](https://img.shields.io/pypi/v/tuff-bird)](https://pypi.org/project/tuff-bird/)
[![Python](https://img.shields.io/pypi/pyversions/tuff-bird)](https://pypi.org/project/tuff-bird/)
[![CI](https://github.com/talex-touch/tuff-bird/actions/workflows/ci.yml/badge.svg)](https://github.com/talex-touch/tuff-bird/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](https://github.com/talex-touch/tuff-bird/blob/main/LICENSE)

![面板实时跟随六个正在训练的 CartPole 运行](https://raw.githubusercontent.com/talex-touch/tuff-bird/main/docs/images/board-live.gif)

训练脚本里调用一次，这次运行的所有内容就写进 `logs/` 下的 TensorBoard 事件文件：指标、配置、
脚本打印的输出，以及用到的 CPU、内存和 GPU。同一次调用还会在浏览器里打开一块面板，跟着这些
文件实时刷新。`tensorboard --logdir logs` 能直接打开同一批文件；反过来，TensorBoard、
tensorboardX 和 PyTorch 写的目录，面板也能打开。这个包没有任何依赖；论文图和 notebook 里的
图表通过可选依赖安装。

## 安装

```bash
pip install tuff-bird
pip install "tuff-bird[system]"     # 通过 psutil 增加 CPU 和内存指标
pip install "tuff-bird[plot]"       # 通过 matplotlib 出论文图
pip install "tuff-bird[notebook]"   # 通过 anywidget 在 Jupyter 里实时画图，包含 [plot]
```

## 快速开始

```python
import tuffbird

run = tuffbird.init(logdir="logs", group="cartpole/lr-0.5", name="seed-0", config={"lr": 0.5, "gamma": 0.99})
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
from tuffbird import SummaryWriter
```

这个兼容层支持 `add_scalar`、`add_scalars`、`add_text`、`add_hparams`、`flush` 和 `close`。

## 跑一下演示

```bash
pip install "tuff-bird[system]"
curl -O https://raw.githubusercontent.com/talex-touch/tuff-bird/main/examples/cartpole.py
python cartpole.py
```

纯 Python 写的 CartPole + REINFORCE：两种学习率各三个种子，六个进程并行，大约 35 秒跑完。

## 面板

| | |
| --- | --- |
| ![两种学习率，各自画成三个种子的均值，带一条表示离散程度的色带](https://raw.githubusercontent.com/talex-touch/tuff-bird/main/docs/images/board-groups.png) | ![六个运行的配置并排对比，两个不同的参数被标出](https://raw.githubusercontent.com/talex-touch/tuff-bird/main/docs/images/board-config.png) |
| 同一目录下的运行组成一组。合并显示时，一组画成均值曲线，色带表示组内各次运行的离散程度。 | 所有运行的配置并排对比，不同的参数会被标出。 |
| ![一次运行的打印输出，stderr 标红](https://raw.githubusercontent.com/talex-touch/tuff-bird/main/docs/images/board-output.png) | ![各运行的 CPU 和内存曲线](https://raw.githubusercontent.com/talex-touch/tuff-bird/main/docs/images/board-system.png) |
| 每次运行打印的内容，stdout 和 stderr 按时间排好，可以搜索，并跟随新输出。 | 训练机器和进程的 CPU、内存，以及 `nvidia-smi` 能看到的 GPU。 |

曲线用指数滑动平均平滑，也可以显示原始值、切换对数横轴。在图上拖动可以放大，双击恢复。
面板跟随系统的浅色或深色主题。图表上的代码按钮会按面板当前的设置，复制画出这张图的 Python
代码：一份出论文图，一份存成 HTML 文件。

## 论文图

```python
import tuffbird

exp = tuffbird.load("logs")
fig = exp.plot("eval/return")   # 一张 matplotlib 图
fig.savefig("return.pdf")
print(fig.tuffbird_caption)
```

同一目录下的运行是同一配置的不同种子，和面板的分组一致。每条曲线是这些运行的均值，色带是
95% bootstrap 置信区间，也就是 [Agarwal et al. (2021)](https://arxiv.org/abs/2108.13264)
建议报告的区间估计；他们推荐的四分位均值用 `estimator="iqm"`。曲线在最短的那次运行结束处
截止，这样曲线末尾不会比开头少算几次运行。`fig.tuffbird_caption` 是写给图注的说明：

```text
Lines: mean across runs (n = 3 per curve). Shaded: 95% bootstrap confidence interval of the mean
(2,000 resamples). Each run is smoothed with a debiased exponential moving average (weight 0.6)
before aggregating. Steps stop where the shortest run stops.
```

| 参数 | 默认值 | 其他取值 |
| --- | --- | --- |
| `group_by` | 同一目录下的运行 | 配置键（如 `"lr"`）、多个键的列表、以运行为参数的函数，或 `None`（每次运行一条曲线） |
| `estimator` | `"mean"` | `"iqm"`（四分位均值）或 `"median"` |
| `band` | `"ci"`，95% 区间 | `"std"`、`"se"`、`"minmax"` 或 `"none"`；`confidence` 设置区间 |
| `smoothing` | `0.6` | 面板的滑动平均权重，0 到 0.999 |
| `truncate` | `True` | `False` 保留最短运行结束之后的步数 |
| `raw` | `False` | `True` 时再用浅色画出原始值 |
| `ax` | 新建一张图 | 自己的坐标轴，每个 tag 一个 |

PDF 内嵌 TrueType 字体，SVG 里的文字保持为文字，两者都能继续编辑；PNG 为 300 dpi。命令行
画的是同一张图，并打印图注：

```bash
tuff-bird plot logs -t eval/return -o return.pdf
tuff-bird plot logs -t eval/return -t train/loss --group-by lr --estimator iqm   # 写到 eval-return_train-loss.pdf
```

## 交互图

```python
exp.chart("eval/return").save("return.html")   # 面板的图表，存成一个文件
exp.show("eval/return")                         # 在 notebook 里，运行写入时实时刷新
```

图表和面板上的一样：悬停看数值，点图例隐藏对应曲线，拖动平滑滑块。存下的文件自带图表脚本
（约 110 KB）和数据，离线也能在任何浏览器里打开。`tuff-bird plot logs -t eval/return -o return.html`
写出的是同一个文件。

在 notebook 里，`show()` 会在运行写入时实时跟随：后台线程每秒刷新一次 widget，所以训练可以
在同一个内核里跑。所有运行都停下 30 秒后，widget 换成存档图；存档图里带一张图片，供不运行
脚本的地方显示，比如不受信任的 notebook。之后保存 notebook，不开内核也能打开可交互的图表。
调用时如果没有运行在写入，`show()` 直接显示存档图。要跟随还没开始的运行，传 `live=True`；
对 `show()` 的返回值调用 `.stop()`，会按当前的样子存档。

notebook 图表在 JupyterLab 4.6 里测过；VS Code、Colab 和 GitHub 的 notebook 预览还没测。
已知限制：

- 只有显示这张图的页面会收到存档图。之后打开或刷新的页面仍是实时 widget，并会提示这一点；
  再运行一次 `show()`，图表才会存进 notebook。
- 有 cell 正在运行时刷新页面，widget 会显示 "Loading widget..."，直到这个 cell 跑完，因为
  JupyterLab 要通过内核恢复 widget。
- 在 cell 重新运行或内核重启之前，内核会保留 widget 画过的每一个点。

## 在另一台机器上训练

通过 SSH 训练时，面板在训练机上启动，不会打开浏览器，而是打印把端口转发到你本机的命令：

```text
[tuffbird] board: http://127.0.0.1:6066  (logdir /data/logs)
[tuffbird] from your own machine: ssh -N -L 6066:127.0.0.1:6066 you@gpu-box  then open http://127.0.0.1:6066
```

面板没有登录。除非用 `TUFFBIRD_BOARD_HOST` 指定别的地址，它只监听 127.0.0.1；监听其他地址时，
能访问到这个端口的人都能看到你的日志和配置。

## 命令行与设置

```bash
tuff-bird board logs                      # 打开一个日志目录的面板，TensorBoard 写的目录也可以
tuff-bird stop logs                       # 停掉服务这个目录的面板
tuff-bird plot logs -t loss -o loss.pdf   # 出图；-o loss.html 写出交互图
```

| 环境变量 | 作用 |
| --- | --- |
| `TUFFBIRD_BOARD=0` | 训练脚本不启动面板。 |
| `TUFFBIRD_OPEN_BROWSER=0` | 启动面板，但不打开浏览器。 |
| `TUFFBIRD_BOARD_PORT` | 优先使用的端口（默认 6066），被占用时顺延到下一个空闲端口。 |
| `TUFFBIRD_BOARD_HOST` | 监听地址（默认 127.0.0.1）。 |

## 工作原理

- **事件文件。** 写入端按 TFRecord 的方式分帧（长度、CRC32C、数据、CRC32C），并手写编码
  `Event` 和 `Summary` 两个 protobuf 消息，所以不需要 TensorFlow，也不需要 protobuf。指标是
  标量摘要，打印的输出用文本插件，配置写成 HParams 会话，所以 TensorBoard 的 HParams 页能
  列出这些运行，并按 `group` 分组。
- **面板。** 一个只用标准库的 HTTP 服务从上次读到的位置继续读每个事件文件；页面先拿一份快照，
  再通过服务器推送事件（SSE）接收新增的点。页面是用
  [TuffEx](https://www.npmjs.com/package/@talex-touch/tuffex) 写的 Vue 应用，随 wheel 一起发布。
- **一个日志目录一块面板。** `logs/.tuffbird/board.json` 记录哪块面板在服务这个目录。同时启动
  的多个脚本会商定由其中一个来启动它；训练结束后面板继续运行，直到执行 `tuff-bird stop`。
- **出图与图表。** `tuffbird.load()` 用面板的读取器读日志目录，并按面板的方式给运行分组。论文图
  用 matplotlib 画。存下的图表是把面板的图表（Vue 和 TuffEx）构建成一个 ES 模块，和图表数据
  一起打包进页面；在 notebook 里，同一个模块作为 anywidget 运行。

## 状态

0.2 是 alpha 版本。面板已经能读取图片和音频，但还不会显示；这件事和其他计划都在
[roadmap issues](https://github.com/talex-touch/tuff-bird/issues?q=is%3Aissue+label%3Aroadmap) 里。

## 开发

```bash
cd web && pnpm install && pnpm build && cd ..   # 把面板页面和图表脚本构建到 src/tuffbird
pip install -e ".[dev,system,plot,notebook]"
python -m pytest
uvx ruff check .
```

其余内容（包括怎么发布新版本）见 [CONTRIBUTING.md](https://github.com/talex-touch/tuff-bird/blob/main/CONTRIBUTING.md)。

## 许可证

[MIT](https://github.com/talex-touch/tuff-bird/blob/main/LICENSE)
