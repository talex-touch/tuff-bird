"""TensorBoard ``Event`` and ``Summary`` messages: building them, and reading them back.

Field numbers follow ``tensorflow/core/util/event.proto``,
``tensorflow/core/framework/summary.proto`` and ``tensor.proto``, and the hparams plugin's
``plugin_data.proto``. Only what tuff-bird writes and what common writers (TensorFlow, PyTorch's
``SummaryWriter``, tensorboardX, Stable-Baselines3) produce is decoded; everything else is
skipped field by field.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field
from typing import Any

from . import proto

FILE_VERSION = "brain.Event:2"

HPARAMS_PLUGIN = "hparams"
HPARAMS_START_TAG = "_hparams_/session_start_info"
HPARAMS_END_TAG = "_hparams_/session_end_info"
TEXT_PLUGIN = "text"
SCALARS_PLUGIN = "scalars"

STATUS_NAMES = {0: "unknown", 1: "success", 2: "failure", 3: "running"}
STATUS_CODES = {name: code for code, name in STATUS_NAMES.items()}

# tensorflow DataType values this reader understands.
DT_FLOAT, DT_DOUBLE, DT_INT32, DT_STRING, DT_INT64, DT_BOOL, DT_HALF = 1, 2, 3, 7, 9, 10, 19


# ---------------------------------------------------------------------------- reading


@dataclass
class Scalar:
    tag: str
    value: float


@dataclass
class Text:
    tag: str
    text: str


@dataclass
class HParamsStart:
    hparams: dict[str, Any]
    group: str
    start_time: float


@dataclass
class HParamsEnd:
    status: str
    end_time: float


@dataclass
class Media:
    """An image or audio summary; the board lists them, M3 renders them."""

    tag: str
    kind: str  # "image" | "audio"
    content_type: str
    data: bytes
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Event:
    wall_time: float = 0.0
    step: int = 0
    file_version: str | None = None
    values: list[Scalar | Text | HParamsStart | HParamsEnd | Media] = field(default_factory=list)


def _decode_tensor(buf: bytes) -> tuple[int, list[Any]]:
    """``(dtype, values)`` of a TensorProto, flattened."""
    dtype = 0
    values: list[Any] = []
    content = b""
    for number, wire, value in proto.iter_fields(buf):
        if number == 1:
            dtype = int(value)  # type: ignore[arg-type]
        elif number == 4:
            content = value  # type: ignore[assignment]
        elif number == 5:  # float_val, packed or not
            raw = value if wire == proto.LENGTH else value
            values.extend(x for (x,) in struct.iter_unpack("<f", raw))  # type: ignore[arg-type]
        elif number == 6:  # double_val
            values.extend(x for (x,) in struct.iter_unpack("<d", value))  # type: ignore[arg-type]
        elif number in (7, 10, 11):  # int_val, int64_val, bool_val
            if wire == proto.LENGTH:
                pos = 0
                raw = value  # type: ignore[assignment]
                while pos < len(raw):
                    item, pos = proto.decode_varint(raw, pos)
                    values.append(proto.as_int64(item))
            else:
                values.append(proto.as_int64(int(value)))  # type: ignore[arg-type]
        elif number == 8:  # string_val
            values.append(bytes(value))  # type: ignore[arg-type]
        elif number == 13:  # half_val, carried as uint16 bit patterns
            raw = value if wire == proto.LENGTH else proto.encode_varint(int(value))  # type: ignore[arg-type]
            pos = 0
            while pos < len(raw):
                bits, pos = proto.decode_varint(raw, pos)
                values.append(struct.unpack("<e", struct.pack("<H", bits & 0xFFFF))[0])
    if content and not values:
        formats = {DT_FLOAT: "<f", DT_DOUBLE: "<d", DT_INT32: "<i", DT_INT64: "<q", DT_HALF: "<e"}
        fmt = formats.get(dtype)
        if fmt:
            values = [x for (x,) in struct.iter_unpack(fmt, content)]
    return dtype, values


def _decode_struct_value(buf: bytes) -> Any:
    """google.protobuf.Value."""
    for number, _wire, value in proto.iter_fields(buf):
        if number == 1:
            return None
        if number == 2:
            return proto.as_double(value)  # type: ignore[arg-type]
        if number == 3:
            return bytes(value).decode("utf-8", "replace")  # type: ignore[arg-type]
        if number == 4:
            return bool(value)
        if number == 5:  # Struct: map<string, Value> fields = 1
            out: dict[str, Any] = {}
            for entry_number, _w, entry in proto.iter_fields(value):  # type: ignore[arg-type]
                if entry_number == 1:
                    key, item = _decode_map_entry(entry)  # type: ignore[arg-type]
                    out[key] = item
            return out
        if number == 6:  # ListValue: repeated Value values = 1
            return [_decode_struct_value(item) for n, _w, item in proto.iter_fields(value) if n == 1]  # type: ignore[arg-type]
    return None


def _decode_map_entry(buf: bytes) -> tuple[str, Any]:
    key = ""
    item: Any = None
    for number, _wire, value in proto.iter_fields(buf):
        if number == 1:
            key = bytes(value).decode("utf-8", "replace")  # type: ignore[arg-type]
        elif number == 2:
            item = _decode_struct_value(value)  # type: ignore[arg-type]
    return key, item


def _decode_hparams(content: bytes) -> HParamsStart | HParamsEnd | None:
    for number, _wire, value in proto.iter_fields(content):
        if number == 3:  # SessionStartInfo
            hparams: dict[str, Any] = {}
            group = ""
            start_time = 0.0
            for n, _w, v in proto.iter_fields(value):  # type: ignore[arg-type]
                if n == 1:
                    key, item = _decode_map_entry(v)  # type: ignore[arg-type]
                    hparams[key] = item
                elif n == 4:
                    group = bytes(v).decode("utf-8", "replace")  # type: ignore[arg-type]
                elif n == 5:
                    start_time = proto.as_double(v)  # type: ignore[arg-type]
            return HParamsStart(hparams=hparams, group=group, start_time=start_time)
        if number == 4:  # SessionEndInfo
            status = 0
            end_time = 0.0
            for n, _w, v in proto.iter_fields(value):  # type: ignore[arg-type]
                if n == 1:
                    status = int(v)  # type: ignore[arg-type]
                elif n == 2:
                    end_time = proto.as_double(v)  # type: ignore[arg-type]
            return HParamsEnd(status=STATUS_NAMES.get(status, "unknown"), end_time=end_time)
    return None


def _decode_value(buf: bytes) -> Scalar | Text | HParamsStart | HParamsEnd | Media | None:
    tag = ""
    simple_value: float | None = None
    tensor: bytes | None = None
    plugin = ""
    plugin_content = b""
    image: bytes | None = None
    audio: bytes | None = None
    for number, _wire, value in proto.iter_fields(buf):
        if number == 1:
            tag = bytes(value).decode("utf-8", "replace")  # type: ignore[arg-type]
        elif number == 2:
            simple_value = proto.as_float(value)  # type: ignore[arg-type]
        elif number == 4:
            image = value  # type: ignore[assignment]
        elif number == 6:
            audio = value  # type: ignore[assignment]
        elif number == 8:
            tensor = value  # type: ignore[assignment]
        elif number == 9:  # SummaryMetadata
            for n, _w, v in proto.iter_fields(value):  # type: ignore[arg-type]
                if n == 1:  # PluginData
                    for pn, _pw, pv in proto.iter_fields(v):  # type: ignore[arg-type]
                        if pn == 1:
                            plugin = bytes(pv).decode("utf-8", "replace")  # type: ignore[arg-type]
                        elif pn == 2:
                            plugin_content = bytes(pv)  # type: ignore[arg-type]

    if plugin == HPARAMS_PLUGIN:
        return _decode_hparams(plugin_content)
    if simple_value is not None:
        return Scalar(tag, simple_value)
    if image is not None:
        meta: dict[str, Any] = {}
        data = b""
        for n, _w, v in proto.iter_fields(image):
            if n == 1:
                meta["height"] = int(v)  # type: ignore[arg-type]
            elif n == 2:
                meta["width"] = int(v)  # type: ignore[arg-type]
            elif n == 4:
                data = bytes(v)  # type: ignore[arg-type]
        return Media(tag, "image", _sniff_image(data), data, meta)
    if audio is not None:
        meta = {}
        data = b""
        content_type = "audio/wav"
        for n, _w, v in proto.iter_fields(audio):
            if n == 1:
                meta["sample_rate"] = proto.as_float(v)  # type: ignore[arg-type]
            elif n == 2:
                meta["channels"] = int(v)  # type: ignore[arg-type]
            elif n == 4:
                data = bytes(v)  # type: ignore[arg-type]
            elif n == 5:
                content_type = bytes(v).decode("utf-8", "replace") or content_type  # type: ignore[arg-type]
        return Media(tag, "audio", content_type, data, meta)
    if tensor is not None:
        dtype, values = _decode_tensor(tensor)
        if plugin == TEXT_PLUGIN or dtype == DT_STRING:
            texts = [v.decode("utf-8", "replace") for v in values if isinstance(v, bytes)]
            if plugin == TEXT_PLUGIN:
                return Text(tag, "\n".join(texts))
            return None  # string tensors of other plugins (TF2 images, audio) wait for M3
        if len(values) == 1 and plugin in ("", SCALARS_PLUGIN):
            number = float(values[0])
            return Scalar(tag, number)
    return None


def _sniff_image(data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if data.startswith(b"GIF8"):
        return "image/gif"
    return "application/octet-stream"


def parse_event(buf: bytes) -> Event:
    event = Event()
    for number, _wire, value in proto.iter_fields(buf):
        if number == 1:
            event.wall_time = proto.as_double(value)  # type: ignore[arg-type]
        elif number == 2:
            event.step = proto.as_int64(int(value))  # type: ignore[arg-type]
        elif number == 3:
            event.file_version = bytes(value).decode("utf-8", "replace")  # type: ignore[arg-type]
        elif number == 5:  # Summary: repeated Value value = 1
            for n, _w, item in proto.iter_fields(value):  # type: ignore[arg-type]
                if n == 1:
                    decoded = _decode_value(item)  # type: ignore[arg-type]
                    if decoded is not None:
                        event.values.append(decoded)
    return event


# ---------------------------------------------------------------------------- writing


def _event(wall_time: float, step: int, payload: bytes) -> bytes:
    return proto.field_double(1, wall_time) + proto.field_varint(2, step) + payload


def _plugin_metadata(plugin: str, content: bytes = b"") -> bytes:
    plugin_data = proto.field_string(1, plugin)
    if content:
        plugin_data += proto.field_bytes(2, content)
    return proto.field_bytes(9, proto.field_bytes(1, plugin_data))


def _summary(*values: bytes) -> bytes:
    return proto.field_bytes(5, b"".join(proto.field_bytes(1, value) for value in values))


def file_version_event(wall_time: float) -> bytes:
    return proto.field_double(1, wall_time) + proto.field_string(3, FILE_VERSION)


def scalars_event(step: int, wall_time: float, scalars: dict[str, float]) -> bytes:
    values = []
    for tag, value in scalars.items():
        number = float(value)
        values.append(proto.field_string(1, tag) + proto.field_float(2, number))
    return _event(wall_time, step, _summary(*values))


def text_event(step: int, wall_time: float, tag: str, text: str) -> bytes:
    shape = proto.field_bytes(2, proto.field_bytes(2, proto.field_varint(1, 1)))
    tensor = proto.field_varint(1, DT_STRING) + shape + proto.field_bytes(8, text.encode("utf-8"))
    value = proto.field_string(1, tag) + _plugin_metadata(TEXT_PLUGIN) + proto.field_bytes(8, tensor)
    return _event(wall_time, step, _summary(value))


def _encode_struct_value(item: Any) -> bytes:
    if item is None:
        return proto.field_varint(1, 0)
    if isinstance(item, bool):
        return proto.field_varint(4, int(item))
    if isinstance(item, (int, float)) and math.isfinite(float(item)):
        return proto.field_double(2, float(item))
    if isinstance(item, (list, tuple)):
        return proto.field_bytes(6, b"".join(proto.field_bytes(1, _encode_struct_value(x)) for x in item))
    if isinstance(item, dict):
        entries = b"".join(
            proto.field_bytes(1, proto.field_string(1, str(k)) + proto.field_bytes(2, _encode_struct_value(v)))
            for k, v in item.items()
        )
        return proto.field_bytes(5, entries)
    return proto.field_string(3, str(item))


def hparams_start_event(wall_time: float, hparams: dict[str, Any], group: str = "") -> bytes:
    entries = b"".join(
        proto.field_bytes(1, proto.field_string(1, str(key)) + proto.field_bytes(2, _encode_struct_value(value)))
        for key, value in hparams.items()
    )
    start = entries
    if group:
        start += proto.field_string(4, group)
    start += proto.field_double(5, wall_time)
    content = proto.field_bytes(3, start)
    value = proto.field_string(1, HPARAMS_START_TAG) + _plugin_metadata(HPARAMS_PLUGIN, content)
    return _event(wall_time, 0, _summary(value))


def hparams_end_event(wall_time: float, status: str) -> bytes:
    end = proto.field_varint(1, STATUS_CODES.get(status, 0)) + proto.field_double(2, wall_time)
    content = proto.field_bytes(4, end)
    value = proto.field_string(1, HPARAMS_END_TAG) + _plugin_metadata(HPARAMS_PLUGIN, content)
    return _event(wall_time, 0, _summary(value))
