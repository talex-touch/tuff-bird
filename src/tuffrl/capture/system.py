"""Samples machine and process metrics into the run as ``sys/*`` scalars.

With ``psutil`` installed: CPU and memory of the machine and this process. Without it: load
average and this process's CPU share, which the standard library can see. NVIDIA GPUs are read
through ``nvidia-smi`` when it is on the PATH. The step of these points is seconds since the
run started.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from collections.abc import Callable

try:  # pragma: no cover - optional
    import psutil  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    psutil = None

_GPU_QUERY = "utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw"


def _gpu_metrics(nvidia_smi: str) -> dict[str, float]:
    try:
        output = subprocess.run(
            [nvidia_smi, f"--query-gpu={_GPU_QUERY}", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3, check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    metrics: dict[str, float] = {}
    names = ["util_percent", "memory_used_mb", "memory_total_mb", "temperature_c", "power_w"]
    for index, line in enumerate(output.strip().splitlines()):
        for name, raw in zip(names, line.split(","), strict=False):
            try:
                metrics[f"sys/gpu{index}/{name}"] = float(raw.strip())
            except ValueError:
                continue  # "[N/A]" on cards that do not report it
    return metrics


class SystemSampler:
    def __init__(self, emit: Callable[[int, dict[str, float]], None], *, interval: float = 5.0) -> None:
        self._emit = emit
        self._interval = interval
        self._start = time.time()
        self._stop = threading.Event()
        self._nvidia_smi = shutil.which("nvidia-smi")
        self._process = psutil.Process() if psutil else None
        self._last_cpu = self._cpu_seconds()
        self._last_wall = time.time()
        self._thread = threading.Thread(target=self._run, name="tuffrl-system", daemon=True)
        self._thread.start()

    @staticmethod
    def _cpu_seconds() -> float:
        return time.process_time()

    def sample(self) -> dict[str, float]:
        metrics: dict[str, float] = {}
        now = time.time()
        cpu = self._cpu_seconds()
        elapsed = max(now - self._last_wall, 1e-6)
        metrics["sys/process_cpu_percent"] = 100.0 * (cpu - self._last_cpu) / elapsed
        self._last_cpu, self._last_wall = cpu, now
        if psutil:
            metrics["sys/cpu_percent"] = psutil.cpu_percent(interval=None)
            metrics["sys/memory_percent"] = psutil.virtual_memory().percent
            if self._process is not None:
                metrics["sys/process_rss_mb"] = self._process.memory_info().rss / 2**20
        elif hasattr(os, "getloadavg"):
            metrics["sys/load_1m"] = os.getloadavg()[0]
        if self._nvidia_smi:
            metrics.update(_gpu_metrics(self._nvidia_smi))
        return metrics

    def _run(self) -> None:
        if psutil:
            # Primes the counter, which psutil keeps per thread: a call from the thread that
            # created the sampler would leave this one's first reading at 0.
            psutil.cpu_percent(interval=None)
        while not self._stop.wait(self._interval):
            self._emit(int(time.time() - self._start), self.sample())

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
