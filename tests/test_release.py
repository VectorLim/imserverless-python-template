"""Offline release contract checks: python -m unittest -v tests.test_release."""

import base64
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import yaml

from automation import cluster as kube, gateway, release
from automation.target import (
    CONFIG,
    ROOT,
    Target,
    app_spec,
    next_version,
    release_branches,
)

CONFIG = Path(__file__).parent / "fixtures/release.yaml"
TARGET = Target(CONFIG)
IMAGE = TARGET.repository + "@sha256:" + "a" * 64
HOST = "example-app.s33prod.mfg.intel.com"
DEPLOY = {
    "kubeconfig": "offline",
    "context": "cn01-linux",
    "owner": "offline-owner",
    "domain": "GAR",
    "hostname": HOST,
}


def deployment():
    return {
        "metadata": {
            "name": "example-app-1-17-deployment",
            "resourceVersion": "123",
        },
        "spec": {
            "selector": {"matchLabels": {"app": "example-app-1-17"}},
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": "example-app",
                            "image": IMAGE,
                            "imagePullPolicy": "Always",
                            "env": [
                                {"name": key, "value": value}
                                for key, value in {
                                    "ENV_MODE": "test",
                                    "SITE": "KM",
                                    "SCRIPT_NAME": "example",
                                }.items()
                            ],
                        }
                    ]
                }
            },
        },
    }


