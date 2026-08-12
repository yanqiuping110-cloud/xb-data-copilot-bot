#!/usr/bin/env python3
"""Non-interactive demo smoke: login → fixture ask → assert rows."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def _post(url: str, payload: dict, token: str | None = None) -> dict:
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {e.code} {url}: {detail}") from e


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--user", default="admin")
    parser.add_argument("--password", default="demo123456")
    parser.add_argument("--question", default="How many orders are there?")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    # health
    try:
        with urllib.request.urlopen(f"{base}/health", timeout=10) as resp:
            if resp.status != 200:
                raise SystemExit(f"health status {resp.status}")
    except Exception as exc:  # noqa: BLE001
        print(f"NEXT: make demo-up  (API not reachable: {exc})")
        raise SystemExit(2) from exc

    login = _post(
        f"{base}/api/v1/auth/login",
        {"username": args.user, "password": args.password},
    )
    token = login.get("accessToken") or login.get("access_token")
    if not token:
        raise SystemExit(f"login missing accessToken: {login}")

    ask = _post(
        f"{base}/api/v1/ask",
        {"question": args.question},
        token=token,
    )
    status = ask.get("status")
    rows = ask.get("rows")
    print(json.dumps({"status": status, "sql": ask.get("sql"), "rowCount": len(rows or []), "answer": ask.get("answer")}, ensure_ascii=False, indent=2))
    if status != "ok" or not rows:
        print("NEXT: check .demo/last-smoke.log and make demo-logs")
        raise SystemExit(1)
    print("SMOKE_OK")


if __name__ == "__main__":
    main()
