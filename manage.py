"""Portable OpenAgents evaluation deployment. Uses the host Docker CLI and Python stdlib."""
import argparse
import csv
import getpass
import hashlib
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener
import json
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if os.name == "nt":
    DEFAULT_CONFIG = Path(os.environ["LOCALAPPDATA"]) / "OpenAgentsEvaluation" / "config"
else:
    DEFAULT_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "openagents-evaluation"


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def private_config(directory):
    if directory.is_relative_to(ROOT):
        raise ValueError("Choose a private configuration directory outside this checkout.")
    allowed = {"postgres-password", "deepseek-key", "login-password"}
    if directory.is_dir() and any(child.name not in allowed or child.is_symlink() or not child.is_file()
                                  for child in directory.iterdir()):
        raise ValueError("Use an empty, dedicated OpenAgents private configuration directory.")
    if directory == Path(directory.anchor) or directory == Path.home().resolve():
        raise ValueError("Use a dedicated configuration subdirectory.")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        directory.chmod(0o700)
    else:
        output = subprocess.check_output(["whoami", "/user", "/fo", "csv", "/nh"])
        sid = next(csv.reader(output.decode(errors="replace").splitlines()))[-1]
        if not re.fullmatch(r"S-1-[0-9-]+", sid):
            raise ValueError("Unable to identify Windows account for private file access.")
        run(["icacls", str(directory), "/inheritance:r", "/grant:r", f"*{sid}:(OI)(CI)F",
             "*S-1-5-18:(OI)(CI)F"], stdout=subprocess.DEVNULL)


def configure(directory):
    private_config(directory)
    for name, env, label in [("deepseek-key", "OPENAGENTS_DEEPSEEK_KEY", "DeepSeek API Key"),
                             ("login-password", "OPENAGENTS_LOGIN_PASSWORD", "New admin password (12+ characters)"),
                             ("postgres-password", None, None)]:
        path = directory / name
        if path.exists():
            continue
        value = secrets.token_hex(32) if env is None else (os.getenv(env) or getpass.getpass(label + ": ")).strip()
        if len(value) < 12 or any(c in value for c in "\n\r\x00"):
            raise ValueError(f"Invalid or empty value for {name}")
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as stream:
            stream.write(value + "\n")


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def verify_images(source_build=False):
    lock = json.loads((ROOT / "images.lock.json").read_text(encoding="utf-8"))
    for image in lock["images"]:
        if source_build and not image.get("pull"):
            continue
        data = run(["docker", "image", "inspect", image["tag"]], capture_output=True, text=True)
        image_info = json.loads(data.stdout)[0]
        if (image_info["Id"], image_info["Os"], image_info["Architecture"]) != (image["id"], "linux", "amd64"):
            raise ValueError("Image mismatch: " + image["tag"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["init", "up", "stop", "status", "images", "build"])
    parser.add_argument("archive", nargs="?", type=Path, help="Docker image bundle for the images action")
    parser.add_argument("--config-dir", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--project", default="openagents-evaluation")
    parser.add_argument("--port", type=int, default=18811)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--source", action="store_true", help="Run locally rebuilt official source images")
    a = parser.parse_args()
    directory = a.config_dir.resolve()
    if a.action == "images":
        if not a.archive or not a.archive.is_file():
            raise ValueError("Supply a downloaded Docker image archive.")
        # Check the release checksum before asking the daemon to import the file.
        sums = a.archive.parent / "SHA256SUMS"
        if not sums.is_file():
            raise ValueError("Place the release SHA256SUMS next to the image archive.")
        expected = {}
        for line in sums.read_text(encoding="utf-8-sig").splitlines():
            if line.strip():
                checksum, name = line.split(maxsplit=1)
                expected[name.lstrip("* ")] = checksum
        if expected.get(a.archive.name) != digest(a.archive):
            raise ValueError("Release file name or SHA-256 mismatch")
        run(["docker", "load", "-i", str(a.archive.resolve())])
        verify_images()
        return
    if a.action == "build":
        from source_build import build
        build()
        return
    if a.action in ("init", "up"):
        configure(directory)
    if a.action == "init":
        return
    if not (1 <= a.port <= 65535):
        raise ValueError("Invalid port")
    env = {**os.environ, "OPENAGENTS_CONFIG":directory.as_posix(), "OPENAGENTS_PORT":str(a.port),
           "OPENAGENTS_BIND":a.bind, "COMPOSE_PROJECT_NAME":a.project}
    env.pop("OPENAGENTS_LOGIN_PASSWORD", None)
    env.pop("OPENAGENTS_DEEPSEEK_KEY", None)
    if a.source:
        env.update(OA_BACKEND_IMAGE="openagents-evaluation/backend-src:2500fcc",
                   OA_WEB_IMAGE="openagents-evaluation/web-src:2500fcc")
    compose = ["docker", "compose", "-p", a.project, "-f", str(ROOT / "compose.yaml")]
    if a.action == "up":
        verify_images(a.source)
        run(compose + ["up", "-d", "--pull", "never"], env=env)
        opener = build_opener(ProxyHandler({}))
        host = "127.0.0.1" if a.bind in ("127.0.0.1", "0.0.0.0") else a.bind
        display_host = "openagents.localhost" if host == "127.0.0.1" else host
        for _ in range(30):
            try:
                with opener.open(f"http://{host}:{a.port}/start/workspace", timeout=2):
                    raise ValueError("Workspace entry did not require authentication.")
            except HTTPError as error:
                if error.code == 401 and error.headers.get("WWW-Authenticate", "").startswith("Basic"):
                    break
            except (URLError, TimeoutError):
                pass
            time.sleep(1)
        else:
            raise ValueError("Workspace entry is not ready; inspect docker compose status and front logs.")
        print(f"Open http://{display_host}:{a.port}/start/workspace  (user: admin)")
    elif a.action == "stop":
        run(compose + ["stop"], env=env)
    else:
        run(compose + ["ps", "-a"], env=env)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as e:
        sys.exit(str(e))
