"""Supervised iPhone tap and reading-condition trials. Recompute evidence using read-only SQLite."""

import argparse
import fcntl
import json
import math
import os
import sqlite3
import time
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = "iphone-tap-eyecare-v3"
TAP_SIDES = ("left", "right", "left", "right", "left")
SIDE_TEXT = {"left": "左", "right": "右"}
TAPS = ("double_tap", "single_tap", "silent")
EYE = ("near_far", "dim_restore")
ALL = (*TAPS, *EYE)
GROUPS = {"capture": TAPS, "eyecare": EYE}
EYE_SECONDS = 12
GRACE = 3
OBSERVE = 6
SCOPES = {"verify": ALL, "verify-capture": TAPS, "verify-eye": EYE}
PHASES = {
    "double_tap": (
        "双击取景 · 五次",
        "在 iPhone 16 Pro Max 勾选现场拍摄，打开后摄，确认家长端静音已关闭。看到绿色指令后，在取景区指定一侧快速点两下，顺序为左、右、左、右、左。每个计时段只做一次。",
    ),
    "single_tap": (
        "单击对照",
        "在同一 iPhone 保持后摄取景。看到「现在单击」后，在左镜框触控区只点一下，保持取景到计时结束。",
    ),
    "silent": (
        "入校静音",
        "现在在同场家长端开启入校静音，等 iPhone 显示静音。若已开启，请先关再开，以记录此次切换。完成后回这里点准备按钮。",
    ),
    "near_far": (
        "护眼提醒 · 靠近再挪远",
        "请使用局域网 HTTPS 真机入口并打开后摄、关闭静音。在 Mac 将家长护眼页与本准备页分为两个可见窗口。请先在普通距离对准纸面标记，确认已有正常读数、没有进行中的距离提醒。看到绿色指令才开始靠近。",
    ),
    "dim_restore": (
        "护眼提醒 · 遮暗再恢复",
        "保持同场 iPhone 局域网后摄取景、家长护眼页可见。先照亮页面并确认没有进行中的明暗提醒。看到绿色指令才开始遮暗。",
    ),
}


def iso(stamp):
    return datetime.fromtimestamp(stamp, UTC).isoformat()


def captures(db, sid, start, end):
    rows = db.execute(
        """SELECT id,created,source,phone_confirmed,user_agent,camera_model,tap_side FROM captures
        WHERE session_id=? AND created BETWEEN ? AND ? ORDER BY created,id""",
        (sid, start, end),
    )
    return [
        {
            "id": cid,
            "at": iso(t),
            "source": source,
            "operator_confirmed": confirmed == 1,
            "iphone_user_agent": "iphone" in ua.lower(),
            "camera_model": model,
            "tap_side": side,
        }
        for cid, t, source, confirmed, ua, model, side in rows
    ]


def readings(db, sid, metric, start, end):
    rows = db.execute(
        """SELECT observed,body FROM telemetry WHERE session_id=? AND metric=?
        AND input_mode='live' AND observed BETWEEN ? AND ? ORDER BY observed""",
        (sid, metric, start, end),
    )
    return [{**json.loads(body), "at": t} for t, body in rows]


def valid_reading(row, method, kind, unit):
    v = row.get("value")
    return (
        row.get("quality") == "ok"
        and row.get("method") == method
        and row.get("value_kind") == kind
        and row.get("unit") == unit
        and type(v) in (int, float)
        and math.isfinite(v)
    )


def score_double(db, sid, windows):
    trials = []
    for i, (start, end) in enumerate(windows):
        expected_side = TAP_SIDES[i] if i < len(TAP_SIDES) else None
        shots = captures(db, sid, start, end + GRACE)
        hit = len(shots) == 1 and all(
            (
                shots[0]["source"] == "double_tap",
                shots[0]["tap_side"] == expected_side,
                shots[0]["iphone_user_agent"],
                shots[0]["operator_confirmed"],
                shots[0]["camera_model"] in (None, "", "iPhone 16 Pro Max"),
            )
        )
        trials.append(
            {
                "window": [start, end],
                "receipt_deadline": end + GRACE,
                "expected_side": expected_side,
                "captures": shots,
                "pass": hit and end - start >= OBSERVE,
            }
        )
    ordered = all(b["window"][0] > a["receipt_deadline"] for a, b in pairwise(trials))
    hits = sum(t["pass"] for t in trials)
    return {
        "trials": trials,
        "single_capture_hits": hits,
        "pass": ordered and len(trials) == hits == 5,
    }


