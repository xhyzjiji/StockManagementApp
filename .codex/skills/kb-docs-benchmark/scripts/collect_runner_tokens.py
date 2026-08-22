#!/usr/bin/env python3
"""Collect token usage from the runtime's own run log.

Why this is a script and not an instruction to grep: the agent-authored one-liner
version of this failed silently in production. A quoting error in the shell command
made the extraction return nothing, and the receipt format had no way to say "my
command broke" — so it reported `events=0`, which the reading rule then interpreted
as "this runtime logs no usage". The log at that moment provably held 158 events.

An error and a legitimate zero must never render the same. Every failure here sets
`err=` to something specific, and `events=` is only trusted when `err=none`.

Usage:
    python3 scripts/collect_runner_tokens.py --log <path> [--json <out.json>]

Emits exactly one line on stdout, meant to be returned verbatim as a receipt:

    LOGTOK file=… bytes=… events=N threads=N total=N answer=N in=N out=N rt=… err=…

Always exits 0: this is instrumentation, and a benchmark result must not bounce
because its cost accounting could not be read.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

# ---------------------------------------------------------------------------
# Runtime shapes. The file, the event name, and the field case ALL differ per
# runtime; carrying one runtime's triple to another yields a confident, silent
# zero. Detection probes for each shape rather than trusting a runtime label.
# ---------------------------------------------------------------------------
CODEX_MARK = '{"method":"thread/tokenUsage/updated","params":'
CURSOR_MARK = '"token:usage"'

# The answer worker identifies itself in its own prompt. Match the role sentence
# in every language the prompts are actually written in — an English-only pattern
# drops a Chinese-prompted worker into "unmatched", where it reads as zero.
ANSWER_PATTERNS = (
    'answer worker',
    'answer-worker',
    '答题 worker',
    '答题worker',
    '答题 Worker',
)
NOT_ANSWER_PATTERNS = ('quality analyz', 'docs quality', '文档质量')


def _arm_of(prompt: str) -> str:
    """Which arm this answer worker was told to run.

    Both arms can live in ONE session. The split into two runs existed only because a
    Cursor subagent returned no usage, so the only way to price an arm was to give it a
    session of its own; per-thread accounting removes that constraint. Once both arms
    share a session, the arm must be read off the worker's own prompt rather than
    inferred from which run it belonged to.

    Only the opening of the prompt is examined: the body of a with_docs prompt
    legitimately mentions without_docs (boundaries, contrasts), and matching the whole
    text would make every worker look like both arms at once.
    """
    head = prompt[:300].lower()
    has_without = 'without_docs' in head or 'without docs' in head
    # 'with_docs' is a substring of 'without_docs' — remove the negatives before asking.
    stripped = head.replace('without_docs', '').replace('without docs', '')
    has_with = 'with_docs' in stripped or 'with docs' in stripped
    if has_with and not has_without:
        return 'with_docs'
    if has_without and not has_with:
        return 'without_docs'
    return ''  # ambiguous — reported as unattributed rather than guessed


def _balanced(text: str, start: int) -> str | None:
    """Slice one complete JSON object starting at `start`, honoring strings."""
    depth = 0
    in_str = False
    esc = False
    i = start
    n = len(text)
    while i < n:
        c = text[i]
        if esc:
            esc = False
        elif c == '\\':
            esc = True
        elif c == '"':
            in_str = not in_str
        elif not in_str:
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        i += 1
    return None


def parse_codex_durations(text: str) -> dict[str, int]:
    """Elapsed ms per thread, summed over that thread's completed turns.

    Why this exists: the parent-measured wall clock it replaces was wrong by ~16x in
    production — it reported 55s for a turn the runtime itself clocked at 912s, i.e. it
    was timing the dispatch rather than the wait. That number landed in the database
    looking exactly like a real measurement, correctly labelled with its source, and
    passed every presence-and-provenance check. Only a magnitude cross-check caught it.

    The runtime already publishes the truth on each `turn/completed`. Read the
    instrument instead of asking the subject to hold a stopwatch.
    """
    total: dict[str, int] = {}
    for m in re.finditer(re.escape('{"method":"turn/completed","params":'), text):
        blob = _balanced(text, m.start())
        if blob is None:
            continue
        try:
            ev = json.loads(blob)
        except Exception:
            continue
        p = ev.get('params') or {}
        tid = p.get('threadId')
        turn = p.get('turn') or {}
        ms = turn.get('durationMs')
        if ms is None:
            started, completed = turn.get('startedAt'), turn.get('completedAt')
            if started and completed:
                # Seconds in this shape; only accept a forward-running interval.
                ms = (completed - started) * 1000 if completed >= started else None
        if not tid or not ms or ms <= 0:
            continue
        total[tid] = total.get(tid, 0) + int(ms)
    return total


def parse_codex(text: str):
    """Last tokenUsage per thread (values are cumulative — verified monotonic),
    plus each thread's role taken from the first userMessage sent to it."""
    durations = parse_codex_durations(text)
    last: dict[str, dict] = {}
    order: list[str] = []
    for m in re.finditer(re.escape(CODEX_MARK), text):
        blob = _balanced(text, m.start())
        if blob is None:
            continue
        try:
            ev = json.loads(blob)
        except Exception:
            continue
        p = ev.get('params') or {}
        tid = p.get('threadId')
        total = ((p.get('tokenUsage') or {}).get('total')) or {}
        if not tid or total.get('totalTokens') is None:
            continue
        if tid not in last:
            order.append(tid)
        last[tid] = total

    roles: dict[str, str] = {}
    # Match only the event NAME, then decide from the PARSED object whether it is a user
    # message. The earlier pattern also pinned `"item"` as the first key inside `params`,
    # so a serializer that emitted `threadId` first would match nothing — and the receipt
    # would then say `no_answer_worker_thread_matched`, i.e. "this run had no answer
    # worker" rather than "my pattern is key-order dependent". Same failure family this
    # whole file exists to prevent: a broken reader that reads as an empty result.
    for m in re.finditer(r'\{"method":"item/completed"', text):
        blob = _balanced(text, m.start())
        if blob is None:
            continue
        try:
            ev = json.loads(blob)
        except Exception:
            continue
        p = ev.get('params') or {}
        item = p.get('item') or {}
        if item.get('type') != 'userMessage':
            continue
        tid = p.get('threadId')
        if not tid or tid in roles:
            continue
        body = item.get('content') or item.get('text') or ''
        if isinstance(body, list):
            body = ' '.join(str(x.get('text', '')) for x in body if isinstance(x, dict))
        roles[tid] = re.sub(r'\s+', ' ', str(body))[:400]

    threads = []
    for tid in order:
        tu = last[tid]
        prompt = roles.get(tid, '')
        low = prompt.lower()
        is_answer = (any(p.lower() in low for p in ANSWER_PATTERNS)
                     and not any(p in low for p in NOT_ANSWER_PATTERNS))
        threads.append({
            'thread_id': tid,
            'is_answer_worker': is_answer,
            'arm': _arm_of(prompt) if is_answer else '',
            'total_tokens': tu.get('totalTokens') or 0,
            'input_tokens': tu.get('inputTokens') or 0,
            'output_tokens': tu.get('outputTokens') or 0,
            'duration_ms': durations.get(tid, 0),
        })
    return threads


