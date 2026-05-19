#!/usr/bin/env python3
"""
eBuy incremental update — given new raw emails JSON, append to history.jsonl with dedupe.

Usage:
  python3 ebuy_incremental.py --new-emails /path/to/new_emails.json [--run-mode incremental|reconcile]
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from parser import parse_email   # noqa: E402  (in-repo module)

HERE = Path(__file__).parent
HISTORY = HERE / 'ebuy_history.jsonl'
STATE = HERE / 'state.json'
PARSE_ERRORS = HERE / 'parse_errors.jsonl'


def load_existing_hashes():
    seen = set()
    if HISTORY.exists():
        with HISTORY.open() as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    ev = json.loads(line)
                    seen.add(ev['event_id'])
                except Exception:
                    pass
    return seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--new-emails', required=True, help='Path to JSON file with list of new emails')
    ap.add_argument('--run-mode', default='incremental', choices=['incremental', 'reconcile'])
    args = ap.parse_args()

    new_emails = json.loads(Path(args.new_emails).read_text())
    print(f'Input: {len(new_emails)} emails')

    seen = load_existing_hashes()
    print(f'Existing event hashes: {len(seen)}')

    new_events = []
    skipped = 0
    failed = []

    for em in new_emails:
        ev = parse_email(em)
        if ev is None:
            failed.append({
                'email_id': em.get('email_id'),
                'subject': em.get('subject'),
                'date': em.get('date'),
                'mode': args.run_mode,
                'failed_at': datetime.now(timezone.utc).isoformat(),
            })
            continue
        if ev['event_id'] in seen:
            skipped += 1
            continue
        new_events.append(ev)
        seen.add(ev['event_id'])

    # Append new events
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY.open('a') as f:
        for ev in new_events:
            f.write(json.dumps(ev, ensure_ascii=False) + '\n')

    # Log parse errors
    if failed:
        with PARSE_ERRORS.open('a') as f:
            for x in failed:
                f.write(json.dumps(x, ensure_ascii=False) + '\n')

    # Update state
    state = {}
    if STATE.exists():
        try: state = json.loads(STATE.read_text())
        except: state = {}
    total_events = sum(1 for _ in HISTORY.open()) if HISTORY.exists() else 0
    state.update({
        'last_run_iso': datetime.now(timezone.utc).astimezone().isoformat(),
        'last_run_mode': args.run_mode,
        'last_run_input_emails': len(new_emails),
        'last_run_new_events': len(new_events),
        'last_run_skipped_duplicates': skipped,
        'last_run_parse_failures': len(failed),
        'total_events': total_events,
        'seen_event_hashes_count': len(seen),
    })
    STATE.write_text(json.dumps(state, indent=2))

    print(f'New events appended: {len(new_events)}')
    print(f'Skipped duplicates: {skipped}')
    print(f'Parse failures: {len(failed)}')
    print(f'Total events in history: {total_events}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
