"""Release a built image digest to IMServerless, then verify its Kubernetes rollout.

The gateway wire contract comes from the locally verified IMServerless UI 2.7.0
client. Keep business execution and triggers outside this release command.
"""

import json
import os
import time

from .cluster import Cluster, configure, preflight, verify
from .gateway import succeeded, text, tunnel
from .target import app_spec, next_version


def wait_for(check, attempts, error):
    for _ in range(attempts):
        result = check()
        if result:
            return result
        time.sleep(2)
    raise error


def deploy(target, image, *, kubeconfig, context, owner, domain, hostname=""):
    # A hostname override names the unsuffixed app; suffixed apps derive their own.
    hostname = "" if target.suffix else hostname
    app_spec(target, image, hostname, "1.0", False)
    if not owner or not domain:
        raise ValueError("IMServerless owner and domain are required")
    cluster = Cluster(kubeconfig, context, target.namespace)
    preflight(cluster, target)
    with tunnel(kubeconfig, context) as gateway:
        reply = gateway.call("QueryAppVersion", {1: target.namespace})
        succeeded(reply, 2, 3)
        version, update = next_version(
            [value.decode("utf-8") for value in reply.get(1, [])], target.function
        )
        spec = json.dumps(app_spec(target, image, hostname, version, update))
        name = target.deployment_name(version)
        print(
            f"IMServerless {'update' if update else 'create'} {target.namespace}/{name}",
            flush=True,
        )
        # A lost mutation response can still mean success. Do not retry automatically.
        if update:
            succeeded(gateway.call("Modify", {1: spec, 2: owner, 3: domain}))
        else:
            succeeded(gateway.call("CreateApp", {1: spec, 4: owner, 5: domain}))

        def created():
            matches = [
                item
                for item in cluster.get("deployments")["items"]
                if item["metadata"]["name"] == name
            ]
            return matches[0] if len(matches) == 1 else None

        def available():
            status = gateway.call(
                "QueryAppStatus", {1: target.namespace, 2: version, 3: target.function}
            )
            succeeded(status, 2, 3)
            return text(status, 1) == "Available"

        deployment = wait_for(
            created,
            60,
            TimeoutError(
                "Accepted by IMServerless but deployment missing; inspect before retrying"
            ),
        )
        configure(cluster, deployment, image, target)
        pods = verify(cluster, name, image)
        wait_for(
            available,
            30,
            RuntimeError(
                "Kubernetes rollout completed but IMServerless is not Available"
            ),
        )
    result = {
        "namespace": target.namespace,
        "deployment": name,
        "image": image,
        "version": version,
        "status": "Available",
        "pods": pods,
    }
    summary = json.dumps(result, indent=2)
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as output:
            output.write("\n```json\n" + summary + "\n```\n")
    return result
