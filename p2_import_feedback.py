#!/usr/bin/env python3
"""E3 反馈/跟踪导入器：把 Review UI 采集的结果并入 p2_state.json。

静态站点无后端，浏览器无法直接写 p2_state.json；本模块是**诚实的人工桥梁**：
Review UI 导出 JSON（或提交 GitHub Issue 携带 JSON 块）→ 本导入器严格校验后合并。

schema 与 `p2_intelligence.record_feedback` / `register_monitor` 完全一致：
- feedback: event_id / canonical_event_id / label / note / importance(1-5) / confidence(1-5) / outcome / user_id / created_at
- monitoring: watchlist_id / event_id / canonical_event_id / status(active|resolved|snoozed) / updated_at

§9.5 单一事实源：导入行携带的原始 `event_id`（evt_...）在写入 p2_state 时**归一化为
`canonical_event_id`**（cev_...，经 S1 Registry 的 by_event_id 解析）。下游（S5 funnel 的
feedback_status_by_ceid、Second Brain）一律以 canonical_event_id 为锚点。无法解析的 event_id
（不在 S1 Registry）按 fail-closed 拒绝，不静默落到原始 id。

纪律（与 S1–S6、P2 一致）：
- fail-closed：任何非法行（label/status/评分越界、未知 watchlist、缺 event_id、event_id 无法解析为
  canonical）一律拒绝并报告，**绝不静默修正、绝不制造或补全用户偏好**。
- observation/结论分离：导入器只落事实，不做偏好推断；偏好结论由 Personal Memory 在样本足够后产出。
- 去重：feedback 按 (canonical_event_id, label) 保留最新；monitoring 按 (watchlist_id, canonical_event_id)
  覆盖（与 register_monitor 语义一致，且以 canonical 为锚点）。
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

VERSION = "import-v1.1"

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


def load_by_event_id(ce_path: Path | None = None) -> dict[str, str] | None:
    """读取 S1 Canonical Event Registry 的 event_id → canonical_event_id 映射。

    缺失时返回 None（调用方退化为 fail-soft：保留原始 event_id 作为 ceid，
    避免图谱/Registry 缺文件时导入器整体不可用）。
    """
    p = ce_path or (ROOT / "canonical_events.json")
    if not p.exists():
        return None
    data = json.loads(Path(p).read_text(encoding="utf-8"))
    return data.get("by_event_id")


def _resolve_ceid(event_id: Any, by_event_id: dict[str, str] | None) -> str | None:
    """§9.5 FK：原始 event_id → canonical_event_id。

    - Registry 缺失（by_event_id=None）：fail-soft，返回原始 id 作为 ceid。
    - Registry 存在但 event_id 不在映射内：返回 None（→ 调用方 fail-closed 拒绝）。
    """
    eid = _as_text(event_id).strip()
    if not eid:
        return None
    if by_event_id is None:
        return eid
    return by_event_id.get(eid)


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


def normalize_feedback(
    rows: list[Any],
    watchlist_ids: set[str] | None = None,
    by_event_id: dict[str, str] | None = None,
) -> tuple[list[dict], list[dict]]:
    """拆分为 (接受, 拒绝)；拒绝项附带 reasons。去重按 (canonical_event_id, label) 保留最新 created_at。"""
    accepted: dict[tuple[str, str], dict] = {}
    rejected: list[dict] = []
    for row in rows or []:
        errors = validate_feedback_row(row, watchlist_ids)
        if errors:
            rejected.append({"row": row, "reasons": errors})
            continue
        # §9.5 FK 归一化：event_id → canonical_event_id（fail-closed）
        ceid = _resolve_ceid(row.get("event_id"), by_event_id)
        if ceid is None:
            rejected.append({"row": row, "reasons": ["event_id 无法解析为 canonical_event_id（不在 S1 Registry 的 by_event_id）"]})
            continue
        created = _valid_timestamp(row.get("created_at")) or now()
        item = {
            "event_id": _as_text(row.get("event_id")).strip(),
            "canonical_event_id": ceid,
            "label": row.get("label"),
            "note": _as_text(row.get("note") or ""),
            "importance": _parse_rating(row.get("importance")),
            "confidence": _parse_rating(row.get("confidence")),
            "outcome": (_as_text(row.get("outcome")).strip() or None) if row.get("outcome") else None,
            "user_id": (_as_text(row.get("user_id")).strip() or None) if row.get("user_id") else None,
            "created_at": created,
        }
        key = (item["canonical_event_id"], item["label"])
        prior = accepted.get(key)
        if prior is None or item["created_at"] >= prior["created_at"]:
            accepted[key] = item
    return list(accepted.values()), rejected


def normalize_monitoring(
    rows: list[Any],
    watchlist_ids: set[str] | None = None,
    by_event_id: dict[str, str] | None = None,
) -> tuple[list[dict], list[dict]]:
    """拆分为 (接受, 拒绝)；去重按 (watchlist_id, canonical_event_id) 覆盖（与 register_monitor 语义一致）。"""
    accepted: dict[tuple[str, str], dict] = {}
    rejected: list[dict] = []
    for row in rows or []:
        errors = validate_monitor_row(row, watchlist_ids)
        if errors:
            rejected.append({"row": row, "reasons": errors})
            continue
        # §9.5 FK 归一化：event_id → canonical_event_id（fail-closed）
        ceid = _resolve_ceid(row.get("event_id"), by_event_id)
        if ceid is None:
            rejected.append({"row": row, "reasons": ["event_id 无法解析为 canonical_event_id（不在 S1 Registry 的 by_event_id）"]})
            continue
        item = {
            "watchlist_id": _as_text(row.get("watchlist_id")).strip(),
            "event_id": _as_text(row.get("event_id")).strip(),
            "canonical_event_id": ceid,
            "status": row.get("status"),
            "updated_at": _valid_timestamp(row.get("updated_at")) or now(),
        }
        accepted[(item["watchlist_id"], item["canonical_event_id"])] = item
    return list(accepted.values()), rejected


def merge_state(state: dict, feedback: list[dict], monitoring: list[dict]) -> dict:
    """把规范化后的记录并入 state：去重后覆盖，保留其余字段不变。

    去重锚点统一为 canonical_event_id（§9.5 单一事实源）；旧条目若缺 canonical_event_id
    则回退到 event_id 比对，兼容迁移期。
    """
    merged = json.loads(json.dumps(state))  # 深度拷贝，避免就地污染
    merged.setdefault("feedback", [])
    merged.setdefault("monitoring", [])

    def _fb_key(f: dict) -> tuple:
        return (f.get("canonical_event_id") or f.get("event_id"), f.get("label"))

    def _mon_key(m: dict) -> tuple:
        return (m.get("watchlist_id"), m.get("canonical_event_id") or m.get("event_id"))

    by_fb = {_fb_key(f): f for f in feedback}
    merged["feedback"] = [f for f in merged["feedback"] if _fb_key(f) not in by_fb]
    merged["feedback"].extend(feedback)

    by_mon = {_mon_key(m): m for m in monitoring}
    merged["monitoring"] = [m for m in merged["monitoring"] if _mon_key(m) not in by_mon]
    merged["monitoring"].extend(monitoring)
    return merged


def validate_state(state: dict) -> None:
    """§9.5 schema guard：fail-closed 校验 state 中每条 feedback/monitoring 都锚定 canonical_event_id。"""
    for f in state.get("feedback", []):
        assert f.get("canonical_event_id"), f"feedback 缺 canonical_event_id: {f}"
    for m in state.get("monitoring", []):
        assert m.get("canonical_event_id"), f"monitoring 缺 canonical_event_id: {m}"


def import_payload(
    payload: dict,
    state: dict,
    watchlist_ids: set[str] | None = None,
    by_event_id: dict[str, str] | None = None,
) -> dict[str, Any]:
    """校验并合并一份导出负载，返回导入报告（不写文件）。"""
    feedback, fb_rejected = normalize_feedback(payload.get("feedback") or [], watchlist_ids, by_event_id)
    monitoring, mon_rejected = normalize_monitoring(payload.get("monitoring") or [], watchlist_ids, by_event_id)
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


def run(
    import_path: Path,
    state_path: Path = STATE_PATH,
    ce_path: Path | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    payload = load_payload(Path(import_path))
    state = json.loads(Path(state_path).read_text(encoding="utf-8")) if Path(state_path).exists() else {
        "version": "p2-v1.0", "watchlists": [], "feedback": [], "monitoring": [],
    }
    watchlist_ids = {w.get("id") for w in (state.get("watchlists") or []) if w.get("id")}
    by_event_id = load_by_event_id(ce_path)
    report = import_payload(payload, state, watchlist_ids, by_event_id)
    if persist:
        validate_state(report["state"])  # fail-closed：写盘前强制 schema 守卫
        Path(state_path).write_text(json.dumps(report["state"], ensure_ascii=False, indent=2) + "\n",
                                    encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="导入 Review UI 采集的反馈 / 跟踪书签到 p2_state.json")
    parser.add_argument("path", help="导出 JSON 文件，或含 ```json 块的 GitHub Issue 正文")
    parser.add_argument("--state", default=str(STATE_PATH), help="目标 p2_state.json 路径")
    parser.add_argument("--ce", default=str(ROOT / "canonical_events.json"),
                        help="S1 Canonical Event Registry 路径（提供 event_id→canonical_event_id 映射）")
    parser.add_argument("--no-persist", action="store_true", help="只校验不写文件")
    args = parser.parse_args()
    report = run(Path(args.path), Path(args.state), ce_path=Path(args.ce), persist=not args.no_persist)
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
