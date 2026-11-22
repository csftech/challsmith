"""python -m app.cli.cleanup [--instances-only] [--dry-run] [--yes]: pre-release cleanup (same as POST /cleanup),
only the instance reset, or only print which images it would remove."""
import argparse
import sys

from sqlalchemy.orm import Session

from app.clients import chall_manager_client, ctfd_client, docker_client, registry_client
from app.core.config import get_settings
from app.core.db import get_engine
from app.services import cleanup_service, image_cleanup_service

PLAN = """This will delete:
  - every chall-manager instance and leftover challenge-* container and network
  - every CTFd user that is not an admin
  - every web app session (you will be logged out)
  - the unused images and registry tags below, then the build cache and anonymous volumes;
    the registry is garbage-collected (it restarts for a moment)
Challenges, kept images and other data are kept. The image list is computed again after the
instances are gone, so it can only grow by images those instances used."""

PLAN_INSTANCES = """This will delete every chall-manager instance and leftover challenge-* container and network.
CTFd users, web sessions, challenges and images are kept."""


def _mb(n: int) -> str:
    return f"{n / 1e6:.0f} MB"


def format_plan(p: image_cleanup_service.CleanupPlan) -> str:
    out = [f"Unused images to remove: {len(p.images)} (at most {_mb(p.reclaimable_bytes)}: image sizes added up, shared layers counted per image):"]
    out += [f"  {i['ref'] or '<untagged> ' + i['id']}  {_mb(i['size'])}" for i in p.images]
    out.append(f"Registry tags to remove: {len(p.registry)}:")
    out += [f"  {t['repo']}:{t['tag']}  {t['digest']}" for t in p.registry]
    for title, kept in (("Kept images", p.kept_images), ("Kept registry tags", p.kept_registry)):
        out.append(f"{title}: {sum(map(len, kept.values()))}")
        for why, refs in sorted(kept.items()):
            out.append(f"  {why} ({len(refs)}): {', '.join(sorted(refs))}")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.cli.cleanup")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    ap.add_argument("--instances-only", action="store_true", help="only delete instances and their containers and networks (used at boot)")
    ap.add_argument("--dry-run", action="store_true", help="print the images and registry tags the cleanup would remove, change nothing")
    args = ap.parse_args(argv)
    if args.dry_run and args.instances_only:
        ap.error("--dry-run only applies to the full cleanup")
    cm = registry = None
    try:
        s = get_settings()
        docker = docker_client.DockerOps(s.upstream_http_proxy, s.upstream_https_proxy, s.upstream_no_proxy)
        if not args.instances_only:
            ctfd = ctfd_client.CtfdClient(s.ctfd_url, s.ctfd_admin_name, s.ctfd_admin_password)
            registry = registry_client.RegistryClient(s.registry_url)
            if args.dry_run or not args.yes:
                print(format_plan(image_cleanup_service.plan(docker, registry, ctfd, print)))
            if args.dry_run:
                return 0
        if not args.yes:
            print(PLAN_INSTANCES if args.instances_only else PLAN)
            try:
                answer = input(f"Type {cleanup_service.CONFIRM} to continue: ").strip()
            except EOFError:
                answer = ""
            if answer != cleanup_service.CONFIRM:
                print("aborted", file=sys.stderr)
                return 1
        cm = chall_manager_client.ChallManager(s.chall_manager_url)
        if args.instances_only:
            print(cleanup_service.reset_instances(cm, docker, print))
        else:
            with Session(get_engine()) as db:
                print(cleanup_service.run_cleanup(db, cm, ctfd, docker, registry, print))
    except Exception as e:
        print(f"cleanup failed: {e}", file=sys.stderr)
        return 1
    finally:
        for c in (cm, registry):
            if c is not None:
                c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
