from __future__ import annotations

import csv
import json
import os
import random
from pathlib import Path

from ConfigValidator.Config.Models.FactorModel import FactorModel
from ConfigValidator.Config.Models.OperationType import OperationType
from ConfigValidator.Config.Models.RunnerContext import RunnerContext
from ConfigValidator.Config.Models.RunTableModel import RunTableModel
from EventManager.EventSubscriptionController import EventSubscriptionController
from EventManager.Models.RunnerEvents import RunnerEvents

from replication.gl1 import campaign as single
from replication.gl1 import stack_campaign as stack
from replication.gl1.measure import Meter
from replication.runner import envelope


ROOT = Path(__file__).resolve().parents[2]
CAMPAIGNS = {
    "single": ("single_warm", list(single.SUBJECTS), list(single.TREATMENTS)),
    "stack": ("stack_warm", list(stack.STACKS), ["baseline", "slim", "blafs"]),
    "stack-confine": ("stack_warm_confine", list(stack.STACKS), ["confine"]),
}
REPETITIONS = 20
RANDOM_SEED = 42
DATA_COLUMNS = [name for name in single.CSV_FIELDS if name not in ("subject", "treatment")]


def _cpu_set(value: str) -> set[int]:
    cpus = set()
    for part in value.split(","):
        bounds = part.strip().split("-")
        if len(bounds) == 1:
            cpus.add(int(bounds[0]))
        elif len(bounds) == 2:
            first, last = map(int, bounds)
            if last < first:
                raise ValueError(f"Invalid CPU range: {part}")
            cpus.update(range(first, last + 1))
        else:
            raise ValueError(f"Invalid CPU range: {part}")
    if not cpus or min(cpus) < 0:
        raise ValueError(f"Invalid CPU set: {value}")
    return cpus


class RunnerConfig:
    ROOT_DIR = ROOT
    operation_type = OperationType.AUTO
    time_between_runs_in_ms = int(single.COOLDOWN_S * 1000)
    results_output_path = ROOT / "experiments" / "new_runs"
    experiment_path: Path = None

    def __init__(self):
        self.campaign = os.environ.get("WARM_CAMPAIGN", "single")
        if self.campaign not in CAMPAIGNS:
            raise ValueError("WARM_CAMPAIGN must be single, stack, or stack-confine")
        name, self.subjects, self.treatments = CAMPAIGNS[self.campaign]
        self.name = os.environ.get("WARM_RUN_NAME", name)
        if not self.name or Path(self.name).name != self.name or self.name in (".", ".."):
            raise ValueError("WARM_RUN_NAME must be a directory name, not a path")
        self.run_table_model = None
        self._result = None
        EventSubscriptionController.subscribe_to_multiple_events([
            (RunnerEvents.BEFORE_EXPERIMENT, self.before_experiment),
            (RunnerEvents.START_RUN, self.start_run),
            (RunnerEvents.INTERACT, self.interact),
            (RunnerEvents.POPULATE_RUN_DATA, self.populate_run_data),
        ])

    def create_run_table_model(self) -> RunTableModel:

        random.seed(RANDOM_SEED)
        self.run_table_model = RunTableModel(
            factors=[FactorModel("subject", self.subjects),
                     FactorModel("treatment", self.treatments)],
            repetitions=REPETITIONS,
            shuffle=True,
            data_columns=DATA_COLUMNS.copy(),
        )
        return self.run_table_model

    def before_experiment(self) -> None:


        if not hasattr(os, "sched_setaffinity"):
            raise RuntimeError("The GL1 warm experiment requires Linux CPU affinity support")
        cpus = _cpu_set(envelope.LOADGEN_CPUSET)
        available = os.sched_getaffinity(0)
        if not cpus <= available:
            raise RuntimeError(
                f"Load-generator CPUs {sorted(cpus)} are not all available; "
                f"available CPUs: {sorted(available)}. Check MB_ENV_LOADGEN_CPUSET."
            )
        self._check_inputs()
        os.sched_setaffinity(0, cpus)

    def _check_inputs(self) -> None:
        if self.campaign == "single":
            if not single.ASSETS.is_dir():
                raise FileNotFoundError(f"Missing workload assets: {single.ASSETS}")
            return
        required = set()
        for subject in self.subjects:
            required.update(Path(p) for p in stack.STACKS[subject]["compose"])
            required.add(stack.OV / f"{subject}.cpuset.yml")
            for treatment in self.treatments:
                image_treatment = "baseline" if treatment == "confine" else treatment
                required.add(stack.OV / f"{subject}.{image_treatment}.reg.yml")
                if treatment == "confine":
                    required.add(stack.OV / f"{subject}.confine.seccomp.yml")
        missing = sorted(str(p) for p in required if not p.is_file())
        if missing:
            raise FileNotFoundError("Missing stack inputs; set MICROBENCH_DIR and OV_DIR:\n"
                                    + "\n".join(missing))

    def start_run(self, context: RunnerContext) -> None:
        subject = context.execute_run["subject"]
        treatment = context.execute_run["treatment"]
        rep = int(context.execute_run["__run_id"].rsplit("_repetition_", 1)[1])
        self._result = {
            "subject": subject, "treatment": treatment, "rep": rep,
            "kind": single.SUBJECTS[subject]["kind"] if self.campaign == "single" else "stack",
            "ok": False, "error": None,
        }

    def interact(self, context: RunnerContext) -> None:
        result = self._result
        subject, treatment = result["subject"], result["treatment"]
        try:
            if self.campaign == "single":
                single._clear_containers()
                ref = single.image_ref(subject, treatment)
                result["image_ref"] = ref
                if not single.docker.image_exists(ref):
                    result["error"] = "image_absent"
                    return
                policy = single.seccomp_for(subject, treatment)
                if treatment == "confine" and policy is None:
                    raise FileNotFoundError(f"Confine measurement policy missing for {subject}")
                with Meter(Path(context.run_dir)) as meter:
                    metrics = single.DRIVERS[result["kind"]](
                        subject, single.SUBJECTS[subject], ref, policy, meter)
            else:
                stack._clear()


                metrics = stack.run_stack_trial(subject, treatment, Meter(Path(context.run_dir)))
            result.update(metrics)
            result["ok"] = True
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"[:300]

    def _baseline(self, subject: str) -> tuple[str, str] | None:


        tables = [Path(self.experiment_path) / "run_table.csv"]
        if self.campaign == "stack-confine":
            tables.append(Path(os.environ.get(
                "WARM_BASELINE_TABLE", str(self.results_output_path / "stack_warm" / "run_table.csv"))))
        for path in tables:
            if not path.is_file():
                continue
            with path.open(newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    if (row.get("__done") == "DONE" and row.get("subject") == subject
                            and row.get("treatment") == "baseline" and row.get("ok") == "True"):
                        cold, steady = row.get("cold_output_hash"), row.get("steady_output_hash")
                        if cold and steady:
                            return cold, steady
        return None

    def populate_run_data(self, context: RunnerContext) -> dict:
        result = self._result
        if result["ok"]:
            baseline = self._baseline(result["subject"])
            if baseline is None and result["treatment"] == "baseline":
                baseline = (result.get("cold_output_hash"), result.get("steady_output_hash"))
            if baseline is not None:
                result["cold_match"] = result.get("cold_output_hash") == baseline[0]
                result["steady_match"] = result.get("steady_output_hash") == baseline[1]

        out = Path(context.run_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "trial.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        return {column: result.get(column) for column in DATA_COLUMNS}
