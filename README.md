# IMServerless Python template

A clean starting point for Python jobs on the existing IMServerless / Rancher platform.
It contains a harmless example pipeline, the platform `main.handle()` contract, a Docker image,
and the release automation extracted from SOIMS. No manufacturing rules, credentials, historical
results, installer bundles, existing Git history, or remote repository are copied.

## Start locally

Python 3.13+ is recommended to match the source project's tooling. Application code uses the standard library;
the offline release checks need PyYAML.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe main.py
```

Replace `pipeline/example.py` with your logic, update dispatch in `main.py`, and update `tests/test_main.py`.
Keep the `handle(job_id, context, header, body) -> (bool, str, str)` contract. Unknown scripts and unsupported
modes fail explicitly. The example only supports `ENV_MODE=test` and makes no external calls or writes.
The release helper also requires test mode. Enabling real business writes requires a deliberate code and test change;
a branch named `prod` would not change that behavior.

## Set up your repository

1. Edit **[release.yaml](release.yaml)**: project description, unique `funcname`, matching hostname,
   image repository, resources, runtime settings, Secret references, and your own branch names.
   `release` and `sandbox` are examples. There are no required `prod` or `test` branches.
2. Keep `namespace: icmpcs-soims` for this existing environment unless you have approval and access to another namespace.
   Give each new repository its own application and image identity. Never reuse another application's target.
3. Create your remote repository and add it as HTTPS `origin`. Configure runner access and credentials using
   [the release guide](docs/releases.md). The GitHub environment `release` must permit your selected branches.
4. Once configured, a push to a branch listed in `release.yaml` builds, tests, pushes, and deploys that branch's target.
   Other branches stop after checkout and configuration planning. Workflow files must be present on the pushed branch;
   GitHub's manual dispatch UI also needs the workflow on the default branch.

`release.yaml` is the single application/deployment configuration. The GitHub workflow remains a separate YAML because
GitHub requires `.github/workflows/`; `config/func.json` is the platform host configuration.
`tests/fixtures/release.yaml` is synthetic test data, not a second deployment configuration.

## Build locally

```powershell
docker build -f dockerfile -t imserverless-template:local .
docker run --rm --network none --entrypoint python imserverless-template:local main.py
```

The default base is the existing shared `amr-registry.caas.intel.com/soia/icmpcs-soims:base`.
It supplies `funchost_controller` and its platform dependencies. Registry access is required to fetch it.
To use another compatible base, supply `--build-arg BASE_IMAGE=<image>` and confirm the host contract.
The current shared base has an inherited `python-dotenv` dependency conflict; this template adds no
application dependencies and does not repair the shared base. See [validation](docs/validation.md).

The Docker context uses an allowlist: only application source, `config/func.json`, `requirements.txt`,
and the Dockerfile are sent. Add explicit entries when your application needs other packaged assets.
Tests, release tools, runner files, `.env`, and local secrets are excluded.

## Layout

| Path | Responsibility |
| --- | --- |
| `main.py`, `pipeline/` | Runtime entry and replaceable application logic |
| `config/func.json`, `dockerfile` | IMServerless function host and packaging |
| `release.yaml` | AppSpec, Secret references, and branch-to-suffix mappings |
| `automation/` | Offline plan, credential checks, digest deployment and rollout verification |
| `.github/workflows/release.yml` | Build, test, push and optional deployment |
| `runner/` | Optional repository-level runner setup from Windows / Docker Desktop |
| `tests/test_main.py`, `tests/test_release.py` | Offline application and release contract tests |

See [design provenance](docs/template-decisions.md) for the recent Copilot decisions carried into this template.