class ReleaseTest(unittest.TestCase):
    def test_repository_branch_configuration_resolves_distinct_targets(self):
        targets = [Target(branch=branch) for branch in release_branches()]
        self.assertEqual(len({target.function for target in targets}), len(targets))
        self.assertEqual(len({target.repository for target in targets}), len(targets))
        for target in targets:
            self.assertNotIn("secrets", target.spec)
            self.assertNotIn("branches", target.spec)

    def test_target_comes_from_release_yaml(self):
        self.assertEqual(
            (TARGET.namespace, TARGET.function, TARGET.repository, TARGET.registry),
            (
                "icmpcs-soims",
                "example-app",
                "amr-registry.caas.intel.com/soia/example-app",
                "amr-registry.caas.intel.com",
            ),
        )
        self.assertEqual(
            set(TARGET.secrets),
            {
                "example-runtime",
                "example-api",
                "itcaas-regcred",
                "example-share",
            },
        )
        self.assertEqual(Target(CONFIG, branch="release").function, "example-app")

    def test_custom_branch_targets_separate_app_and_image(self):
        target = Target(CONFIG, branch="sandbox")
        self.assertEqual(
            (target.namespace, target.function, target.repository),
            (
                "icmpcs-soims",
                "example-app-sandbox",
                "amr-registry.caas.intel.com/soia/example-app-sandbox",
            ),
        )
        self.assertEqual(target.secrets, TARGET.secrets)
        image = target.repository + "@sha256:" + "a" * 64
        spec = app_spec(target, image, "", "1.0", False)
        self.assertEqual(
            (spec["funcname"], spec["dnshostname"]),
            ("example-app-sandbox", "example-app-sandbox.s33prod.mfg.intel.com"),
        )
        self.assertEqual(TARGET.function, "example-app")
        with self.assertRaises(ValueError):
            app_spec(target, IMAGE, "", "1.0", False)
        with self.assertRaises(ValueError):
            Target(CONFIG, branch="feature")

    def test_branches_come_from_release_yaml_and_are_validated(self):
        self.assertEqual(release_branches(CONFIG), {"release": "", "sandbox": "-sandbox"})
        for branches in ({"release": "", "sandbox": ""}, {"release": "_Bad"}, {}):
            with self.subTest(branches=branches), self.assertRaises(ValueError):
                release_branches(self.write_config(branches=branches))

    def test_target_rejects_production_mode(self):
        spec = yaml.safe_load(CONFIG.read_text())
        spec["containers"][0]["environmentvariable"]["ENV_MODE"] = "prod"
        with self.assertRaisesRegex(ValueError, "ENV_MODE"):
            Target(self.write_config(**spec))

    def write_config(self, **changes):
        spec = yaml.safe_load(CONFIG.read_text())
        spec.update(changes)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        config = Path(folder.name) / "release.yaml"
        config.write_text(yaml.safe_dump(spec))
        return config

    def test_registry_config_selects_only_target_registry(self):
        registry = TARGET.registry
        config = {
            "auths": {
                registry: {"auth": "b2ZmbGluZTpwYXNzd29yZA=="},
                "other.example": {"auth": "do-not-copy"},
            }
        }
        cluster = Mock()
        cluster.get.return_value = {
            "data": {
                ".dockerconfigjson": base64.b64encode(
                    json.dumps(config).encode()
                ).decode()
            }
        }
        with tempfile.TemporaryDirectory() as folder:
            kube.registry_config(cluster, folder, TARGET)
            saved = json.loads((Path(folder) / "config.json").read_text())
            self.assertEqual(saved, {"auths": {registry: config["auths"][registry]}})
            cluster.get.return_value = {
                "data": {
                    ".dockerconfigjson": base64.b64encode(b'{"auths":{}}').decode()
                }
            }
            with self.assertRaises(ValueError):
                kube.registry_config(cluster, folder, TARGET)

    def test_every_push_is_gated_by_release_branches(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())
        triggers = workflow.get("on", workflow.get(True))
        self.assertEqual(triggers["push"]["branches"], ["**"])
        job = workflow["jobs"]["release"]
        self.assertEqual(
            job["env"]["DEPLOY"], "${{ github.event_name == 'push' || inputs.deploy }}"
        )
        gated = [
            step
            for step in job["steps"]
            if "env.RELEASE == 'true'" in step.get("if", "")
        ]
        deploying = [
            step["name"] for step in gated if "env.DEPLOY == 'true'" in step["if"]
        ]
        self.assertEqual(len(gated), 7)
        self.assertEqual(
            deploying,
            [
                "Prepare deployment credentials and check prerequisites",
                "Update IMServerless and verify Rancher rollout",
            ],
        )

    def test_versions_are_numeric_and_scoped_to_selected_app(self):
        app = "example-app"
        self.assertEqual(
            next_version(
                ["unrelated-app-1-30-deployment", "another-app-1-16-deployment"], app
            ),
            ("1.0", False),
        )
        self.assertEqual(
            next_version(
                ["example-app-1-9-deployment", "example-app-1-16-deployment"],
                app,
            ),
            ("1.17", True),
        )
        self.assertEqual(
            next_version(
                [
                    "example-app-sandbox-1-40-deployment",
                    "example-app-1-2-deployment",
                ],
                app,
            ),
            ("1.3", True),
        )
        self.assertEqual(
            next_version(["example-app-1-2-deployment"], app + "-sandbox"),
            ("1.0", False),
        )
        for name in ("example-app-mystery", "example-app-1-999-deployment"):
            with self.assertRaises(ValueError):
                next_version([name], app)

    def test_spec_preserves_mount_and_test_contract(self):
        spec = app_spec(TARGET, IMAGE, HOST, "1.17", True)
        self.assertEqual(
            (spec["namespace"], spec["funcname"], spec["action"]),
            ("icmpcs-soims", "example-app", "update"),
        )
        self.assertEqual(spec["containers"][0]["image"], IMAGE)
        self.assertEqual(spec["containers"][0]["volume"][0]["mountpath"], "/mnt/data")
        self.assertEqual(
            spec["containers"][0]["environmentvariable"]["ENV_MODE"], "test"
        )
        self.assertNotIn("secrets", spec)
        self.assertEqual(
            TARGET.spec["containers"][0]["image"],
            "amr-registry.caas.intel.com/soia/example-app:pending",
        )
        self.assertEqual(app_spec(TARGET, IMAGE, "", "1.17", True)["dnshostname"], HOST)
        for image in (
            TARGET.repository + ":latest",
            IMAGE.replace("example-app", "other"),
        ):
            with self.assertRaises(ValueError):
                app_spec(TARGET, image, HOST, "1.17", True)
        with self.assertRaises(ValueError):
            app_spec(TARGET, IMAGE, "other-app.s33prod.mfg.intel.com", "1.17", True)

    def test_preflight_requires_nonempty_runtime_credentials(self):
        def secret(kind, name):
            keys = {
                "example-runtime": ("SERVICE_USER", "SERVICE_TOKEN"),
                "example-api": ("API_KEY", "API_CONFIG"),
                "itcaas-regcred": (".dockerconfigjson",),
                "example-share": ("username", "password"),
            }[name]
            return {
                "data": {
                    key: base64.b64encode(b"offline-value").decode() for key in keys
                }
            }

        cluster = Mock()
        cluster.get.side_effect = secret
        kube.preflight(cluster, TARGET)
        cluster.get.side_effect = None
        cluster.get.return_value = {"data": {"SERVICE_USER": "eA==", "SERVICE_TOKEN": ""}}
        with self.assertRaisesRegex(ValueError, "Secret"):
            kube.preflight(cluster, TARGET)

    def test_patch_targets_exact_container_and_rejects_changed_image(self):
        cluster = Mock()
        item = deployment()
        item["spec"]["template"]["spec"]["containers"][0]["env"].append(
            {"name": "SERVICE_TOKEN", "value": "old"}
        )
        kube.configure(cluster, item, IMAGE, TARGET)
        args = cluster.call.call_args.args
        self.assertEqual(
            args[:3], ("patch", "deployment", "example-app-1-17-deployment")
        )
        patch_body = json.loads(args[-1])
        self.assertEqual(
            patch_body[0],
            {"op": "test", "path": "/metadata/resourceVersion", "value": "123"},
        )
        self.assertNotIn("old", json.dumps(patch_body))
        self.assertIn("example-runtime", json.dumps(patch_body))
        self.assertIn("itcaas-regcred", json.dumps(patch_body))
        with self.assertRaises(ValueError):
            kube.configure(cluster, item, IMAGE.replace("a", "b"), TARGET)

    def test_verify_rejects_unready_or_wrong_digest_pod(self):
        cluster = Mock()
        cluster.get.return_value = deployment()
        pod = {
            "metadata": {"name": "new-pod"},
            "status": {
                "containerStatuses": [
                    {"name": "example-app", "ready": True, "imageID": IMAGE}
                ]
            },
        }
        cluster.call.return_value = json.dumps({"items": [pod]})
        self.assertEqual(
            kube.verify(cluster, "example-app-1-17-deployment", IMAGE), ["new-pod"]
        )
        for ready, image in ((False, IMAGE), (True, IMAGE + "0")):
            pod["status"]["containerStatuses"][0].update(ready=ready, imageID=image)
            cluster.call.return_value = json.dumps({"items": [pod]})
            with self.assertRaises(RuntimeError):
                kube.verify(cluster, "example-app-1-17-deployment", IMAGE)

    def test_deploy_uses_modify_once_and_fails_before_gateway_if_secrets_missing(self):
        client = Mock()
        client.call.side_effect = [
            {1: [b"example-app-1-16-deployment"], 2: [1]},
            {1: [1]},
            {1: [b"Available"], 2: [1]},
        ]
        cluster = Mock()
        cluster.get.return_value = {"items": [deployment()]}

        @contextmanager
        def connection(*unused):
            yield client

        with patch.object(release, "Cluster", return_value=cluster), patch.object(
            release, "tunnel", side_effect=connection
        ), patch.object(release, "preflight") as preflight, patch.object(
            release, "configure"
        ) as configure, patch.object(
            release, "verify", return_value=["new-pod"]
        ):
            result = release.deploy(TARGET, IMAGE, **DEPLOY)
            self.assertEqual(result["version"], "1.17")
            self.assertEqual(
                [call.args[0] for call in client.call.call_args_list],
                ["QueryAppVersion", "Modify", "QueryAppStatus"],
            )
            fields = client.call.call_args_list[1].args[1]
            self.assertEqual(fields[2], "offline-owner")
            self.assertEqual(json.loads(fields[1])["containers"][0]["image"], IMAGE)
            configure.assert_called_once()
            client.reset_mock()
            preflight.side_effect = ValueError("missing secret")
            with self.assertRaises(ValueError):
                release.deploy(TARGET, IMAGE, **DEPLOY)
            client.call.assert_not_called()

    def test_create_ownership_and_lost_response_are_not_retried(self):
        client = Mock()
        client.call.side_effect = [{2: [1]}, {1: [1]}, {1: [b"Available"], 2: [1]}]
        cluster = Mock()
        item = deployment()
        item["metadata"]["name"] = "example-app-1-0-deployment"
        cluster.get.return_value = {"items": [item]}

        @contextmanager
        def connection(*unused):
            yield client

        with patch.object(release, "Cluster", return_value=cluster), patch.object(
            release, "tunnel", side_effect=connection
        ), patch.object(release, "preflight"), patch.object(
            release, "configure"
        ), patch.object(
            release, "verify", return_value=["new-pod"]
        ):
            release.deploy(TARGET, IMAGE, **DEPLOY)
            fields = client.call.call_args_list[1].args
            self.assertEqual(fields[0], "CreateApp")
            self.assertEqual((fields[1][4], fields[1][5]), ("offline-owner", "GAR"))
            client.reset_mock()
            client.call.side_effect = [{2: [1]}, TimeoutError("lost reply")]
            with self.assertRaises(TimeoutError):
                release.deploy(TARGET, IMAGE, **DEPLOY)
            self.assertEqual(client.call.call_count, 2)


class WireContractTest(unittest.TestCase):
    def test_unicode_and_multibyte_strings(self):
        payload = gateway.strings({1: "x" * 300, 4: "owner-ä½ å¥½"})
        fields = gateway.protobuf(payload)
        self.assertEqual(gateway.text(fields, 4), "owner-ä½ å¥½")
        self.assertEqual(gateway.text(fields, 1), "x" * 300)

    def test_grpc_status_and_truncated_frame_fail_closed(self):
        payload = b"\x08\x01"
        body = b"\x00" + len(payload).to_bytes(4, "big") + payload
        trailers = b"grpc-status: 0\r\n"
        good = body + b"\x80" + len(trailers).to_bytes(4, "big") + trailers
        gateway.succeeded(gateway.decode_reply(good))
        for broken in (body, good[:-1], good.replace(b"status: 0", b"status: 7")):
            with self.assertRaises((ValueError, RuntimeError)):
                gateway.decode_reply(broken)
        with self.assertRaises(ValueError):
            gateway.protobuf(b"\x0a\x05ab")


if __name__ == "__main__":
    unittest.main()
