"""Release command line: python -m automation {plan,preflight,registry-login,deploy} --help."""

import argparse
from pathlib import Path

from .cluster import Cluster, preflight, registry_config
from .release import deploy
from .target import CONFIG, Target, release_branches


def plan(args):
    if args.branch not in release_branches(args.config):
        print("RELEASE=false")
        return
    target = Target(args.config, args.branch)
    print(
        f"RELEASE=true\nREGISTRY={target.registry}\nIMAGE_REPOSITORY={target.repository}"
    )


def main():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", type=Path, default=CONFIG)
    common.add_argument(
        "--branch", required=True, help="Git branch listed under release.yaml branches"
    )
    cluster = argparse.ArgumentParser(add_help=False, parents=[common])
    cluster.add_argument("--kubeconfig", required=True, type=Path)
    cluster.add_argument("--context", required=True)

    parser = argparse.ArgumentParser(prog="python -m automation", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "plan", parents=[common], help="print RELEASE and image settings for GITHUB_ENV"
    )
    commands.add_parser(
        "preflight", parents=[cluster], help="check the required Secrets"
    )
    login = commands.add_parser(
        "registry-login",
        parents=[cluster],
        help="write a Docker config from the pull Secret",
    )
    login.add_argument("--docker-config", required=True, type=Path)
    release = commands.add_parser(
        "deploy", parents=[cluster], help="release an image digest"
    )
    release.add_argument("--image", required=True)
    release.add_argument(
        "--hostname", default="", help="overrides the unsuffixed AppSpec dnshostname"
    )
    release.add_argument("--owner", required=True)
    release.add_argument("--domain", required=True)
    args = parser.parse_args()

    if args.command == "plan":
        return plan(args)
    target = Target(args.config, args.branch)
    if args.command == "deploy":
        return deploy(
            target,
            args.image,
            kubeconfig=args.kubeconfig,
            context=args.context,
            owner=args.owner,
            domain=args.domain,
            hostname=args.hostname,
        )
    connection = Cluster(args.kubeconfig, args.context, target.namespace)
    if args.command == "preflight":
        preflight(connection, target)
    else:
        registry_config(connection, args.docker_config, target)


if __name__ == "__main__":
    main()
