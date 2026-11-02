"""The release target read from release.yaml: AppSpec, Secret names and branch map."""

import copy
from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "release.yaml"
NAME = r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?"
SECRET = r"[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?"
SUFFIX = r"(-[a-z0-9]+)*"


def load(config=CONFIG):
    """Split release.yaml into the AppSpec and the keys that are never sent to IMServerless."""
    spec = yaml.safe_load(Path(config).read_text(encoding="utf-8"))
    return spec, spec.pop("secrets"), spec.pop("branches")


def release_branches(config=CONFIG):
    branches = load(config)[2]
    if not isinstance(branches, dict) or not branches:
        raise ValueError(
            "release.yaml branches must map at least one branch to a suffix"
        )
    for branch, suffix in branches.items():
        if (
            not isinstance(branch, str)
            or not isinstance(suffix, str)
            or not re.fullmatch(SUFFIX, suffix)
        ):
            raise ValueError(f"Invalid branches entry {branch!r}: {suffix!r}")
    if len(set(branches.values())) != len(branches):
        raise ValueError(
            "Each release branch needs its own suffix so apps do not collide"
        )
    return branches


class Target:
    """The reviewed release target of this repository; nothing else is mutated."""

    def __init__(self, config=CONFIG, branch=None):
        spec, secrets, _ = load(config)
        self.suffix = "" if branch is None else release_branches(config).get(branch)
        if self.suffix is None:
            raise ValueError(
                f"Branch {branch!r} is not listed under release.yaml branches"
            )
        if len(spec["containers"]) != 1:
            raise ValueError("Exactly one AppSpec container is supported")
        container = spec["containers"][0]
        image = container["image"].split("@", 1)[0]
        base = re.sub(r":[\w.-]+$", "", image)
        self.repository = base + self.suffix
        container["image"] = self.repository + image[len(base) :]
        function = spec["funcname"]
        spec["funcname"] += self.suffix
        host = spec.get("dnshostname", "")
        if host.startswith(function + "."):
            spec["dnshostname"] = spec["funcname"] + host[len(function) :]
        self.spec = spec
        self.namespace, self.function = spec["namespace"], spec["funcname"]
        if not all(
            isinstance(value, str) and re.fullmatch(NAME, value)
            for value in (self.namespace, self.function)
        ):
            raise ValueError("AppSpec namespace and funcname must be DNS labels")
        self.registry = self.repository.split("/", 1)[0]
        if not re.fullmatch(
            r"[a-z0-9.-]+\.[a-z]+(:\d+)?(/[a-z0-9._-]+)+", self.repository
        ):
            raise ValueError("AppSpec image must name a registry repository")
        self.environment = container.get("environmentvariable") or {}
        # Production writes need an explicit, separately reviewed change.
        if self.environment.get("ENV_MODE") != "test":
            raise ValueError("This release template only deploys ENV_MODE: test")
        self.pull_secret = secrets["pull"]
        self.env_secrets = secrets.get("env") or {}
        self.secrets = {
            **(secrets.get("check") or {}),
            **self.env_secrets,
            self.pull_secret: [".dockerconfigjson"],
        }
        for name, keys in self.secrets.items():
            if (
                not re.fullmatch(SECRET, name)
                or not keys
                or not all(isinstance(key, str) for key in keys)
            ):
                raise ValueError(f"Invalid Secret entry {name!r} in release.yaml")

    def deployment_name(self, version):
        return f"{self.function}-{version.replace('.', '-')}-deployment"


def next_version(names, function):
    versions = []
    for name in names:
        if not name.startswith(function + "-"):
            continue
        match = re.fullmatch(re.escape(function) + r"-(\d+)-(\d+)-deployment", name)
        if not match:
            # Another app whose name extends this one, e.g. <function>-test.
            if re.fullmatch(NAME + r"-\d+-\d+-deployment", name):
                continue
            raise ValueError("Unknown app version format; recheck platform contract")
        versions.append(tuple(map(int, match.groups())))
    if not versions:
        return "1.0", False
    major, minor = max(versions)
    if minor >= 999:
        raise ValueError("IMServerless minor version limit reached")
    return f"{major}.{minor + 1}", True


def app_spec(target, image, hostname, version, update):
    if not re.fullmatch(re.escape(target.repository) + r"@sha256:[0-9a-f]{64}", image):
        raise ValueError("Expected an immutable digest in the AppSpec image repository")
    spec = copy.deepcopy(target.spec)
    hostname = hostname or spec.get("dnshostname", "")
    if not re.fullmatch(
        re.escape(target.function) + r"\.[a-z0-9.-]+\.intel\.com", hostname
    ):
        raise ValueError("Expected a <funcname>.<cluster>.intel.com hostname")
    spec.update(
        dnshostname=hostname, version=version, action="update" if update else "create"
    )
    spec["containers"][0]["image"] = image
    return spec