def score_single(db, sid, start, end):
    shots = captures(db, sid, start, end + GRACE)
    samples = [
        r
        for r in readings(db, sid, "brightness", start, end)
        if valid_reading(r, "center-luma-rec709-v1", "measured", "level")
        and 0 <= r["value"] <= 255
    ]
    times = [start, *(r["at"] for r in samples), end]
    gap = max(b - a for a, b in pairwise(times))
    return {
        "window": [start, end],
        "receipt_deadline": end + GRACE,
        "rear_camera_samples": samples,
        "max_sampling_gap_s": gap,
        "captures": shots,
        "pass": end - start >= OBSERVE and len(samples) >= 3 and gap <= 3 and not shots,
    }


def score_silent(db, sid, prepared_at, start, end):
    # Only the parent API can create session.privacy. Reconstruct state at the time
    # of the trial so a restored camera later on cannot invalidate good evidence.
    rows = db.execute(
        """SELECT seq,ts,payload FROM events WHERE session_id=? AND kind='session.privacy'
        AND ts<=? ORDER BY ts,seq""",
        (sid, end + GRACE),
    )
    enabled = False
    transition = None
    changes = []
    for seq, ts, payload in rows:
        state = json.loads(payload).get("silent")
        if type(state) is not bool:
            raise ValueError("Invalid session.privacy state")
        event = {"seq": seq, "at": ts, "silent": state}
        if ts <= start:
            if state and not enabled:
                transition = event
            if not state:
                transition = None
            enabled = state
        else:
            changes.append(event)
    fresh = enabled and transition is not None and transition["at"] >= prepared_at
    continuously_silent = fresh and all(change["silent"] for change in changes)
    shots = captures(db, sid, transition["at"] if fresh else start, end + GRACE)
    return {
        "prepared_at": prepared_at,
        "window": [start, end],
        "receipt_deadline": end + GRACE,
        "parent_enabled_event": transition,
        "privacy_events_during_window": changes,
        "continuously_silent": continuously_silent,
        "captures": shots,
        "pass": prepared_at <= start
        and end - start >= OBSERVE
        and continuously_silent
        and not shots,
    }


# Thresholds match the server's alert hysteresis. The distance values are camera proxies.
EYE_SPECS = {
    "near_far": ("distance_cm", "qr-size-proxy-v2", "estimated", "cm", 33, 35),
    "dim_restore": ("brightness", "center-luma-rec709-v1", "measured", "level", 65, 75),
}


def score_eye(db, sid, phase, trigger, recovery):
    metric, method, kind, unit, low, high = EYE_SPECS[phase]
    start, trigger_end = trigger
    recovery_start, end = recovery
    deadline = end + GRACE
    observations = readings(db, sid, metric, start, end)
    valid = [
        r
        for r in observations
        if valid_reading(r, method, kind, unit)
        and r["value"] >= 0
        and (metric != "distance_cm" or r["value"] > 0)
    ]
    unsafe = [r for r in valid if start <= r["at"] <= trigger_end and r["value"] < low]
    restored = [
        r for r in valid if recovery_start <= r["at"] <= end and r["value"] >= high
    ]
    rows = db.execute(
        """SELECT a.id,a.started,a.raised,a.ended,a.seen,a.reason,s.transport,s.iphone
        FROM alerts a LEFT JOIN alert_sources s ON s.alert_id=a.id
        WHERE a.session_id=? AND a.metric=? AND a.input_mode='live'
        AND a.raised BETWEEN ? AND ? ORDER BY a.raised""",
        (sid, metric, start, trigger_end),
    )
    events = [
        (seq, ts, event, json.loads(body))
        for seq, ts, event, body in db.execute(
            """SELECT seq,ts,kind,payload FROM events WHERE session_id=?
        AND kind IN ('alert.raised','alert.cleared') AND ts BETWEEN ? AND ? ORDER BY seq""",
            (sid, start, deadline),
        )
    ]
    alerts = []
    for aid, began, raised, ended, seen, reason, transport, iphone in rows:
        matching = [
            (seq, ts, event, payload)
            for seq, ts, event, payload in events
            if payload.get("id") == aid and payload.get("metric") == metric
        ]
        raises = [
            (seq, ts)
            for seq, ts, event, body in matching
            if event == "alert.raised"
            and ts <= trigger_end
            and body.get("input_mode") == "live"
            and valid_reading(body, method, kind, unit)
            and body["value"] < low
        ]
        clears = [
            (seq, ts)
            for seq, ts, event, body in matching
            if event == "alert.cleared"
            and ts >= recovery_start
            and body.get("reason") == "returned_to_range"
        ]
        # The server closes on the observation timestamp, even when another sample
        # in the window later crosses the threshold. Check that exact recovery.
        start_sample = any(abs(r["at"] - began) < 1e-5 for r in unsafe)
        end_sample = ended is not None and any(
            abs(r["at"] - ended) < 1e-5 for r in restored
        )
        pair_ok = len(raises) == len(clears) == 1 and raises[0][0] < clears[0][0]
        seen_active = (
            seen is not None
            and raised <= seen <= deadline
            and bool(clears)
            and seen <= clears[0][1]
        )
        passed = (
            pair_ok
            and transport == "lan_https"
            and iphone == 1
            and seen_active
            and reason == "returned_to_range"
            and start_sample
            and end_sample
        )
        alerts.append(
            {
                "id": aid,
                "started": began,
                "raised": raised,
                "ended": ended,
                "parent_seen": seen,
                "reason": reason,
                "transport": transport,
                "iphone": iphone == 1,
                "raised_events": raises,
                "cleared_events": clears,
                "pass": bool(passed),
            }
        )
    return {
        "trigger_window": list(trigger),
        "recovery_window": list(recovery),
        "receipt_deadline": deadline,
        "metric": metric,
        "method": method,
        "trigger_samples": unsafe,
        "recovery_samples": restored,
        "alerts": alerts,
        "pass": trigger_end - start >= OBSERVE
        and end - recovery_start >= OBSERVE
        and trigger_end < recovery_start
        and any(alert["pass"] for alert in alerts),
    }


