# Validation

Run locally from this repository:

```powershell
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m unittest -v test_main test_release
python -m automation plan --branch release
python -m automation plan --branch sandbox
python -m automation plan --branch feature/example
```

`test_release.py` uses a synthetic fixture to exercise Secret handling, mounts, branch suffixes,
version selection, immutable digests, concurrent-edit protection, CreateApp/Modify and gateway framing.
Its fixture remains independent of application configuration changes. One check also resolves all
configured repository branches to distinct app/image targets. All service and cluster responses are mocked.
`test_main.py` checks default/explicit dispatch, the platform result tuple, unknown scripts and rejected modes.

Local image checks:

```powershell
docker build -f dockerfile -t imserverless-template:local .
docker run --rm --network none --entrypoint python imserverless-template:local main.py
docker run --rm --network none --entrypoint python imserverless-template:local -m pip check
```

The shared base is known to contain incompatible python-dotenv requirements between DataSyncX and
imserverless-funcapp. Report that inherited result separately from application tests. Change to a compatible
base release when available; do not silently ignore pip check failures or force incompatible dependencies.
The release workflow runs behavioral tests rather than claiming the inherited base passes pip check.

Local tests and image checks do not prove live registry push, runner registration, authenticated cluster
access, platform rollout, scheduling, or production business behavior. Those require separately configured
credentials and authorized end-to-end validation. See [LOCAL-VALIDATION.md](../LOCAL-VALIDATION.md) for creation-time evidence.
