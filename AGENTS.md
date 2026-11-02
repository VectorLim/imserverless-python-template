# Engineering workflow

Trace entry points and callers before editing. Use the smallest complete change and preserve unrelated work.
Keep business logic in pipeline/, runtime dispatch in main.py, and deployment logic in automation/.
release.yaml is the authoritative application target, Secret reference list, and branch map.
Use developer-selected branch names; never infer ENV_MODE from the Git branch name.
Never commit credentials, .env files, kubeconfigs, output data, or runner registration files.
Run `python -m unittest -v test_main test_release` after relevant changes.
Keep packaged tests offline. Deployment verification does not prove a business job ran.
Do not push images, register runners, or change live resources without authorization.
Do not retry an accepted IMServerless mutation after a lost response; inspect its state first.