def parse_cursor(text: str):
    """Single session-level event; no per-thread split is available."""
    found = None
    for m in re.finditer(r'\{"ts"[^\n]*?"token:usage"', text):
        line_start = text.rfind('{', 0, m.start() + 1)
        blob = _balanced(text, line_start if line_start >= 0 else m.start())
        if blob is None:
            continue
        try:
            ev = json.loads(blob)
        except Exception:
            continue
        e = ev.get('event') or {}
        if e.get('name') != 'token:usage' or e.get('from') != 'MAIN_AGENT':
            continue
        total = e.get('total_tokens') or 0
        if not total:
            total = (e.get('input_tokens') or 0) + (e.get('output_tokens') or 0)
        found = {
            'thread_id': 'MAIN_AGENT',
            'is_answer_worker': False,  # session total, NOT the answer worker's cost
            'arm': '',
            'total_tokens': total,
            'input_tokens': e.get('input_tokens') or 0,
            'output_tokens': e.get('output_tokens') or 0,
            'duration_ms': 0,
        }
    return [found] if found else []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--log', required=True, help='path to the runtime run log')
    ap.add_argument('--json', help='optional path to also write structured output')
    args = ap.parse_args()

    def emit(**kw):
        # `none` everywhere a value is genuinely absent. Never 0 as a stand-in:
        # 0 reads as "ran and cost nothing", which is a different claim entirely.
        fields = ['file', 'bytes', 'events', 'threads', 'total', 'answer', 'in', 'out', 'dur',
                  'with', 'without', 'rt', 'err']
        print('LOGTOK ' + ' '.join(f'{k}={kw.get(k, "none")}' for k in fields))
        if args.json:
            try:
                with open(args.json, 'w', encoding='utf-8') as fh:
                    json.dump(kw, fh, ensure_ascii=False, indent=1)
            except Exception:
                pass
        return 0

    path = args.log
    if not os.path.isfile(path):
        return emit(file='none', err='log_not_found')
    try:
        size = os.path.getsize(path)
        with open(path, 'r', errors='replace') as fh:
            text = fh.read()
    except Exception as exc:
        return emit(file=path, err=f'read_failed:{type(exc).__name__}')

    if CODEX_MARK in text:
        rt, threads = 'codex', parse_codex(text)
        n_events = text.count(CODEX_MARK)
    elif CURSOR_MARK in text:
        rt, threads = 'cursor', parse_cursor(text)
        n_events = text.count(CURSOR_MARK)
    else:
        # Genuinely no usage events of any known shape. This is the ONLY path that
        # may report events=0 with err=none, and even here the caller is told which
        # shapes were tried so "unknown runtime" stays distinguishable from "empty".
        return emit(file=path, bytes=size, events=0, threads=0, rt='unknown',
                    err='no_known_event_shape')

    if not threads:
        return emit(file=path, bytes=size, events=n_events, threads=0, rt=rt,
                    err='shape_matched_but_no_parsable_events')

    # Per-arm rollup. Both arms in one session is the shape the split was invented to
    # avoid; now that each thread carries its own accounting, it is the shape to prefer,
    # and the receipt has to be able to say what each arm cost.
    def arm_pair(name):
        """`<tokens>/<duration_ms>` for one arm, with each half independently absent-able.

        A zero duration is NOT reported as 0. Read too early — before the worker's turn
        has completed — the runtime has published no duration yet, and emitting `0` there
        would hand downstream a measurement saying the arm answered instantly. Observed
        live: an early read produced `with=86616/0`, i.e. real tokens beside a fake clock.
        The same NULL≠0 rule the DB columns carry has to hold in the receipt too, or the
        receipt becomes the place the zero is born.
        """
        rows = [t for t in threads if t.get('arm') == name]
        if not rows:
            return 'none'
        tok = sum(r['total_tokens'] for r in rows)
        dur = sum(r.get('duration_ms') or 0 for r in rows)
        return f"{tok or 'none'}/{dur or 'none'}"

    total = sum(t['total_tokens'] for t in threads)
    tin = sum(t['input_tokens'] for t in threads)
    tout = sum(t['output_tokens'] for t in threads)
    answers = [t for t in threads if t['is_answer_worker']]

    # Per-arm cost is the answer worker's thread. Report the session total too, but
    # never silently substitute one for the other — they differ by ~4x in practice.
    if answers:
        ans = sum(t['total_tokens'] for t in answers)
        ain = sum(t['input_tokens'] for t in answers)
        aout = sum(t['output_tokens'] for t in answers)
        # Elapsed for the same threads. 0 means the runtime published no turn duration —
        # report it as absent, never as an instant answer.
        adur = sum(t.get('duration_ms') or 0 for t in answers) or None
        err = 'none'
    else:
        ans = ain = aout = adur = None
        err = 'no_answer_worker_thread_matched'

    with_pair, without_pair = arm_pair('with_docs'), arm_pair('without_docs')

    # `err=none` used to mean only "an answer worker was found" — it said nothing about
    # whether BOTH arms were found. That let `err=none with=none without=12345/6789`
    # happen, and the documented reading rule ("every other field is meaningless until
    # err=none") then licenses treating that half-empty receipt as good. A missing arm is
    # exactly the kind of failure this err= vocabulary exists to name, and the per-arm
    # fields were added after the vocabulary was written — so they never got a word.
    #
    # Reported, not judged: a run that deliberately measured ONE leg (`configuration` set
    # to a single arm) will legitimately show this, and the reader decides. What must not
    # happen is the receipt staying silent about it.
    if err == 'none':
        missing = [n for n, v in (('with', with_pair), ('without', without_pair)) if v == 'none']
        if missing:
            err = 'arm_missing:' + '+'.join(missing)

    return emit(file=path, bytes=size, events=n_events, threads=len(threads),
                total=total, answer=ans if ans is not None else 'none',
                **{'with': with_pair, 'without': without_pair},
                **{'in': ain if ain is not None else 'none',
                   'out': aout if aout is not None else 'none',
                   'dur': adur if adur is not None else 'none'},
                rt=rt, err=err) or _also(args, threads, total, tin, tout)


def _also(args, threads, total, tin, tout):
    if args.json:
        try:
            with open(args.json, 'r+', encoding='utf-8') as fh:
                data = json.load(fh)
                data['threads_detail'] = threads
                data['session_input_tokens'] = tin
                data['session_output_tokens'] = tout
                data['session_total_tokens'] = total
                fh.seek(0)
                json.dump(data, fh, ensure_ascii=False, indent=1)
                fh.truncate()
        except Exception:
            pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
