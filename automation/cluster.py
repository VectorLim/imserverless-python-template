"""kubectl access to the target namespace: Secret checks, workload patching and rollout checks."""

import base64
import json
import os
from pathlib import Path
import subprocess


class Cluster:
    def __init__(self, kubeconfig, context, namespace):
        self.command = [
            "kubectl",
            "--kubeconfig",
            str(kubeconfig),
            "--context",
            context,
            "--request-timeout=30s",
            "-n",
            namespace,
        ]

    def call(self, *arguments):
        result = subprocess.run(
            self.command + list(arguments),
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
        if result.returncode:
            # Secret operations must not surface credential material through kubectl errors.
            raise RuntimeError(
                "kubectl failed; check network, target and RBAC (output suppressed)"
            )
        return result.stdout

    def get(self, kind, name=None):
        args = ["get", kind] + ([name] if name else []) + ["-o", "json"]
        return json.loads(self.call(*args))


def preflight(cluster, target):
    for name, keys in target.secrets.items():
        data = cluster.get("secret", name).get("data", {})
        if not all(
            key in data and base64.b64decode(data[key], validate=True).strip()
            for key in keys
        ):
            raise ValueError(f"Required nonempty keys missing in Secret {name}")


def registry_config(cluster, directory, target):
    """Use the existing Rancher registry Secret without putting credentials in YAML."""
    secret = cluster.get("secret", target.pull_secret)
    config = json.loads(
        base64.b64decode(secret["data"][".dockerconfigjson"], validate=True)
    )
    matches = [
        value
        for key, value in config.get("auths", {}).items()
        if key.removeprefix("https://").removeprefix("http://").rstrip("/")
        == target.registry
    ]
    if len(matches) != 1 or not (
        matches[0].get("auth") or matches[0].get("identitytoken")
    ):
        raise ValueError(
            "Registry Secret has no inline credentials for the target registry"
        )
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = directory / "config.json"
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump({"auths": {target.registry: matches[0]}}, output)


def configure(cluster, deployment, image, target):
    containers = deployment["spec"]["template"]["spec"]["containers"]
    if len(containers) != 1 or containers[0]["image"] != image:
        raise ValueError("Expected exactly one container with the requested digest")
    container = containers[0]
    # Inline environment entries override envFrom; remove any credentials left by the platform.
    credentials = {key for keys in target.env_secrets.values() for key in keys}
    environment = [
        entry for entry in container.get("env", []) if entry["name"] not in credentials
    ]
    settings = {entry["name"]: entry.get("value") for entry in environment}
    if any(
        settings.get(key) != str(value) for key, value in target.environment.items()
    ):
        raise ValueError(
            "Generated deployment did not preserve the AppSpec environment"
        )
    env_from = [
        entry
        for entry in container.get("envFrom", [])
        if entry.get("secretRef", {}).get("name") not in target.env_secrets
    ]
    env_from.extend(
        {"secretRef": {"name": name, "optional": False}} for name in target.env_secrets
    )
    container_path = "/spec/template/spec/containers/0/"
    # JSON Patch tests prevent changing a concurrently edited workload.
    patch = [
        {
            "op": "test",
            "path": "/metadata/resourceVersion",
            "value": deployment["metadata"]["resourceVersion"],
        },
        {"op": "add", "path": container_path + "imagePullPolicy", "value": "Always"},
        {"op": "add", "path": container_path + "env", "value": environment},
        {"op": "add", "path": container_path + "envFrom", "value": env_from},
        {
            "op": "add",
            "path": "/spec/template/spec/imagePullSecrets",
            "value": [{"name": target.pull_secret}],
        },
    ]
    cluster.call(
        "patch",
        "deployment",
        deployment["metadata"]["name"],
        "--type=json",
        "--patch",
        json.dumps(patch),
    )


def verify(cluster, name, image):
    cluster.call("rollout", "status", "deployment/" + name, "--timeout=180s")
    deployment = cluster.get("deployment", name)
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    if container["image"] != image or container.get("imagePullPolicy") != "Always":
        raise RuntimeError("Deployment image/pull policy verification failed")
    labels = deployment["spec"]["selector"]["matchLabels"]
    selector = ",".join(f"{key}={value}" for key, value in sorted(labels.items()))
    pods = json.loads(cluster.call("get", "pods", "-l", selector, "-o", "json"))[
        "items"
    ]
    active = [pod for pod in pods if not pod["metadata"].get("deletionTimestamp")]
    if not active:
        raise RuntimeError("No running pods found for the new deployment")
    digest = image.split("@", 1)[1]
    for pod in active:
        statuses = [
            status
            for status in pod.get("status", {}).get("containerStatuses", [])
            if status["name"] == container["name"]
        ]
        if (
            len(statuses) != 1
            or not statuses[0].get("ready")
            or not statuses[0].get("imageID", "").endswith(digest)
        ):
            raise RuntimeError("Pod readiness or running digest verification failed")
    return [pod["metadata"]["name"] for pod in active]
