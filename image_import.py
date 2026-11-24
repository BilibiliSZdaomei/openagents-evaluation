"""Import the approved Docker save bundle using only names owned by this deployment."""
import gzip
import hashlib
import io
import json
import re
import subprocess
import tarfile
from contextlib import contextmanager

BLOB = re.compile(r"blobs/sha256/([0-9a-f]{64})")


def inspect_image(reference):
    result = subprocess.run(["docker", "image", "inspect", reference], capture_output=True, text=True)
    if result.returncode:
        return None
    return json.loads(result.stdout)[0]


def saved_config_digest(reference):
    # containerd engine image IDs may identify manifests, not image configs.
    # Verify the actual config bytes referenced by docker-save's own manifest.
    process = subprocess.Popen(["docker", "image", "save", reference], stdout=subprocess.PIPE)
    configs = {}
    references = set()
    try:
        with process.stdout as stream, tarfile.open(fileobj=stream, mode="r|", bufsize=1024*1024) as archive:
            for item in archive:
                if not item.isfile() or item.size > 2 * 1024 * 1024:
                    continue
                if item.name == "manifest.json":
                    references.update(r["Config"].lstrip("./") for r in json.load(archive.extractfile(item)))
                elif BLOB.fullmatch(item.name) or re.fullmatch(r"[a-f0-9]{64}\.json", item.name):
                    raw = archive.extractfile(item).read()
                    if raw.lstrip().startswith(b"{"):
                        try:
                            info = json.loads(raw)
                        except (ValueError, UnicodeError):
                            continue
                        if isinstance(info,dict) and info.get("os") == "linux" and info.get("architecture") == "amd64" and "rootfs" in info:
                            configs[item.name] = "sha256:" + hashlib.sha256(raw).hexdigest()
            while stream.read(1024 * 1024):
                pass
    except BaseException:
        process.kill()
        process.wait()
        raise
    if process.wait():
        raise ValueError("Unable to verify local image bytes: " + reference)
    matches = {configs[name] for name in references if name in configs}
    if len(matches) != 1:
        raise ValueError("Expected one linux/amd64 image configuration: " + reference)
    return matches.pop()


def matches(reference, expected, known, verified_manifest=None):
    info = inspect_image(reference)
    if not info or (info["Os"], info["Architecture"]) != ("linux", "amd64"):
        return False
    handle = info["Id"]
    # The pinned platform manifest was verified against its config bytes on containerd.
    if handle == expected or handle == verified_manifest:
        return True
    if handle not in known:
        # Use the inspected immutable handle; an unrelated tag can move.
        known[handle] = saved_config_digest(handle)
    return known[handle] == expected


def tag_targets(images, known=None):
    known = {} if known is None else known
    rows = subprocess.check_output(["docker", "image", "ls", "--no-trunc", "--format",
                                   "{{.Repository}}:{{.Tag}} {{.ID}}"], text=True)
    existing = dict(row.rsplit(" ", 1) for row in rows.splitlines() if row)
    for image in images:
        alias = image["alias"]
        if alias in existing and not matches(alias, image["id"], known, image.get("manifest")):
            raise ValueError("Project image name already refers to a different ID: " + alias)
    return existing


def ensure_aliases(images):
    known = {}
    existing = tag_targets(images, known)
    for image in images:
        if image["alias"] in existing:
            continue
        # Legacy installations may have only the old tag; source builds pull
        # the dependency by registry digest. Never retag those shared names.
        for source in filter(None, (image["id"], image.get("pull"), image.get("tag"))):
            info = inspect_image(source)
            if info and matches(info["Id"], image["id"], known, image.get("manifest")):
                subprocess.run(["docker", "image", "tag", info["Id"], image["alias"]], check=True)
                break
        else:
            raise ValueError("Load the locked release image using manage.py images: " + image["alias"])


@contextmanager
def members(archive):
    with gzip.open(archive, "rb") as stream:
        with tarfile.open(fileobj=stream, mode="r|", bufsize=1024*1024) as tar:
            yield tar


def plan(archive, images):
    # Use the Docker manifest for image identity. The original OCI index and its
    # containerd/ref.name annotations must never reach the shared daemon.
    identities = {i["id"].removeprefix("sha256:"): i for i in images}
    present = set()
    manifest = None
    with members(archive) as tar:
        for member in tar:
            if member.name == "manifest.json":
                if manifest is not None or not member.isfile() or member.size > 1024*1024:
                    raise ValueError("Unexpected Docker manifest")
                manifest = json.load(tar.extractfile(member))
            elif member.isfile() and BLOB.fullmatch(member.name):
                if member.name in present:
                    raise ValueError("Duplicate image blob")
                present.add(member.name)
                blob = BLOB.fullmatch(member.name)[1]
                if blob in identities:
                    if member.size > 2 * 1024 * 1024:
                        raise ValueError("Unexpected locked image configuration size")
                    raw = tar.extractfile(member).read()
                    info = json.loads(raw)
                    if (hashlib.sha256(raw).hexdigest() != blob or
                            (info.get("os"), info.get("architecture")) != ("linux", "amd64")):
                        raise ValueError("Locked image config bytes or platform do not match")
    if not isinstance(manifest, list) or len(manifest) != len(images):
        raise ValueError("Bundle does not contain the four locked images")
    names, used, clean = {}, set(), []
    for record in manifest:
        config = record["Config"]
        match = BLOB.fullmatch(config)
        if not match or match[1] not in identities or config in used:
            raise ValueError("Unknown or repeated image configuration")
        used.add(config)
        image = identities[match[1]]
        names[config] = match[1] + ".json"
        layer_names = []
        for layer in record["Layers"]:
            layer_id = BLOB.fullmatch(layer)
            if not layer_id or layer_id[1] in identities:
                raise ValueError("Invalid image layer path")
            names[layer] = layer_id[1] + "/layer.tar"
            layer_names.append(names[layer])
        clean.append({"Config": names[config], "RepoTags": [image["alias"]], "Layers": layer_names})
    if not set(names).issubset(present):
        raise ValueError("Image archive is incomplete")
    return clean, names


def import_bundle(archive, images):
    manifest, names = plan(archive, images)
    tag_targets(images)
    # Emit a standard Docker-save archive with freshly constructed metadata.
    # Only locked image configs and their layers pass through; no original
    # index.json, repositories, OCI layout, or unreferenced blobs are included.
    process = subprocess.Popen(["docker", "image", "load"], stdin=subprocess.PIPE)
    try:
        with process.stdin as sink, tarfile.open(fileobj=sink, mode="w|", bufsize=1024*1024, copybufsize=1024*1024) as out:
            payload = json.dumps(manifest, separators=(",", ":")).encode()
            metadata = tarfile.TarInfo("manifest.json")
            metadata.size = len(payload)
            out.addfile(metadata, io.BytesIO(payload))
            with members(archive) as src:
                for member in src:
                    name = names.get(member.name)
                    if name is None:
                        continue
                    item = tarfile.TarInfo(name)
                    item.size = member.size
                    out.addfile(item, src.extractfile(member))
    except BaseException:
        process.kill()
        process.wait()
        raise
    if process.wait():
        raise RuntimeError("Docker rejected the project-scoped image archive")
    ensure_aliases(images)
