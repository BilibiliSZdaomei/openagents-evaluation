"""Build the original pinned application source without using the deployment checkout as a Docker context."""
import io
import json
import os
import subprocess
import tarfile
import tempfile
from pathlib import Path


def run(args, **opts):
    return subprocess.run(args, check=True, **opts)


def build():
    root = Path(__file__).resolve().parent
    lock = json.loads((root / "images.lock.json").read_text(encoding="utf-8"))
    commit = lock["upstream_commit"]
    from image_import import ensure_aliases, tag_targets
    dependencies = [dep for dep in lock["images"] if dep.get("pull")]
    tag_targets(dependencies)
    for dep in dependencies:
        run(["docker", "pull", "--platform", "linux/amd64", dep["pull"]])
    ensure_aliases(dependencies)
    temp_root = Path(os.getenv("OPENAGENTS_BUILD_TEMP") or tempfile.gettempdir()).resolve()
    if temp_root.is_relative_to(root):
        raise ValueError("Choose an external build temporary directory outside this checkout.")
    with tempfile.TemporaryDirectory(dir=temp_root) as folder:
        tmp = Path(folder)
        git = ["git", "-C", str(tmp)]
        run(git + ["init", "--bare", "--quiet"])
        run(git + ["fetch", "--quiet", "--depth=1", "--no-tags", lock["upstream_url"], commit])
        if subprocess.check_output(git + ["rev-parse", "FETCH_HEAD"], text=True).strip() != commit:
            raise ValueError("Unexpected upstream commit")
        for kind, part, dockerfile, base, tag in [
            ("backend", "backend", "production.Dockerfile", "python:3.12-slim", "backend-src"),
            ("frontend", "frontend", "Dockerfile", "node:20-alpine", "web-src")
        ]:
            archive = tmp / "upstream.tar"
            run(git + ["archive", "--format=tar", "-o", str(archive), commit + ":workspace/" + part])
            context = tmp / "build.tar"
            patched = False
            with tarfile.open(archive, "r:") as original, tarfile.open(context, "w") as target:
                for member in original:
                    payload = original.extractfile(member) if member.isfile() else None
                    if member.name == dockerfile:
                        text = payload.read().decode()
                        if not text.startswith("FROM " + base + "\n"):
                            raise ValueError("Unrecognized upstream Dockerfile base")
                        data = text.replace("FROM " + base, "FROM " + lock["build_bases"][kind], 1).encode()
                        member.size = len(data)
                        payload = io.BytesIO(data)
                        patched = True
                    target.addfile(member, payload)
            if not patched:
                raise ValueError("Expected upstream Dockerfile missing")
            flags = ["--build-arg", f"RELEASE_SHA={commit}"] if kind == "backend" else ["--build-arg","NEXT_PUBLIC_API_URL=/wsapi"]
            with context.open("rb") as stdin:
                run(["docker", "build", "--platform", "linux/amd64", "-f", dockerfile,
                     "-t", "openagents-evaluation/" + tag + ":2500fcc", *flags, "-"], stdin=stdin)


if __name__ == "__main__":
    build()