def score(db, sid, phase, evidence):
    if phase == "double_tap":
        return score_double(db, sid, [t["window"] for t in evidence["trials"]])
    if phase == "single_tap":
        return score_single(db, sid, *evidence["window"])
    if phase == "silent":
        return score_silent(db, sid, evidence["prepared_at"], *evidence["window"])
    if phase in EYE:
        return score_eye(
            db, sid, phase, evidence["trigger_window"], evidence["recovery_window"]
        )
    raise ValueError(f"Unknown phase: {phase}")


def record(db, sid, phase, guide):
    prepared = time.time()
    guide.ready(*PHASES[phase])
    if phase == "double_tap":
        trials = []
        for i, side in enumerate(TAP_SIDES):
            side_text = SIDE_TEXT[side]
            if i:
                guide.ready(
                    f"准备第 {i + 1}/5 次双击",
                    "看清提示并确认手机已回到后摄取景。准备好后点下方按钮，再按绿色指令操作。",
                )
            trial = guide.window(
                f"第 {i + 1}/5 次",
                f"现在双击{side_text}侧",
                f"在 iPhone 取景框标有「{side_text}镜框」的触控区快速点两下，然后停手。",
                OBSERVE,
            )
            trials.append({"window": trial})
            guide.settle(GRACE)
        observation = {"trials": trials}
    elif phase in EYE:
        near = phase == "near_far"
        trigger = guide.window(
            PHASES[phase][0],
            "现在靠近标记" if near else "现在遮暗纸面",
            "向标记靠近并保持，让整个标记一直在画面中。"
            if near
            else "遮暗页面并保持，让后摄继续取景。",
            EYE_SECONDS,
        )
        hold = "保持靠近，标记仍须完整可见。" if near else "继续保持纸面偏暗。"
        guide.ready(
            "保持当前状态，确认提醒",
            hold
            + "在手机和可见的家长护眼页查看提醒，然后点击准备。等下一个绿色指令再改变状态。",
        )
        recovery = guide.window(
            "恢复观察",
            "现在挪远" if near else "现在恢复照明",
            "慢慢挪远，保持标记完整可见。留意手机和家长端的恢复状态。"
            if near
            else "移开遮挡，恢复明亮照明，观察手机和家长端的恢复状态。",
            EYE_SECONDS,
        )
        guide.settle(GRACE)
        observation = {"trigger_window": trigger, "recovery_window": recovery}
    else:
        silent = phase == "silent"
        trial = guide.window(
            "入校静音" if silent else "单击对照",
            "静音下双击" if silent else "现在单击",
            "在 iPhone 原取景位置快速点两下，保持静音。"
            if silent
            else "在后摄取景区只点一下，保持取景。",
            OBSERVE,
        )
        guide.settle(GRACE)
        observation = {"window": trial}
        if silent:
            observation["prepared_at"] = prepared
    observed = guide.confirm(phase)
    result = score(db, sid, phase, observation)
    result["pass"] = result["pass"] and observed
    return {
        **({"operator_confirmed_both_displays": observed} if phase in EYE else {}),
        "protocol": PROTOCOL,
        "phase": phase,
        "ended": iso(time.time()),
        "operator_performed": observed,
        "result": result,
    }


