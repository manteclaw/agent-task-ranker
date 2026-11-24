# agent-task-ranker

Rank a queue of subagent tasks by **unblockability** before you spend a spawn
slot: what can actually be done right now, in what order.

Feed it a JSON array of tasks (file or stdin); it prints the same array back,
sorted, each task annotated with `rank_score` and `rank_reasons` so the
ordering is auditable instead of vibes.

## Who it's for

Anyone orchestrating multiple agents against a mixed backlog — some tasks are
pure code that can start immediately, some are stuck behind a dead platform,
a login wall, or the user. Spawning in queue order wastes your best slots on
the blocked items. Rank first, spawn in score order.

## The scoring rubric

| Signal | Task field | Score |
|---|---|---|
| Pure code, no external dependencies | `type: "code"`, `external: false` | **+100** |
| Money lane (revenue work) | `money_lane: true` | **+80** |
| Fixes a critical blocker | `critical: true` | **+60** |
| Internal dependency already satisfied | `depends_on` paths all exist | **+40** |
| Platform probe says GO | `platform` + cache verdict `GO` | **+40** |
| Fast (≤3 min expected) | `expected_minutes` | **+20** |
| Long-running (≥10 min expected) | `expected_minutes` | **−20** |
| Unsatisfied dependencies | `depends_on` paths missing | **−40** |
| Needs user action | `needs_user_action: true` | **−60** |
| Platform known dead/blocked | `platform` + cache verdict `BLOCKED` | **−80** |
| Needs browser auth / OAuth / captcha | `needs_auth: true` or `external: true` | **−100** |

## Spawn-order pattern

The rubric implements one operator's slot-management rule:

1. **Pure code first** — no external deps, starts now, finishes deterministically.
2. **Money lane next** — revenue work outranks housekeeping.
3. **Critical fixes** — unblock other work early.
4. **Satisfied internal deps** — ready the moment a slot frees.
5. **External deps last, browser-auth at the very back** — in a headless
   setup these are the tasks most likely to burn a slot and return nothing.

Keep one slot in reserve for emergency respawns instead of filling every
slot the ranker offers you.

## Usage

```console
$ cat tasks.json
[
  {"name": "fix response parser", "type": "code", "external": false, "expected_minutes": 2},
  {"name": "register on new marketplace", "platform": "someplace", "needs_auth": true, "expected_minutes": 15},
  {"name": "ship earnings report", "money_lane": true, "type": "code", "external": false}
]

$ python3 task-queue-rank.py --tasks tasks.json
[
  { "name": "ship earnings report", ..., "rank_score": 180, "rank_reasons": ["money_lane", "pure_code"] },
  { "name": "fix response parser",  ..., "rank_score": 120, "rank_reasons": ["pure_code", "fast"] },
  { "name": "register on new marketplace", ..., "rank_score": -120, "rank_reasons": ["needs_auth", "slow"] }
]

$ cat tasks.json | python3 task-queue-rank.py    # stdin works too
```

### Platform-probe cache

If you run a pre-flight prober (see `agent-preflight-probe`), its verdicts
feed the platform rows above. The cache is a JSON object keyed by platform
name:

```json
{ "someplace": { "verdict": "BLOCKED", "reason": "browser OAuth required" } }
```

Location, in order of precedence: `--cache PATH`, `$PLATFORM_PROBE_CACHE`,
`~/.state/platform-probe-cache.json`. A missing cache is fine — platform
rows just don't fire. See `.env.example`.

## Honest limits

- **The weights are one operator's heuristic, not an optimal scheduler.**
  They are tuned for one person's lanes (headless agents, marketplace work,
  a hard rule that browser-auth tasks go last). They are constants in one
  function precisely so you can edit them — treat the table above as a
  documented starting rubric, and re-tune it against your own outcomes.
- **It ranks the metadata you give it.** A task mislabelled as pure code
  ranks as pure code. The ranker never probes anything itself; garbage in,
  confidently ranked garbage out.
- **Dependency checks are file-existence checks.** `depends_on` entries are
  treated as paths; a path that exists but is stale still counts as
  satisfied.

## License

MIT — see `LICENSE`.
