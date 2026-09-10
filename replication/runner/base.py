from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional


class Phase(str, Enum):
    PULL = "pull"                 
    PROVISIONING = "provisioning"
    COLD_START = "cold_start"
    STEADY_STATE = "steady_state"


@dataclass
class PhaseWindow:
    phase: Phase
    start_monotonic: float
    end_monotonic: float
    start_wall: float
    end_wall: float

    @property
    def duration_s(self) -> float:
        return self.end_monotonic - self.start_monotonic


@dataclass
class TrialContext:

    image_ref: str
    assets_dir: Path
    cpus: float
    memory_mb: int
    cpuset_cpu: int
    steady_duration_s: float
    provisioning_timeout_s: float
    seccomp_profile: Optional[Path] = None


@dataclass
class WorkloadOutcome:
    windows: dict[Phase, PhaseWindow] = field(default_factory=dict)
    cold_output_hash: Optional[str] = None
    steady_output_hash: Optional[str] = None
    peak_memory_bytes: Optional[int] = None
    error: Optional[str] = None

    extra: dict[str, object] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error is None and len(self.windows) == 3


@dataclass(frozen=True)
class SubjectSpec:
    id: str
    image: str
    tag: str
    category: str
    workload_factory: Callable[[], "Workload"]

    @property
    def image_ref(self) -> str:
        return f"{self.image}:{self.tag}"


class Workload(ABC):


    subject_id: str

    @abstractmethod
    def execute(self, ctx: TrialContext) -> WorkloadOutcome:
        pass
