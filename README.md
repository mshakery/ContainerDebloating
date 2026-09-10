
## Reproduction of analysis

Use R 4.6.1 and install the packages listed in `analysis/README.md`. From this
directory, run:

```sh
Rscript analysis/main.R
```

The first run extracts the cold-pull archive under `experiments/gl1/cold_eb/`.
Outputs are written to `analysis/stats/`, `analysis/figures/`, and
`analysis/tables/`.

## Generate single-images

Use a dedicated Linux build host with Docker and an overlay2 installation
compatible with BLAFS. BLAFS modifies the Docker storage and restarts its daemon.
The measurement runners also remove containers during trial cleanup. These
scripts therefore require an experiment host dedicated to this study.

Create and activate a Python 3.13 environment, then install the host-side
workload clients. The tested Experiment Runner EnergiBridge plugin uses syntax
introduced in Python 3.12; Python 3.10 and 3.11 cannot import that plugin.

```sh
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install -r replication/requirements.txt
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
```

Install the external tools separately: SlimToolkit/mintoolkit must provide the
`slim` command, and BLAFS must provide `baffs`. The package contains the thesis
adapters, not copies of these third-party toolchains. The recorded adapters use
`slim slim`, `baffs shadow`, and `baffs debloat`. Their original tool revisions
were not recorded in the available files. Consult the tools' installation
documentation for the required build-host setup.

Start the registry expected by the build orchestrator:

```sh
docker run -d --restart unless-stopped --name pullbench-registry \
  -p 127.0.0.1:5000:5000 -v pullbench-registry-data:/var/lib/registry registry:2
python -m replication.gl1.build_all
```

The existing `pullbench-registry` container can be reused. Successful builds
receive both registry tags (`127.0.0.1:5000/<subject>__<treatment>:latest`) and
warm-run tags (`campaign/<subject>:<treatment>`). Results are written to
`experiments/build_all_results.json`. Set `REGISTRY` if a different registry is
used. When the build and measurement hosts differ, pull these registry tags on
the measurement host and apply the corresponding `campaign/` tags there.

## Confine profiles

Confine changes the runtime seccomp policy and retains the baseline image.
The package includes the 15 measurement-host policies named
`*.gl1.seccomp.json`, each with its original `.mode` record. Cassandra has no
saved policy. The policies are required by the warm runner and by the analysis
of blocked system calls.

`replication/debloat/confine.py` also contains the generation adapter. To generate
a new policy after installing Confine and its call graphs:

```sh
export CONFINE_DIR=/absolute/path/to/confine
python -c 'from replication.debloat.confine import build_confine_image; from replication.workloads.registry import SUBJECTS_BY_ID; print(build_confine_image(SUBJECTS_BY_ID["nginx"]))'
```

This creates `nginx.seccomp.json`; it does not recreate or replace the saved
`nginx.gl1.seccomp.json`. The adapter mentions patches to the original Confine
checkout, but those patches and the measurement-host policy adjustment procedure
were unavailable. Preserve the supplied `.gl1` policies when reproducing the
saved treatment.

## Run warm experiments with Experiment Runner

From the package root, with the environment above active:

```sh
WARM_CAMPAIGN=single python "$EXPERIMENT_RUNNER_DIR/" replication/gl1/WarmRunnerConfig.py
```

Launch the stack campaigns:

```sh
WARM_CAMPAIGN=stack python "$EXPERIMENT_RUNNER_DIR/" replication/gl1/WarmRunnerConfig.py
WARM_CAMPAIGN=stack-confine python "$EXPERIMENT_RUNNER_DIR/" replication/gl1/WarmRunnerConfig.py
```

## The cold-pull experiment

The cold runner uses a separate Docker daemon at
`unix:///var/run/docker-cold.sock`. It prunes that daemon's store for each trial.
Keep the registry on the main daemon. The original startup command is:

```sh
sudo dockerd --data-root /var/lib/docker-cold \
  -H unix:///var/run/docker-cold.sock --pidfile /var/run/docker-cold.pid \
  --bridge=none --iptables=false
```

Use a separate terminal or service for that daemon. Set `COLD_DOCKER_HOST` only
to another dedicated, disposable experiment daemon. After restoring and
populating the original stack-image registry, generate the pull manifests:

```sh
python -m replication.gl1.cold_runner.make_stack_manifests
```

This generator reads existing `mbpull/` registry entries. It does not build the
stack images. With the manifests present, launch the final configuration:

```sh
python "$EXPERIMENT_RUNNER_DIR/" replication/gl1/cold_runner/RunnerConfig.py
```
