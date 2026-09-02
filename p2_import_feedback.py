#!/usr/bin/env python3
"""E3 反馈/跟踪导入器：把 Review UI 采集的结果并入 p2_state.json。

静态站点无后端，浏览器无法直接写 p2_state.json；本模块是**诚实的人工桥梁**：
Review UI 导出 JSON（或提交 GitHub Issue 携带 JSON 块）→ 本导入器严格校验后合并。

schema 与 `p2_intelligence.record_feedback` / `register_monitor` 完全一致：
- feedback: event_id / label / note / importance(1-5) / confidence(1-5) / outcome / user_id / created_at
- monitoring: watchlist_id / event_id / status(active|resolved|snoozed) / updated_at

纪律（与 S1–S6、P2 一致）：
- fail-closed：任何非法行（label/status/评分越界、未知 watchlist、缺 event_id）一律拒绝并报告，
  **绝不静默修正、绝不制造或补全用户偏好**。
- observation/结论分离：导入器只落事实，不做偏好推断；偏好结论由 Personal Memory 在样本足够后产出。
- 去重：feedback 按 (event_id, label) 保留最新；monitoring 按 (watchlist_id, event_id) 覆盖（与 register_monitor 一致）。
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
STATE_PATH = Path(__file__).resolve().parent / "p2_state.json"

VERSION = "import-v1.0"

# 与 p2_intelligence.record_feedback 的 allowed 保持一致
ALLOWED_LABELS = {"useful", "important", "noise", "irrelevant", "incorrect", "acted_on"}
# 与 p2_intelligence.register_monitor 的 status 保持一致
ALLOWED_STATUS = {"active", "resolved", "snoozed"}
RATING_MIN, RATING_MAX = 1, 5

# GitHub Issue 正文中 ```json ... ``` 代码块（沿用项目既有「Issue 携带机器可解析负载」约定）
_JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_text(value: Any) -> str:
    return "" if value is None else str(value)


def _parse_rating(value: Any) -> int | None:
    """评分必须严格落在 1..5；接受 int 或纯数字字符串，其余返回 None（由调用方判定）。"""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    try:
        iv = int(value)
    except (TypeError, ValueError):
        return None
    return iv if RATING_MIN <= iv <= RATING_MAX else None


def _valid_timestamp(value: Any) -> str | None:
    """仅接受可解析的 ISO 时间戳；缺失则回落到导入时刻（诚实：不编造用户操作时间）。"""
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        datetime.fromisoformat(text)
    except ValueError:
        return None
    return str(value)


def validate_feedback_row(row: Any, watchlist_ids: set[str] | None = None) -> list[str]:
    """返回错误列表；空列表代表合法。"""
    if not isinstance(row, dict):
        return ["反馈行不是对象"]
    errors: list[str] = []
    if not _as_text(row.get("event_id")).strip():
        errors.append("缺少 event_id")
    label = row.get("label")
    if label not in ALLOWED_LABELS:
        errors.append(f"label 非法或不明：{label!r}（允许 {sorted(ALLOWED_LABELS)}）")
    for field in ("importance", "confidence"):
        if field in row and row[field] not in (None, ""):
            if _parse_rating(row[field]) is None:
                errors.append(f"{field} 必须为空或 {RATING_MIN}..{RATING_MAX} 的整数：{row[field]!r}")
    if row.get("created_at") and _valid_timestamp(row.get("created_at")) is None:
        errors.append(f"created_at 不是合法 ISO 时间：{row.get('created_at')!r}")
    return errors


def validate_monitor_row(row: Any, watchlist_ids: set[str] | None = None) -> list[str]:
    if not isinstance(row, dict):
        return ["跟进行不是对象"]
    errors: list[str] = []
    if not _as_text(row.get("event_id")).strip():
        errors.append("缺少 event_id")
    wid = _as_text(row.get("watchlist_id")).strip()
    if not wid:
        errors.append("缺少 watchlist_id")
    elif watchlist_ids is not None and wid not in watchlist_ids:
        errors.append(f"watchlist_id 未知：{wid!r}（已知 {sorted(watchlist_ids)}）")
    status = row.get("status")
    if status not in ALLOWED_STATUS:
        errors.append(f"status 非法或不明：{status!r}（允许 {sorted(ALLOWED_STATUS)}）")
    if row.get("updated_at") and _valid_timestamp(row.get("updated_at")) is None:
        errors.append(f"updated_at 不是合法 ISO 时间：{row.get('updated_at')!r}")
    return errors


def normalize_feedback(rows: list[Any], watchlist_ids: set[str] | None = None) -> tuple[list[dict], list[dict]]:
    """拆分为 (接受, 拒绝)；拒绝项附带 reasons。去重按 (event_id, label) 保留最新 created_at。"""
    accepted: dict[tuple[str, str], dict] = {}
    rejected: list[dict] = []
    for row in rows or []:
        errors = validate_feedback_row(row, watchlist_ids)
        if errors:
            rejected.append({"row": row, "reasons": errors})
            continue
        created = _valid_timestamp(row.get("created_at")) or now()
        item = {
            "event_id": _as_text(row.get("event_id")).strip(),
            "label": row.get("label"),
            "note": _as_text(row.get("note") or ""),
            "importance": _parse_rating(row.get("importance")),
            "confidence": _parse_rating(row.get("confidence")),
            "outcome": (_as_text(row.get("outcome")).strip() or None) if row.get("outcome") else None,
            "user_id": (_as_text(row.get("user_id")).strip() or None) if row.get("user_id") else None,
            "created_at": created,
        }
        key = (item["event_id"], item["label"])
        prior = accepted.get(key)
        if prior is None or item["created_at"] >= prior["created_at"]:
            accepted[key] = item
    return list(accepted.values()), rejected


def normalize_monitoring(rows: list[Any], watchlist_ids: set[str] | None = None) -> tuple[list[dict], list[dict]]:
    """拆分为 (接受, 拒绝)；去重按 (watchlist_id, event_id) 覆盖（与 register_monitor 语义一致）。"""
    accepted: dict[tuple[str, str], dict] = {}
    rejected: list[dict] = []
    for row in rows or []:
        errors = validate_monitor_row(row, watchlist_ids)
        if errors:
            rejected.append({"row": row, "reasons": errors})
            continue
        item = {
            "watchlist_id": _as_text(row.get("watchlist_id")).strip(),
            "event_id": _as_text(row.get("event_id")).strip(),
            "status": row.get("status"),
            "updated_at": _valid_timestamp(row.get("updated_at")) or now(),
        }
        accepted[(item["watchlist_id"], item["event_id"])] = item
    return list(accepted.values()), rejected


def merge_state(state: dict, feedback: list[dict], monitoring: list[dict]) -> dict:
    """把规范化后的记录并入 state：去重后覆盖，保留其余字段不变。"""
    merged = json.loads(json.dumps(state))  # 深度拷贝，避免就地污染
    merged.setdefault("feedback", [])
    merged.setdefault("monitoring", [])

    by_fb = {(f.get("event_id"), f.get("label")): f for f in feedback}
    merged["feedback"] = [f for f in merged["feedback"]
                          if (f.get("event_id"), f.get("label")) not in by_fb]
    merged["feedback"].extend(feedback)

    by_mon = {(m.get("watchlist_id"), m.get("event_id")): m for m in monitoring}
    merged["monitoring"] = [m for m in merged["monitoring"]
                            if (m.get("watchlist_id"), m.get("event_id")) not in by_mon]
    merged["monitoring"].extend(monitoring)
    return merged


def import_payload(payload: dict, state: dict, watchlist_ids: set[str] | None = None) -> dict[str, Any]:
    """校验并合并一份导出负载，返回导入报告（不写文件）。"""
    feedback, fb_rejected = normalize_feedback(payload.get("feedback") or [], watchlist_ids)
    monitoring, mon_rejected = normalize_monitoring(payload.get("monitoring") or [], watchlist_ids)
    merged = merge_state(state, feedback, monitoring)
    return {
        "version": VERSION,
        "imported_feedback": len(feedback),
        "imported_monitoring": len(monitoring),
        "rejected_feedback": len(fb_rejected),
        "rejected_monitoring": len(mon_rejected),
        "rejections": fb_rejected + mon_rejected,
        "state_feedback_total": len(merged.get("feedback", [])),
        "state_monitoring_total": len(merged.get("monitoring", [])),
        "state": merged,
    }


def load_payload(path: Path) -> dict:
    """支持：纯 JSON 文件 / GitHub Issue 正文（提取 ```json 块）。"""
    text = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    match = _JSON_BLOCK.search(text)
    if match:
        try:
            data = json.loads(match.group(1))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    raise ValueError(f"无法从 {path} 解析出 feedback/monitoring JSON 负载")


def run(import_path: Path, state_path: Path = STATE_PATH, persist: bool = True) -> dict[str, Any]:
    payload = load_payload(Path(import_path))
    state = json.loads(Path(state_path).read_text(encoding="utf-8")) if Path(state_path).exists() else {
        "version": "p2-v1.0", "watchlists": [], "feedback": [], "monitoring": [],
    }
    watchlist_ids = {w.get("id") for w in (state.get("watchlists") or []) if w.get("id")}
    report = import_payload(payload, state, watchlist_ids)
    if persist:
        Path(state_path).write_text(json.dumps(report["state"], ensure_ascii=False, indent=2) + "\n",
                                    encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="导入 Review UI 采集的反馈 / 跟踪书签到 p2_state.json")
    parser.add_argument("path", help="导出 JSON 文件，或含 ```json 块的 GitHub Issue 正文")
    parser.add_argument("--state", default=str(STATE_PATH), help="目标 p2_state.json 路径")
    parser.add_argument("--no-persist", action="store_true", help="只校验不写文件")
    args = parser.parse_args()
    report = run(Path(args.path), Path(args.state), persist=not args.no_persist)
    print(json.dumps({
        "imported_feedback": report["imported_feedback"],
        "imported_monitoring": report["imported_monitoring"],
        "rejected_feedback": report["rejected_feedback"],
        "rejected_monitoring": report["rejected_monitoring"],
        "state_feedback_total": report["state_feedback_total"],
        "state_monitoring_total": report["state_monitoring_total"],
        "rejections": report["rejections"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
