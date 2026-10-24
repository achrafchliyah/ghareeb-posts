#!/usr/bin/env python3
"""Post the next approved carousel in posts/ to Instagram. Run once a day by .github/workflows/post.yml.

  posts/<NNN>/01.jpg ... 08.jpg + caption.txt   approved episodes, pushed here by `run.py approve` on the PC
  posted.json                                   episodes already published (written by this script)

  python3 publish.py             publish the lowest-numbered approved episode that isn't posted yet
  python3 publish.py --dry-run   check token, image URLs and caption without posting

Needs IG_ACCESS_TOKEN (Instagram API with Instagram Login, scope instagram_business_content_publish)
and IG_USER_ID in the environment. Uses only the standard library.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://graph.instagram.com/v26.0"
ROOT = Path(__file__).resolve().parent
POSTS = ROOT / "posts"
LOG = ROOT / "posted.json"


class ApiError(RuntimeError):
    pass


def call(method: str, path: str, **params) -> dict:
    params["access_token"] = os.environ["IG_ACCESS_TOKEN"]
    data = urllib.parse.urlencode(params).encode()
    url = f"{API}/{path}"
    if method == "GET":
        req = urllib.request.Request(f"{url}?{data.decode()}")
    else:
        req = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            err = json.loads(body).get("error", {})
            body = f"{err.get('message')} (code {err.get('code')}, subcode {err.get('error_subcode')})"
        except ValueError:
            pass
        raise ApiError(f"{method} /{path} -> HTTP {e.code}: {body}") from None


def load_log() -> list[dict]:
    return json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else []


def save_log(log: list[dict]) -> None:
    LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def queue(log: list[dict]) -> list[Path]:
    done = {e["episode"] for e in log}
    dirs = [d for d in POSTS.iterdir() if d.is_dir() and d.name.isdigit()] if POSTS.exists() else []
    return sorted((d for d in dirs if int(d.name) not in done), key=lambda d: int(d.name))


def marker(episode: int) -> str:
    """Text every caption contains (see caption.txt), used to spot a post that went out but wasn't logged."""
    return f"الحلقة {episode} من"


def image_urls(d: Path) -> list[str]:
    repo = os.environ.get("GITHUB_REPOSITORY", "achrafchliyah/ghareeb-posts")
    ref = os.environ.get("GITHUB_SHA") or "main"   # a commit SHA avoids stale CDN copies of replaced images
    return [f"https://raw.githubusercontent.com/{repo}/{ref}/posts/{d.name}/{p.name}" for p in sorted(d.glob("*.jpg"))]


def wait_finished(container: str, timeout: int = 300) -> None:
    deadline = time.time() + timeout
    while True:
        status = call("GET", container, fields="status_code").get("status_code")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED") or time.time() > deadline:
            raise ApiError(f"container {container} ended as {status}")
        time.sleep(10)


def output(**values) -> None:
    """Expose values to later workflow steps."""
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            for k, v in values.items():
                f.write(f"{k}={v}\n")


def main() -> int:
    dry = "--dry-run" in sys.argv
    user = os.environ["IG_USER_ID"]
    me = call("GET", "me", fields="user_id,username")
    me = (me.get("data") or [me])[0]
    print(f"logged in as @{me.get('username')}")

    log = load_log()
    pending = queue(log)

    # A run that published but crashed before saving posted.json must not post the same episode twice.
    recent = call("GET", f"{user}/media", fields="caption,timestamp", limit=10).get("data", [])
    while pending and any(marker(int(pending[0].name)) in (m.get("caption") or "") for m in recent):
        d = pending.pop(0)
        hit = next(m for m in recent if marker(int(d.name)) in (m.get("caption") or ""))
        print(f"episode {int(d.name)} is already on Instagram ({hit['id']}); recording it")
        log.append({"episode": int(d.name), "media_id": hit["id"], "posted_at": hit.get("timestamp")})
        if not dry:
            save_log(log)

    if not pending:
        print("::warning::no approved episodes left to post; approve more with `python run.py approve` on the PC")
        output(remaining=0)
        return 0

    d = pending[0]
    urls = image_urls(d)
    caption = (d / "caption.txt").read_text(encoding="utf-8").strip()
    if not 2 <= len(urls) <= 20:
        raise SystemExit(f"posts/{d.name} has {len(urls)} images; a carousel needs 2-20")
    print(f"next: episode {int(d.name)} ({len(urls)} slides), {len(pending) - 1} more approved after it")

    if dry:
        for u in urls:
            with urllib.request.urlopen(urllib.request.Request(u, method="HEAD"), timeout=30) as r:
                print(f"  ok {r.status} {r.headers.get('Content-Type')}  {u}")
        print("caption:\n" + caption)
        output(remaining=len(pending), episode=int(d.name))
        return 0

    children = [call("POST", f"{user}/media", image_url=u, is_carousel_item="true")["id"] for u in urls]
    carousel = call("POST", f"{user}/media", media_type="CAROUSEL", children=",".join(children), caption=caption)["id"]
    wait_finished(carousel)
    media = call("POST", f"{user}/media_publish", creation_id=carousel)["id"]
    log.append({"episode": int(d.name), "media_id": media, "posted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    save_log(log)
    print(f"posted episode {int(d.name)} -> media {media}")
    output(remaining=len(pending) - 1, episode=int(d.name))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ApiError as e:
        print(f"::error::{e}")
        sys.exit(1)
