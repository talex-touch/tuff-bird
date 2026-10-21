"""Files written here open in TensorBoard, and files TensorBoard tools write open here."""

from __future__ import annotations

import pytest
from helpers import quiet_run, read_events, values_of

from tuffbird import SummaryWriter
from tuffbird.events import Media, Scalar, Text

pytest.importorskip("tensorboard")
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator  # noqa: E402
from tensorboard.plugins.hparams import plugin_data_pb2  # noqa: E402


def load(path) -> EventAccumulator:
    accumulator = EventAccumulator(str(path), size_guidance={"scalars": 0, "tensors": 0})
    accumulator.Reload()
    return accumulator


def test_tensorboard_reads_a_run(tmp_path):
    run = quiet_run(tmp_path, "run", group="sweep", config={"lr": 0.1, "opt": "adam"})
    for step in range(3):
        run.log({"loss": 1.0 / (step + 1)}, step=step)
    run.log_text("notes", "hello")
    run.finish()

    board = load(tmp_path / "sweep" / "run")
    loss = board.Scalars("loss")
    assert [event.step for event in loss] == [0, 1, 2]
    assert [event.value for event in loss] == pytest.approx([1.0, 0.5, 1 / 3])
    assert board.Tensors("notes")[0].tensor_proto.string_val == [b"hello"]

    content = board.PluginTagToContent("hparams")
    start = plugin_data_pb2.HParamsPluginData.FromString(content["_hparams_/session_start_info"]).session_start_info
    assert start.hparams["lr"].number_value == pytest.approx(0.1)
    assert start.hparams["opt"].string_value == "adam"
    assert start.group_name == "sweep"
    end = plugin_data_pb2.HParamsPluginData.FromString(content["_hparams_/session_end_info"]).session_end_info
    assert end.status == 1  # STATUS_SUCCESS


def test_summary_writer_shim_reads_back_in_tensorboard(tmp_path):
    with SummaryWriter(str(tmp_path / "exp"), board=False) as writer:
        for step in range(3):
            writer.add_scalar("loss", 1.0 / (step + 1), step)
            writer.add_scalars("acc", {"train": 0.5, "val": 0.25}, step)
        writer.add_text("notes", "hello", 0)
        writer.add_hparams({"lr": 0.1}, {"hparam/score": 0.75})

    board = load(tmp_path / "exp")
    assert sorted(board.Tags()["scalars"]) == ["acc/train", "acc/val", "hparam/score", "loss"]
    assert [event.value for event in board.Scalars("acc/val")] == [0.25, 0.25, 0.25]
    assert "notes" in board.Tags()["tensors"]


def test_reads_what_tensorboardx_writes(tmp_path):
    tensorboardx = pytest.importorskip("tensorboardX")
    numpy = pytest.importorskip("numpy")
    writer = tensorboardx.SummaryWriter(str(tmp_path / "run"))
    for step in range(5):
        writer.add_scalar("reward", step * 2.0, step)
    writer.add_text("notes", "from tensorboardX", 1)
    writer.add_image("frame", numpy.zeros((3, 4, 4), dtype=numpy.uint8), 0)
    writer.close()

    events = read_events(tmp_path, "run")
    assert [(event.step, value.value) for event in events for value in event.values if isinstance(value, Scalar)] == [
        (step, step * 2.0) for step in range(5)
    ]
    [text] = values_of(events, Text)
    assert (text.tag, text.text) == ("notes/text_summary", "from tensorboardX")
    [image] = values_of(events, Media)
    assert (image.tag, image.kind, image.content_type) == ("frame", "image", "image/png")
    assert image.data.startswith(b"\x89PNG")
