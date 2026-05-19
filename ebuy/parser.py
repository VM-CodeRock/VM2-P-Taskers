#!/usr/bin/env python3
"""
eBuy Consolidated Notice parser.
Parses ebuy_admin@gsa.gov emails into structured event records.
"""
import json
import re
import hashlib
from datetime import datetime
from pathlib import Path

STATUS_KEYWORDS = ['NEW REQUEST', 'Q&A ADDED', 'AMENDED', 'CANCELED', 'CANCELLED', 'WITHDRAWN', 'CLOSED']

# Date pattern like "04/06/2026 06:10 PM EDT" or with EST
DATE_RE = re.compile(r'(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}\s+[AP]M\s+(?:EDT|EST))')
REQ_LINE_RE = re.compile(r'^((?:RFI|RFQ|RFP)\d+[A-Z]?)\s+(.+)$', re.MULTILINE)
VEHICLE_RE = re.compile(r'Consolidated Notice\)\s*-\s*(\S+)')


def parse_email(email):
    """Parse a single ebuy_admin email into an event dict, or None on failure."""
    body = email.get('body', '') or ''
    subject = email.get('subject', '') or ''
    email_date = email.get('date', '')

    # Vehicle from subject
    vm = VEHICLE_RE.search(subject)
    vehicle = vm.group(1).strip() if vm else None

    # Get the request section (before "Definition of Status:")
    req_section = body.split('Definition of Status:')[0]

    # Find the request ID + status line: "RFI1804638      NEW REQUEST     04/06/2026 06:10 PM EDT"
    req_match = REQ_LINE_RE.search(req_section)
    if not req_match:
        return None
    request_id = req_match.group(1).strip()
    rest_of_line = req_match.group(2)

    # Status: pick longest matching keyword at start of rest_of_line
    status = None
    for kw in sorted(STATUS_KEYWORDS, key=len, reverse=True):
        if rest_of_line.startswith(kw):
            status = kw
            break
    if not status:
        # Try fallback: word(s) before first date
        first_date_m = DATE_RE.search(rest_of_line)
        if first_date_m:
            candidate = rest_of_line[:first_date_m.start()].strip()
            status = candidate if candidate else 'UNKNOWN'
        else:
            status = 'UNKNOWN'

    # Find all dates in the request section
    dates = DATE_RE.findall(req_section)
    posted_date = dates[0] if len(dates) >= 1 else None
    due_by = dates[1] if len(dates) >= 2 else None

    # Buyer + Title: text between posted_date and due_by, then text after due_by on that line
    buyer = None
    title = None
    if posted_date and due_by:
        # Find positions in req_section
        try:
            posted_pos = req_section.index(posted_date) + len(posted_date)
            due_pos = req_section.index(due_by, posted_pos)
            between = req_section[posted_pos:due_pos].strip()
            after = req_section[due_pos + len(due_by):].strip()

            # Buyer = collapse the multi-line text between posted and due
            buyer_lines = [ln.strip() for ln in between.split('\n') if ln.strip()]
            buyer = ' | '.join(buyer_lines) if buyer_lines else None

            # Title = first line after due_by (rest of line through end of paragraph)
            # Cut at next blank line or first carriage return paragraph break
            title_raw = after.split('\n')[0].strip()
            # If title is empty, try next non-empty line
            if not title_raw:
                for ln in after.split('\n'):
                    if ln.strip():
                        title_raw = ln.strip()
                        break
            title = title_raw if title_raw else None
        except ValueError:
            pass

    # Dedupe key
    dedupe_basis = f"{request_id}|{status}|{posted_date or ''}"
    event_id = hashlib.sha1(dedupe_basis.encode()).hexdigest()[:16]

    return {
        'event_id': event_id,
        'request_id': request_id,
        'status': status,
        'posted_date': posted_date,
        'due_by': due_by,
        'buyer': buyer,
        'title': title,
        'vehicle': vehicle,
        'email_date': email_date,
        'email_id': email.get('email_id'),
        'subject': subject,
        'reviewed': False,
        'analyst_requested': False,
        'analyst_requested_at': None,
        'notes': None,
    }


def main():
    # When run from repo: outputs go alongside this script
    here = Path(__file__).parent
    src = Path('/home/user/workspace/ebuy_emails_raw.json')
    out_jsonl = here / 'ebuy_history.jsonl'
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)

    with src.open() as f:
        emails = json.load(f)

    # Sort emails by date ascending so the jsonl is chronological
    emails.sort(key=lambda e: e.get('date', ''))

    seen = set()
    events = []
    failed = []

    for em in emails:
        ev = parse_email(em)
        if ev is None:
            failed.append({'email_id': em.get('email_id'), 'subject': em.get('subject'), 'date': em.get('date')})
            continue
        if ev['event_id'] in seen:
            continue
        seen.add(ev['event_id'])
        events.append(ev)

    # Write jsonl (append-only style — but this is initial backfill so we overwrite)
    with out_jsonl.open('w') as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False) + '\n')

    # Summary
    print(f'Parsed: {len(events)} unique events from {len(emails)} emails')
    print(f'Failed to parse: {len(failed)}')
    if failed:
        for x in failed[:5]:
            print(f"  - {x}")

    # Status breakdown
    from collections import Counter
    status_counts = Counter(e['status'] for e in events)
    print('\nStatus breakdown:')
    for s, c in status_counts.most_common():
        print(f'  {s}: {c}')

    # Vehicle breakdown
    vehicle_counts = Counter(e['vehicle'] for e in events)
    print('\nVehicle breakdown:')
    for v, c in vehicle_counts.most_common():
        print(f'  {v}: {c}')

    # Unique requests vs total events
    unique_reqs = set(e['request_id'] for e in events)
    print(f'\nUnique Request IDs: {len(unique_reqs)}')
    print(f'Total events (incl. amendments/Q&A): {len(events)}')

    return events


if __name__ == '__main__':
    main()
