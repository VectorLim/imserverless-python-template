# Source and decisions

Created 2026-11-02 from local SOIMS commit `99b039c` and the latest relevant VS Code GitHub Copilot
sessions for that exact workspace. The source worktree was clean at extraction. The source project
and its Git history were preserved. This repository begins with a new, independent history.

Latest sessions reviewed, newest first (times shown in Asia/Kuala_Lumpur):

- `307ff8a4-2847-457e-a314-a68a7cd050f0`, 2026-11-02 12:47, “Refactor code for GitHub workflow”.
  The user removed required/default prod/test branches and asked for one configuration YAML.
- `0b0a61e6-dac4-46fd-8f9a-e5b3d0a5e246`, 2026-11-02 12:37, “Version increment and test branch setup”.
  Branch suffixes should separate apps/images, increment versions, and have a developer guide.
- `c918d9b6-c6b1-4e5f-a743-bf96002c2d98`, 2026-11-02 10:39, “Shared GitHub Actions runners on Rancher”.
  The discussion moved from shared organization infrastructure toward a repository-level setup
  developers can use with their own configuration.

Only the relevant decisions were carried over. Raw chat transcripts and their local paths are not copied.
`release.yaml` owns the AppSpec, Secret declarations and branch mappings. Workflow YAML and host JSON
remain where their respective platforms require them. Example branches are freely replaceable.

Reused: the existing deployment/gateway helper, release workflow, focused offline contract tests,
function host contract, and repository runner pattern. Replaced: SOIMS pipelines, hardcoded test app
identity, personal owner, manufacturing database/AED credentials, share mounts and historical documentation.
No production records, encrypted credentials, installers or binaries are included.

The shared SOIMS base remains an explicit configurable infrastructure dependency. The example app
uses only Python's standard library and does not call manufacturing services. The existing namespace
is retained as the environment default; other target names are examples to replace before releasing.
