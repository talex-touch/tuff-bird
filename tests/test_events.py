"""The TFRecord framing and the protobuf messages, without any TensorFlow code."""

from __future__ import annotations

import struct

import pytest

from tuffbird.events.crc32c import _crc32c_python, crc32c, masked_crc32c
from tuffbird.events.records import CorruptRecordError, RecordReader, encode_record
from tuffbird.events.schema import (
    HParamsEnd,
    HParamsStart,
    Scalar,
    Text,
    hparams_end_event,
    hparams_start_event,
    parse_event,
    scalars_event,
    text_event,
)


def test_crc32c_matches_the_standard_check_value():
    assert _crc32c_python(b"123456789") == 0xE3069283
    assert crc32c(b"123456789") == 0xE3069283


def test_masked_crc_matches_tensorboard():
    stub = pytest.importorskip("tensorboard.compat.tensorflow_stub.pywrap_tensorflow")
    for data in (b"", b"tuff-bird", struct.pack("<Q", 1234), bytes(range(256))):
        assert masked_crc32c(data) == stub.masked_crc32c(data)


def test_reader_leaves_an_unfinished_record_for_the_next_read(tmp_path):
    path = tmp_path / "events"
    first, second = encode_record(b"first"), encode_record(b"second record")
    path.write_bytes(first + second[:7])
    reader = RecordReader(str(path))
    assert reader.read_available() == [b"first"]
    with path.open("ab") as handle:
        handle.write(second[7:])
    assert reader.read_available() == [b"second record"]
    assert reader.read_available() == []


def test_reader_widens_its_window_for_a_large_record(tmp_path):
    path = tmp_path / "events"
    path.write_bytes(encode_record(b"x" * 5000) + encode_record(b"y"))
    reader = RecordReader(str(path))
    assert reader.read_available(max_bytes=1024) == [b"x" * 5000]
    assert reader.read_available() == [b"y"]


def test_reader_rejects_a_damaged_length(tmp_path):
    record = bytearray(encode_record(b"payload"))
    record[0] ^= 0xFF
    path = tmp_path / "events"
    path.write_bytes(bytes(record))
    with pytest.raises(CorruptRecordError):
        RecordReader(str(path)).read_available()


def test_reader_checks_data_when_asked(tmp_path):
    record = bytearray(encode_record(b"payload"))
    record[14] ^= 0xFF  # inside the data
    path = tmp_path / "events"
    path.write_bytes(bytes(record))
    assert RecordReader(str(path)).read_available() == [bytes(record[12:19])]
    with pytest.raises(CorruptRecordError):
        RecordReader(str(path), verify_data=True).read_available()


def test_scalars_and_text_round_trip():
    event = parse_event(scalars_event(3, 1.5, {"loss": 0.25, "acc": 1.0}))
    assert (event.step, event.wall_time) == (3, 1.5)
    assert event.values == [Scalar("loss", 0.25), Scalar("acc", 1.0)]
    assert parse_event(text_event(4, 2.0, "stdout", "héllo\n")).values == [Text("stdout", "héllo\n")]


def test_hparams_round_trip():
    config = {"lr": 0.5, "opt": "adam", "nesterov": True, "layers": [64, 64], "schedule": None}
    start = parse_event(hparams_start_event(10.0, config, group="sweep")).values[0]
    assert start == HParamsStart(hparams=config, group="sweep", start_time=10.0)
    for status in ("success", "failure", "unknown"):
        end = parse_event(hparams_end_event(11.0, status)).values[0]
        assert end == HParamsEnd(status=status, end_time=11.0)
