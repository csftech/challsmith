"""python -m app.cli.cleanup [--yes]: pre-release cleanup, same as POST /cleanup."""
import argparse
import sys

from sqlalchemy.orm import Session

from app.clients import chall_manager_client, ctfd_client, docker_client
from app.core.config import get_settings
from app.core.db import get_engine
from app.services import cleanup_service

PLAN = """This will delete:
  - every chall-manager instance and leftover challenge-* container and network
  - every CTFd user that is not an admin
  - every web app session (you will be logged out)
Challenges, images and other data are kept."""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.cli.cleanup")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = ap.parse_args(argv)
    if not args.yes:
        print(PLAN)
        try:
            answer = input(f"Type {cleanup_service.CONFIRM} to continue: ").strip()
        except EOFError:
            answer = ""
        if answer != cleanup_service.CONFIRM:
            print("aborted", file=sys.stderr)
            return 1
    cm = None
    try:
        s = get_settings()
        cm = chall_manager_client.ChallManager(s.chall_manager_url)
        ctfd = ctfd_client.CtfdClient(s.ctfd_url, s.ctfd_admin_name, s.ctfd_admin_password)
        docker = docker_client.DockerOps(s.upstream_http_proxy, s.upstream_https_proxy, s.upstream_no_proxy)
        with Session(get_engine()) as db:
            print(cleanup_service.run_cleanup(db, cm, ctfd, docker, print))
    except Exception as e:
        print(f"cleanup failed: {e}", file=sys.stderr)
        return 1
    finally:
        if cm is not None:
            cm.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
