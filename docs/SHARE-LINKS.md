# VM2 Share Links — Magic-link bypass

**Last updated:** 2026-05-08

A way to share VM2 URLs without giving out the basic-auth password. Anyone with a current key in the URL gets straight into the portal — no login prompt.

---

## How it works

```
https://vm2-p-taskers-production.up.railway.app/portal.html?key=k-260508-7QmF3vR9LaB2tNcK
                                                            └────────── magic key ─────────┘
```

When nginx sees `?key=<value>`:

1. Looks up the value in the active-keys list (set via `VM2_PUBLIC_KEYS` Railway env var)
2. If valid → skips the basic-auth challenge, sets a cookie `vm2_key` for 7 days
3. Subsequent navigation to subpages, deliverables, project pages reads the cookie automatically — no need to keep `?key=` in every URL
4. If invalid (or no key) → standard basic-auth prompt appears

The keys are checked **in addition to** basic-auth — anyone who knows the username/password still gets in normally.

---

## Quick reference

### Generate a new key

```bash
./scripts/generate_share_key.sh
# → k-260508-7QmF3vR9LaB2tNcKaB12
```

Format: `k-<YYMMDD>-<22 random base62 chars>`. The date prefix makes rotation tracking obvious.

### Activate the key

1. Open Railway → **vm2-portal** service → **Variables** tab
2. Find or add `VM2_PUBLIC_KEYS` (comma-separated)
3. Append the new key, optionally keep the previous one for a grace window:

   ```
   VM2_PUBLIC_KEYS=k-260508-NEW-KEY,k-260501-OLD-KEY
   ```

4. Save. Railway redeploys in ~30 seconds.
5. Test: `https://<railway-url>/portal.html?key=k-260508-NEW-KEY` should load directly.

### Share the link

```
https://vm2-p-taskers-production.up.railway.app/portal.html?key=k-260508-NEW-KEY
```

Send it via email, Slack, anywhere. The recipient clicks once → in for 7 days.

### Revoke a key

Remove it from `VM2_PUBLIC_KEYS`. Save. Railway redeploys. The URL stops working ~30s later.

### See your active keys

Visit [https://vm2-p-taskers-production.up.railway.app/go](https://vm2-p-taskers-production.up.railway.app/go) (basic-auth required). The page lets you:

- See which keys are active vs. invalid
- Copy a key or full URL with one click
- Generate a new key client-side
- Save keys to localStorage for future visits

---

## Recommended rotation rhythm

| Cadence | When to rotate |
|---|---|
| Every 7 days | After sending the URL to anyone outside Changeis |
| Every 30 days | If the URL is only used personally |
| Immediately | After leaking the URL by accident or losing a device |

**Grace-window pattern**: Always keep the **previous** key active for 2-3 days when rotating. This avoids breaking links you sent recently.

```
# Day 0:  VM2_PUBLIC_KEYS=k-current
# Day 7:  VM2_PUBLIC_KEYS=k-new,k-current     ← grace window starts
# Day 10: VM2_PUBLIC_KEYS=k-new                ← old key expires
```

---

## Security notes

- **Treat keys like passwords.** Anyone with the URL gets full read access (and can hit POST endpoints if they figure them out — the API has no auth of its own beyond nginx).
- **HTTPS only.** Railway terminates TLS, so URLs are encrypted in transit. But anyone who sees the URL (browser history, screen-share, email forwarding) gets in.
- **Don't commit keys to the repo.** `VM2_PUBLIC_KEYS` lives only in Railway env vars. Same model as `VM2_AUTH_PASSWORD`.
- **Rotate after sharing externally.** A 7-day rotation is the recommended cadence for any link you've sent outside your own browser.
- **The cookie is HttpOnly + SameSite=Lax** so JavaScript can't read it and other origins can't ride it.
- **Magic-link bypasses ALL pages**, not just the one you linked. Don't share the link with anyone who shouldn't see project deliverables, the Todoist Auto-Helper, etc. For per-deliverable scoping, see "Future work" below.

---

## Architecture

```
nginx.conf
├── map $arg_key $effective_key { ... }    ← prefer query param, fall back to cookie
├── map $effective_key $auth_realm { ... } ← active keys → "off", else realm name
└── server { auth_basic $auth_realm; ... }  ← per-request decision

entrypoint.sh
└── reads VM2_PUBLIC_KEYS env var → injects map entries between
    # __VM2_PUBLIC_KEYS_BEGIN__ and # __VM2_PUBLIC_KEYS_END__ markers
```

Key files:

- [`nginx.conf`](../nginx.conf) — the `map` directive and conditional `auth_basic`
- [`entrypoint.sh`](../entrypoint.sh) — env var → nginx config injection
- [`go.html`](../go.html) — the `/go` share-link helper page
- [`scripts/generate_share_key.sh`](../scripts/generate_share_key.sh) — key generator

---

## Future work (not built today)

- **Auto-rotation cron** — generate a new key every Sunday, update Railway env via API, email the new URL to varun@changeis.com
- **Per-deliverable scoped keys** — sub-pattern URLs that grant access to a single page only
- **Read-only mode for shared keys** — block POST `/api/projects/*` when accessed via magic link, require basic-auth for writes
- **Key audit log** — track which key was used to access which page, when

Each of these is a 30-60 minute add when you want them.
