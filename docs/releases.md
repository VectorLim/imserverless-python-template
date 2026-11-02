# Releases and repository runner setup

## Configure the target

Edit `release.yaml` before any remote push to a configured branch. The example uses:

```yaml
branches:
  release: ''
  sandbox: '-sandbox'
```

Choose any Git branch names. Each suffix must be unique and use lowercase letters, digits and hyphens.
The empty suffix uses the base `funcname` and image repository; `-sandbox` appends to both and to the hostname's
first label. Each app has its own numeric version sequence: first deployment `1.0`, then the highest existing
major/minor version plus one minor, up to `999`. AppSpec hostname must match `<funcname>.<cluster>.intel.com`.

`secrets.pull` names an existing same-namespace Docker registry Secret containing `.dockerconfigjson`.
`secrets.env` maps runtime Secret names to required nonempty keys; these are attached through `envFrom`.
`secrets.check` maps other prerequisite Secret names to keys; these are checked but not injected.
The example requires only `itcaas-regcred` and no application credentials or share mounts. Add your own
runtime Secret names and volumes when your application needs them. Never put values in this file.

Plan locally without credentials, network access or deployment:

```powershell
.\.venv\Scripts\python.exe -m automation plan --branch release
.\.venv\Scripts\python.exe -m automation plan --branch sandbox
.\.venv\Scripts\python.exe -m automation plan --branch feature/example
```

The last command prints `RELEASE=false`. Replace the first two branch names when you change your map.
The workflow listens to pushes and consults this map before build, push and deploy steps.
Manual dispatch defaults to build/test/push only; select `deploy` to update IMServerless too.
Build-only dispatch still needs registry push credentials.

## Required runner and GitHub settings

Use a **trusted, repository-level Linux x64 runner** with labels `self-hosted`, `linux`, `x64`,
`imserverless-release`. It needs Git, Bash, Python with `venv`, Docker with Buildx, and kubectl compatible
with your cluster. It must reach enterprise GitHub, Harbor, the Rancher Kubernetes API, and the Python
package index used to install `PyYAML==6.0.3`. The job uses Git directly because the source GHES installation
could not fetch the pinned checkout action. Tokens are process-scoped and are not stored in Git config.

Create a GitHub environment named `release`. Set repository/environment variables:

| Variable | Purpose |
| --- | --- |
| `RANCHER_CONTEXT` | Context present in the supplied kubeconfig |
| `IMSERVERLESS_OWNER` | Authorized platform owner identity |
| `IMSERVERLESS_DOMAIN` | Platform domain, e.g. `GAR` |
| `IMSERVERLESS_HOSTNAME` | Optional override for the base app hostname; suffix apps use release.yaml |

Supply `RANCHER_KUBECONFIG` as a GitHub Secret, or mount a protected kubeconfig read-only into the runner
and set `RUNNER_KUBECONFIG` to its path. The runner script provides the mounted-file option.
Runner fallback variables are `RUNNER_RANCHER_CONTEXT`, `RUNNER_IMSERVERLESS_OWNER`,
`RUNNER_IMSERVERLESS_DOMAIN`, and `RUNNER_IMSERVERLESS_HOSTNAME`; GitHub settings take precedence.
The identity needs access to the target namespace's Secrets and deployments, pod observation, and
port-forward access to `imserverless/service/deployment-gateway` on port 50053. Request appropriate
platform permissions; the template does not provision RBAC or create credential Secrets.
The gateway contract is copied from the source project's IMServerless UI 2.7.0 integration.
Its proxy bypass includes the source Rancher host; configure `NO_PROXY` for other environments.

For Harbor, set `REGISTRY_USERNAME` and `REGISTRY_PASSWORD` as GitHub Secrets, or let a deployment job
read the target registry entry from `secrets.pull` through its cluster credential. The workflow writes
only that registry entry into a temporary Docker configuration and removes job credentials at completion.

## Optional Windows runner installer

After creating the HTTPS `origin`, with PowerShell 7, Docker Desktop's Linux engine, and Git Credential
Manager authentication able to administer that repository:

```powershell
.\runner\start-runner.ps1 -Kubeconfig C:\secure\rancher.kubeconfig -Context cn01-linux -Owner YOUR_OWNER -Domain GAR
```

This is an explicit operational action: it downloads checksum-pinned runner/kubectl artifacts, builds a
runner image, registers it with `origin`, and starts a persistent Docker container. It is not part of
local template creation. Versions/checksums were inherited from the reviewed source; check compatibility
when upgrading. Use `-BaseImage` to override the runner's shared base. The script expects the base to
provide Git, Bash, Python/venv and the Linux libraries required by the Actions runner.
Re-running starts an existing container; it does not reconfigure its credentials or update its image.

The Docker socket grants control of the host engine. Use this setup only for trusted repositories on
a host you control. It is not a shared multi-tenant Rancher runner design. Keep credentials scoped to
the intended workloads. Runner registrations are repository-specific; matching labels alone do not
let other repositories use one. Organization sharing requires separately approved registration/access.

## Release behavior and recovery

Images use `ci-<run-id>-<attempt>-<commit-prefix>` tags, then deploy by immutable digest.
Before pushing, offline tests run inside the packaged image with networking disabled; test files are
copied into a stopped container so Docker-in-Docker host path differences do not break bind mounts.
The helper checks Secrets, calls CreateApp or Modify once, waits for the generated deployment,
sets `imagePullPolicy: Always`, attaches runtime Secret references, and checks rollout, running digest,
and IMServerless `Available`. A resourceVersion test rejects concurrent deployment edits.

GitHub concurrency is per repository and branch; never configure multiple repositories to deploy the
same app. Deployment does not invoke a business job, create a trigger, clean up older app versions,
or prove manufacturing service access. Schedule management remains a separate platform action.
If a mutation times out after submission, inspect the actual app and deployment before retrying;
a lost response can still mean the operation succeeded. There is no automatic mutation retry or rollback.
