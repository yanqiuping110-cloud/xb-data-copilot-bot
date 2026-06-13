"""
问数评测回放脚本（第 6 周：Memory 多轮子集）。

用法（backend/ 目录）:
  $env:APP_ENV = "development"
  python scripts/replay_eval.py --subset memory --token "<JWT>"
  python scripts/replay_eval.py --subset memory --base-url http://127.0.0.1:8000

依赖：API 已启动、copilot 库已迁移、业务库可读。
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent
CASE_FILES = {
    "memory": REPO_ROOT / "docs" / "eval" / "memory_multiturn.json",
    "agent": REPO_ROOT / "docs" / "eval" / "agent_complex_report.json",
}


def load_cases(subset: str) -> list[dict]:
    """加载评测用例 JSON。"""
    case_file = CASE_FILES.get(subset)
    if case_file is None:
        raise SystemExit(f"未知子集: {subset}，支持: {', '.join(CASE_FILES)}")
    if not case_file.is_file():
        raise SystemExit(f"用例文件不存在: {case_file}")
    data = json.loads(case_file.read_text(encoding="utf-8"))
    return data.get("cases", [])


def _check_expect(result: dict, expect: dict) -> list[str]:
    """校验单轮期望，返回错误列表。"""
    errors: list[str] = []
    status = result.get("status")
    if "status" in expect and status != expect["status"]:
        errors.append(f"status 期望 {expect['status']} 实际 {status}")
    if "status_in" in expect and status not in expect["status_in"]:
        errors.append(f"status 期望 ∈ {expect['status_in']} 实际 {status}")
    if expect.get("no_server_error") and status is None:
        errors.append("响应无 status（可能 5xx）")
    dl = result.get("degradeLevel", result.get("degrade_level"))
    if "degrade_level_lte" in expect and dl is not None:
        if int(dl) > int(expect["degrade_level_lte"]):
            errors.append(f"degrade_level {dl} > {expect['degrade_level_lte']}")
    return errors


def run_case(client: httpx.Client, case: dict) -> dict:
    """执行单个多轮用例。"""
    case_id = case.get("id", "?")
    session_id = f"eval-{uuid.uuid4().hex[:12]}"
    turn_results: list[dict] = []
    errors: list[str] = []

    prefs = case.get("preferences")
    if prefs:
        client.put("/api/v1/memory/preferences", json={"preferences": prefs})

    for i, turn in enumerate(case.get("turns", []), start=1):
        if case.get("new_session_on_turn") == i:
            r = client.post("/api/v1/sessions")
            r.raise_for_status()
            session_id = r.json().get("sessionId") or session_id

        resp = client.post(
            "/api/v1/ask",
            json={"question": turn["question"], "sessionId": session_id},
            timeout=180.0,
        )
        if resp.status_code >= 500:
            errors.append(f"轮次 {i}: HTTP {resp.status_code}")
            turn_results.append({"turn": i, "http_status": resp.status_code})
            continue
        body = resp.json()
        turn_errors = _check_expect(body, turn.get("expect", {}))
        if turn_errors:
            errors.extend([f"轮次 {i}: {e}" for e in turn_errors])
        turn_results.append(
            {
                "turn": i,
                "question": turn["question"],
                "status": body.get("status"),
                "degrade_level": body.get("degradeLevel"),
                "trace_id": body.get("traceId"),
            }
        )

    return {"id": case_id, "passed": len(errors) == 0, "errors": errors, "turns": turn_results}


def main() -> int:
    parser = argparse.ArgumentParser(description="问数评测回放")
    parser.add_argument("--subset", default="memory", help="评测子集（memory / agent）")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token", required=True, help="Bearer JWT")
    args = parser.parse_args()

    cases = load_cases(args.subset)
    headers = {"Authorization": f"Bearer {args.token}"}
    passed = 0
    reports: list[dict] = []

    with httpx.Client(base_url=args.base_url.rstrip("/"), headers=headers) as client:
        for case in cases:
            report = run_case(client, case)
            reports.append(report)
            if report["passed"]:
                passed += 1
                print(f"[PASS] {report['id']}")
            else:
                print(f"[FAIL] {report['id']}: {'; '.join(report['errors'])}")

    total = len(cases)
    print(f"\n合计: {passed}/{total} 通过")
    out = ROOT / "replay_eval_report.json"
    out.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告已写入 {out}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
