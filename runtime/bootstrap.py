"""Provision only this Compose project's original OpenAgents workspace, via its native API."""
import crypt
import fcntl
import html
import json
import os
import secrets
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from sqlalchemy import create_engine, text

STATE = Path("/state")
ENTRY = Path("/entry")
AGENT = "review-assistant"
THREAD = "本地对话测评"
MODEL = "deepseek-flash"


def secret(name):
    value = (Path("/run/secrets") / name).read_text().strip()
    if not value:
        raise RuntimeError(f"Empty secret file {name}")
    return value


def write_atomic(path, value, group=None):
    with NamedTemporaryFile(mode="w", dir=path.parent, encoding="utf-8", delete=False) as f:
        f.write(value)
        f.flush()
        os.fsync(f.fileno())
        if group is not None:
            os.fchown(f.fileno(), 0, group)
            os.fchmod(f.fileno(), 0o640)
        tmp = f.name
    os.replace(tmp, path)


def api(method, path, data=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Workspace-Token"] = token
    request = Request("http://backend:8000/v1" + path, method=method, headers=headers,
                      data=json.dumps(data).encode() if data is not None else None)
    try:
        with urlopen(request, timeout=40) as response:
            obj = json.load(response)
    except HTTPError as e:
        raise RuntimeError(f"OpenAgents {method} {path.split('?')[0]} returned HTTP {e.code}") from None
    if obj.get("code") not in (None, 0, "0"):
        raise RuntimeError(f"OpenAgents {method} {path.split('?')[0]} returned code {obj['code']}")
    return obj.get("data", obj)


def main():
    # An independent random owner marker allows recovery after an interrupted create,
    # without selecting or revealing any other workspace's credentials.
    marker = STATE / "workspace-owner"
    if not marker.exists():
        write_atomic(marker, f"bootstrap-{secrets.token_hex(12)}@evaluation.invalid")
    owner = marker.read_text()
    password = secret("postgres-password")
    engine = create_engine(f"postgresql://openagents:{password}@db:5432/openagents")
    with engine.connect() as db:
        row = db.execute(text("SELECT id,slug,password_hash FROM workspaces WHERE creator_email=:owner"),
                         {"owner": owner}).mappings().one_or_none()
    if row is None:
        net = api("POST", "/workspaces", {"name": "OpenAgents 评测", "creator_email": owner})
        network, slug, token = net["workspaceId"], net["slug"], net["token"]
    else:
        network, slug, token = str(row["id"]), row["slug"], row["password_hash"]
    agents = api("GET", "/cloud-agents?" + urlencode({"network": network}), token=token)["cloud_agents"]
    config = {"network": network, "model": MODEL, "api_key": secret("deepseek-key"),
              "base_url": "https://api.deepseek.com/v1", "max_tokens": 0,
              "system_prompt": "你是评测工作区的协作助手，用中文简洁回答。"}
    if any(a.get("agentName", a.get("agent_name")) == AGENT for a in agents):
        api("PATCH", f"/cloud-agents/{AGENT}", config, token)
    else:
        api("POST", "/cloud-agents", {**config, "provider": "deepseek", "agent_name": AGENT}, token)
    with engine.connect() as db:
        channel = db.execute(text("SELECT name FROM channels WHERE workspace_id=:id AND title=:title "
                                  "ORDER BY created_at, id LIMIT 1"),
                             {"id": network, "title": THREAD}).scalar()
    if not channel:
        result = api("POST", "/events", {"network": network, "type": "network.channel.create",
                     "source": "human:" + owner, "target": "core", "visibility": "channel",
                     "payload": {"title": THREAD, "title_manually_set": True, "master": AGENT,
                                 "participants": [AGENT], "visibility": "public"}}, token)
        channel = result["metadata"]["channel_name"]
    url = f"/{quote(slug, safe='')}/threads/{quote(channel, safe='')}?{urlencode({'token':token})}"
    digest = crypt.crypt(secret("login-password"), crypt.mksalt(crypt.METHOD_SHA512))
    if not digest.startswith("$6$"):
        raise RuntimeError("SHA-512 password hashing unavailable")
    write_atomic(ENTRY / "passwords", "admin:" + digest + "\n", 101)
    page = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="referrer" content="no-referrer"><title>OpenAgents · 评测工作区</title>'
            '<style>html,body,iframe{height:100%;width:100%;border:0;margin:0;display:block}</style>'
            '<iframe title="OpenAgents 工作区" referrerpolicy="no-referrer" src="' +
            html.escape(url, quote=True) + '"></iframe></html>')
    write_atomic(ENTRY / "index.html", page, 101)
    print("Workspace, evaluation thread and DeepSeek agent ready.", flush=True)


if __name__ == "__main__":
    with (STATE / "bootstrap.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        main()
