#!/usr/bin/env python3
"""
Task Queue Ranker — Rank subagent tasks by unblockability before spawning.
Highest score = spawn first. Lowest score = spawn last or skip.

Usage:
    python3 task-queue-rank.py --tasks tasks.json
    # OR pipe from stdin
    echo '[{"name":"fix parser","deps":[],"type":"code","external":false}]' | python3 task-queue-rank.py

The platform-probe cache (verdicts from a pre-flight prober, keyed by
platform name: {"<platform>": {"verdict": "GO"|"BLOCKED"|...}}) is read
from, in order of precedence:
    --cache PATH
    $PLATFORM_PROBE_CACHE
    ~/.state/platform-probe-cache.json   (default; missing file = no cache)

Scoring:
    +100  No external dependencies (pure code)
    +80   Money lane (revenue work, marketplace earnings)
    +60   Fixes critical blocker
    +40   Internal dependency already satisfied
    +20   Fast (<3 min expected)
    -100  Needs browser auth / OAuth / captcha
    -80   Platform known dead (check cache)
    -60   Needs user action
    -40   Has unsatisfied dependencies
    -20   Long-running (>10 min)

Exit: prints ranked JSON array
"""
import json, os, sys, argparse
from pathlib import Path

DEFAULT_CACHE_FILE = Path.home() / ".state" / "platform-probe-cache.json"

def load_cache(cache_file):
    if cache_file.exists():
        try:
            with open(cache_file) as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def score_task(task, cache):
    score = 0
    reasons = []

    # External deps penalty
    if task.get("external", False):
        score -= 100
        reasons.append("external_dep")

    # Platform check
    platform = task.get("platform", "").lower()
    if platform:
        pc = cache.get(platform, {})
        if pc.get("verdict") == "BLOCKED":
            score -= 80
            reasons.append(f"platform_blocked:{platform}")
        elif pc.get("verdict") == "GO":
            score += 40
            reasons.append(f"platform_ready:{platform}")

    # Auth requirement
    if task.get("needs_auth", False):
        score -= 100
        reasons.append("needs_auth")

    # User action required
    if task.get("needs_user_action", False):
        score -= 60
        reasons.append("needs_user")

    # Money lane bonus
    if task.get("money_lane", False):
        score += 80
        reasons.append("money_lane")

    # Critical blocker
    if task.get("critical", False):
        score += 60
        reasons.append("critical")

    # Pure code bonus
    if task.get("type") == "code" and not task.get("external"):
        score += 100
        reasons.append("pure_code")

    # Fast task bonus
    if task.get("expected_minutes", 99) <= 3:
        score += 20
        reasons.append("fast")
    elif task.get("expected_minutes", 0) >= 10:
        score -= 20
        reasons.append("slow")

    # Dependencies satisfied?
    deps = task.get("depends_on", [])
    unsatisfied = []
    for dep in deps:
        dep_file = Path(dep)
        if not dep_file.exists():
            unsatisfied.append(dep)
    if unsatisfied:
        score -= 40
        reasons.append(f"unsatisfied_deps:{unsatisfied}")
    elif deps:
        score += 40
        reasons.append("deps_satisfied")

    return {"score": score, "reasons": reasons}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", help="JSON file with task array")
    parser.add_argument("--cache",
                        default=os.environ.get("PLATFORM_PROBE_CACHE"),
                        help="platform-probe cache JSON (default: ~/.state/platform-probe-cache.json)")
    args = parser.parse_args()

    if args.tasks:
        with open(args.tasks) as f:
            tasks = json.load(f)
    else:
        tasks = json.load(sys.stdin)

    cache_file = Path(args.cache) if args.cache else DEFAULT_CACHE_FILE
    cache = load_cache(cache_file)
    ranked = []
    for t in tasks:
        s = score_task(t, cache)
        ranked.append({
            **t,
            "rank_score": s["score"],
            "rank_reasons": s["reasons"],
        })

    ranked.sort(key=lambda x: x["rank_score"], reverse=True)
    print(json.dumps(ranked, indent=2))

if __name__ == "__main__":
    main()