def used_windows(phase, result):
    if phase in EYE:
        return [(result["trigger_window"][0], result["receipt_deadline"])]
    trials = result["trials"] if phase == "double_tap" else [result]
    return [
        (trial["window"][0], trial.get("receipt_deadline", trial["window"][1]))
        for trial in trials
    ]


def verify(db, evidence, phases=ALL):
    latest = {
        run["phase"]: run for run in evidence["runs"] if run.get("protocol") == PROTOCOL
    }
    measured, windows = {}, []
    missing = [phase for phase in phases if phase not in latest]
    for phase in phases:
        if phase not in latest:
            continue
        run = latest[phase]
        result = score(db, evidence["session"], phase, run["result"])
        result["operator_performed"] = run.get("operator_performed") is True
        if phase in EYE:
            result["operator_confirmed_both_displays"] = (
                run.get("operator_confirmed_both_displays") is True
            )
            result["pass"] = (
                result["pass"] and result["operator_confirmed_both_displays"]
            )
        windows_here = used_windows(phase, result)
        completed = all(
            0 <= start < deadline <= time.time() for start, deadline in windows_here
        )
        result["pass"] = result["pass"] and result["operator_performed"] and completed
        measured[phase] = result
        windows.extend(windows_here)
    ordered = sorted(windows)
    independent = all(b[0] > a[1] for a, b in pairwise(ordered))
    return {
        "session": evidence["session"],
        "device": evidence["device"],
        "protocol": PROTOCOL,
        "missing": missing,
        "independent_windows": independent,
        "runs": measured,
        "passed": not missing
        and independent
        and all(r["pass"] for r in measured.values()),
    }


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".{os.getpid()}.tmp")
    temp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    )
    temp.replace(path)


def append_run(path, evidence, run):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        latest = json.loads(path.read_text()) if path.exists() else evidence
        if latest["session"] != evidence["session"]:
            raise ValueError("Session mismatch")
        latest["runs"].append(run)
        save(path, latest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sid", required=True)
    parser.add_argument("--phase", required=True, choices=[*ALL, *GROUPS, *SCOPES])
    parser.add_argument("--db", type=Path, default=ROOT / "var/lumiread.sqlite3")
    parser.add_argument("--evidence", type=Path)
    parser.add_argument(
        "--guide",
        action="store_true",
        help="Open a clickable Mac preparation and timing page",
    )
    args = parser.parse_args()
    if not args.sid.replace("-", "").replace("_", "").isalnum():
        parser.error("Invalid session ID")
    dest = args.evidence or ROOT / "var/qa/iphone-sensors" / (args.sid + ".json")
    evidence = (
        json.loads(dest.read_text())
        if dest.exists()
        else {
            "session": args.sid,
            "device": "iPhone 16 Pro Max (operator declaration)",
            "runs": [],
        }
    )
    if evidence["session"] != args.sid:
        parser.error("Session mismatch")
    uri = "file:" + quote(str(args.db.resolve())) + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        if not db.execute("SELECT 1 FROM sessions WHERE id=?", (args.sid,)).fetchone():
            parser.error("Session not found in this database")
        if args.phase in SCOPES:
            report = verify(db, evidence, SCOPES[args.phase])
            name = {
                "verify": "iphone_sensor_trials",
                "verify-capture": "iphone_capture_trials",
                "verify-eye": "iphone_eye_trials",
            }[args.phase]
            print(
                json.dumps(
                    {
                        "passed": report["passed"],
                        "missing": report["missing"],
                        "independent_windows": report["independent_windows"],
                        "phases": {k: r["pass"] for k, r in report["runs"].items()},
                    }
                )
            )
            if report["passed"]:
                save(ROOT / "reports" / (name + ".json"), report)
            return 0 if report["passed"] else 1
        if __package__:
            from .field_guide import BrowserGuide, TerminalGuide
        else:
            from field_guide import BrowserGuide, TerminalGuide
        guide = BrowserGuide() if args.guide else TerminalGuide()
        try:
            phases = GROUPS.get(args.phase, (args.phase,))
            passed = True
            for phase in phases:
                run = record(db, args.sid, phase, guide)
                # Preserve every attempt, including legacy failures and interrupted multi-phase runs.
                append_run(dest, evidence, run)
                success = run["operator_performed"] and run["result"]["pass"]
                passed = passed and success
                print(phase, "PASS" if success else "FAILED", dest, flush=True)
            guide.finish(passed)
            return 0 if passed else 1
        finally:
            guide.close()


if __name__ == "__main__":
    raise SystemExit(main())
