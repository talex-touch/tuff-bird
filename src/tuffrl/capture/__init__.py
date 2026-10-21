"""What a run records besides the metrics it logs: printed output and system metrics."""

from .stdout import OutputCapture
from .system import SystemSampler

__all__ = ["OutputCapture", "SystemSampler"]
