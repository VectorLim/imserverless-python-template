# Local creation checks - 2026-11-02

- Source checkout: `C:\Project\applications.manufacturing.analytics.atm.icmpcs-soims`, commit `99b039c`.
  `git status --short` was empty before and after extraction.
- Main-agent command: source checkout `.venv\Scripts\python.exe -m unittest -v test_main test_release`
  with this new repository as working directory. Passed: 20 tests (0.380 s).
- `python -m automation plan --branch release`: base example-app repository, exit 0.
- `python -m automation plan --branch sandbox`: example-app-sandbox repository, exit 0.
- `python -m automation plan --branch feature/example`: `RELEASE=false`, exit 0.
- PowerShell parser for `runner/start-runner.ps1`: no syntax errors. Installer was not executed.
- `docker build --pull=false -f dockerfile -t imserverless-template:local .`: passed.
  Resolved base digest: `sha256:4e4034b7d8a158d03fb8b688049e9caa79dd24a6b48ee6235e925aa4b0df5e45`.
- Offline image imports, sample `handle()` result, and absence of `.env`, `secret/key.key`,
  `secret/config_new.json`: passed. Image /app contains only main.py, pipeline, requirements.txt,
  and import-generated __pycache__.
- `docker run --rm --network none --entrypoint python imserverless-template:local main.py`:
  returned `(True, 'Example pipeline completed', 'Example pipeline completed')`.
- Packaged tests: `docker create --network none --entrypoint python ... -m unittest -v test_main`,
  copy test_main.py into the stopped container, start and inspect exit code: 4 tests passed, exit 0.
- Default `funchost_controller` started in a detached network-disabled container; logs showed loading
  `/app/main.py` and FunctionApplicationServer startup, container state `running`, exit code 0.
  This is startup observation, not an invocation through the platform RPC API. Test containers removed.
- `docker run --rm --network none --entrypoint python imserverless-template:local -m pip check`:
  exit 1, inherited base conflict: imserverless-funcapp 1.0.0 requires python-dotenv==1.0.1,
  installed version is 1.2.2. No application dependency was added to mask this conflict.
- Independent test runner repeated all 20 tests successfully and checked all 10 workflow run blocks
  with `bash -n` in the built image using LF-normalized stdin: exit 0.
- Main-agent final checks: local Markdown links valid; tracked file exclusion check passed (29 files);
  all 5 release helper implementation files are byte-for-byte identical to the source.
- Independent static review: no concrete implementation defects reported. Its missing validation link
  was corrected when this evidence file was added.

No remote repository was created, no image pushed, no runner registered, and no live platform resource
changed. The local image remains available as `imserverless-template:local`. GitHub Actions execution,
runner installation and live rollout remain untested for this template.
