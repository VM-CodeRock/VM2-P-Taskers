# VM2-P-Taskers — Disaster Recovery Runbook

**Last updated**: 2026-05-05
**Use this when**: production is broken, Railway is unreachable, the repo is corrupted, secrets are lost, or you need to rebuild from scratch.

Read [ARCHITECTURE.md](./ARCHITECTURE.md) first if you haven't.

---

## 1. Severity ladder (start here)

| Symptom | Severity | Jump to |
|---|---|---|
| Browser shows 500/502 | P1 | §3 nginx down |
| Promote button fails | P2 | §4 API down |
| `portal.html` shows raw `<li>` tags | P2 | §5 portal corruption |
| Salt/password mismatch on a file | P3 | §6 (DEPRECATED — should never happen post-Railway) |
| Lost the Railway dashboard | P1 | §7 rebuild from scratch |
| Lost the GitHub repo | P0 | §8 nuclear |
| Cron not firing | P3 | §9 cron recovery |

---

## 2. Quick diagnostic commands

Run these first, in order, to localize the problem.

```bash
# ① Live URL responding?
curl -I -u vm2:97harry23! https://vm2-p-taskers-production.up.railway.app/portal.html

# ② API health?
curl -s -u vm2:97harry23! https://vm2-p-taskers-production.up.railway.app/api/health

# ③ Project list reachable?
curl -s -u vm2:97harry23! https://vm2-p-taskers-production.up.railway.app/api/projects | head

# ④ GitHub repo state?
git ls-remote https://github.com/vm-coderock/VM2-P-Taskers.git HEAD

# ⑤ Last 5 commits
git -C /tmp/repo log --oneline -5  # after a fresh clone
```

If ① returns 401 → basic-auth misconfigured (env var missing/wrong).
If ① returns 502 → nginx is up but upstream (you're hitting an API route) is down.
If ② succeeds but ③ fails → API process up, project_helper import broken.
If ④ fails → GitHub access lost or repo deleted.

---

## 3. P1: nginx (Service A) is down

**Symptom**: portal.html and all deliverables return 5xx or hang.

```bash
# Railway dashboard → vm2-portal service → Deployments tab
#   - Look at the most recent deploy: did the build fail?
#   - If yes: roll back to the previous green deploy (Deployments → ⋯ → Redeploy)
#   - If the deploy succeeded but the container crashes: check Logs

# Common failure modes:
#   "openssl: not found" → Dockerfile missing openssl install. Fix line in
#                          Dockerfile: RUN apk add --no-cache openssl
#   "could not bind to 8080" → another process bound; restart container
#   "auth_basic_user_file failed" → entrypoint.sh didn't write .htpasswd;
#                                   check VM2_AUTH_PASSWORD env var is set
```

**Fast rollback**:
```
Railway → vm2-portal → Deployments → previous green build → Redeploy
```

---

## 4. P2: Projects API (Service B) is down

**Symptom**: Promote button shows "Error: Failed to fetch", projects.html shows empty cards or "Could not load projects".

```bash
# ① Check if the service exists and is healthy
# Railway dashboard → vm2-projects-api service → Logs
# Look for: "[entrypoint] Cloning ..." then "INFO: Application startup complete."

# ② Common failure modes
#   - Missing GITHUB_TOKEN → git clone fails. Set token in Railway env.
#   - Repo URL wrong → clone hangs. Check REPO_URL or rely on default.
#   - project_helper.py import error → fix syntax in scripts/project_helper.py and push.
#   - 409 conflicts → cron pushed concurrently; transient, browser retries.

# ③ Force redeploy
# Railway → vm2-projects-api → Settings → Redeploy
# OR push any commit to main (Railway auto-redeploys on push)

# ④ If completely broken, rebuild from api/Dockerfile manually:
docker build -f api/Dockerfile -t vm2-api .
docker run -e GITHUB_TOKEN=$TOKEN -p 8000:8000 vm2-api
```

If the API is permanently broken, the portal stays fully functional — only the Promote button stops working until the API is back. Cards/list views on projects.html still load (they read project state from the project HTML files).

---

## 5. P2: portal.html corrupted

**Symptom**: Raw underlined links above the topbar, bullet list mid-table, lint failure.

```bash
git clone https://github.com/vm-coderock/VM2-P-Taskers.git /tmp/recover
cd /tmp/recover

# ① Check the lint
python3 scripts/portal_lint.py
# Lists every issue found

# ② Auto-recover from the last known-clean commit
LAST_CLEAN=$(git log --oneline -- portal.html | grep -i "fix portal\|clean portal" | head -1 | awk '{print $1}')
git show $LAST_CLEAN:portal.html > portal.html

# ③ Re-add any missing entries via the helper
python3 scripts/portal_add_entry.py --file <name>.html --title "..." --type "..." --date YYYY-MM-DD

# ④ Verify and push
python3 scripts/portal_lint.py
git add portal.html
git commit -m "Recover portal.html from corruption"
git push
```

**Root cause prevention**: Cron task instructions must use `portal_add_entry.py`. See `scripts/README.md`. The lint script catches future regressions; wire it into CI/Railway-build if drift continues.

---

## 6. P3: StaticCrypt password mismatch (DEPRECATED)

This entire failure mode was eliminated in the March 25, 2026 Railway migration. If you see `class="staticrypt-html"` in any current file, **decrypt it back to plain HTML** — do NOT add more encryption.

Decryption recipe is preserved at `_system/staticrypt-decrypt.py` (not in repo by default; see Honcho memory `[2026-03-25]` for the algorithm: PBKDF2 SHA-1 1K → SHA-256 14K → SHA-256 585K iterations, UTF-8 salt).

---

## 7. P1: Lost Railway dashboard / account

If you've lost access to the Railway account or need to migrate hosts:

### Option A: Recover Railway access
1. Railway support: support@railway.com — provide GitHub username, email
2. Account recovery typically takes <24h

### Option B: Rebuild on a new Railway account / different host

The system is **portable** — every config is in the repo. To rebuild:

#### Service A (nginx static)
1. New Railway project → **+ New** → Deploy from GitHub Repo → select `vm-coderock/VM2-P-Taskers`
2. Railway picks up the top-level `Dockerfile` automatically
3. Add env vars:
   ```
   VM2_AUTH_USERNAME=vm2
   VM2_AUTH_PASSWORD=97harry23!
   VM2_TODOIST_TOKEN=<your-token>
   ```
4. Settings → Networking → Generate Domain
5. Verify: `curl -u vm2:97harry23! https://<new-url>/portal.html`

#### Service B (Projects API)
1. **+ New** in the same Railway project → Deploy from GitHub Repo
2. Settings → Build → set **Dockerfile Path = `api/Dockerfile`**
3. Settings → Networking → Service Name = `vm2-projects-api` (matches the `proxy_pass` in nginx.conf)
4. Add env vars:
   ```
   GITHUB_TOKEN=<PAT with repo scope>
   GIT_USER_EMAIL=vm2@changeis.com
   GIT_USER_NAME=VM2 Projects API
   ```
5. Verify: from Service A logs you should see successful `/api/health` calls

#### Other hosting platforms
The Docker images run anywhere. Equivalent setups:
- **Fly.io**: `fly launch` in repo root for nginx, then `fly launch -f api/Dockerfile` for API
- **Render**: Web Service from Dockerfile (twice)
- **DigitalOcean App Platform**: same; just point at the two Dockerfiles
- **AWS ECS/Fargate**: build and push the two images, run as two tasks

Update the `vm2-portal` env var `VM2_PROJECTS_API_URL` to point at the new internal URL of Service B.

---

## 8. P0: Lost the GitHub repo

**Worst case.** All work is gone unless you have a backup.

### Restore sources (in order of preference)
1. **Dropbox snapshot** — `V M2/VM2-main-folder/VM2-P/` should have copies of every deliverable. Index by date.
2. **Local clones** — anyone who's run the API or done dev work should have `/repo` or a local checkout.
3. **Railway image** — the running container has a complete checkout in `/usr/share/nginx/html`. Connect with `railway run bash` and tarball it: `tar czf /tmp/vm2.tgz /usr/share/nginx/html && cat /tmp/vm2.tgz | base64`
4. **Honcho memory** — has cron specs, key decisions, slugs of all major deliverables. Use to reconstruct what should exist.

### Rebuild repo
```bash
# Create a fresh GitHub repo (vm-coderock/VM2-P-Taskers)
git init
# Restore files from Dropbox / local backup
cp -r ~/Dropbox/VM2-main-folder/VM2-P/* .
git add .
git commit -m "Disaster recovery — restoring from Dropbox backup"
git remote add origin https://github.com/vm-coderock/VM2-P-Taskers.git
git push -u origin main
```

Then proceed to §7 to redeploy Railway services.

### What you'll lose
- Git history (only if Dropbox is the source — no version control there)
- Honcho memory and cron schedules need to be reconfigured manually
- Any deliverables that were never backed up to Dropbox

### Prevention
- Nightly Dropbox sync of every deliverable — already in cron schedule
- Monthly Dropbox integrity check — already in cron schedule
- Consider GitHub repo backup to a second host (e.g., GitLab mirror) for true redundancy

---

## 9. P3: A cron stopped firing

**Symptom**: expected daily/weekly deliverable didn't appear.

```bash
# In Perplexity Computer (any session):
#   "list crons"
#   - Verify the expected cron is still active
#   - Check last_run timestamp — if older than expected, cron is stuck

# Common causes:
#   - Cron was system-cancelled (Perplexity-side); recreate from scratch
#   - Skill referenced no longer loads; re-save the skill
#   - Connector OAuth expired (Gmail, Todoist, etc.); re-authenticate

# Recreate a cron:
#   Use `schedule_cron` with action=create, providing the cron_expression and task text.
#   Honcho memory contains the full task text for every cron — search for the cron name.
```

The full set of crons should always include:
1. Gmail Task Intake (M-F business hours)
2. Nightly Compliance Audit (every other day, 2 AM UTC)
3. Daily Todoist Auto-Helper (daily, 11 AM UTC)
4. Weekly Digest & Git Tag (Saturdays, 12 PM UTC)
5. Monthly Dropbox Integrity Check (1st of month, 1 PM UTC)
6. CCC Cardio Tennis Check-In (Sundays, 12 PM UTC)
7. APFS/SAM monitoring (multiple)

If any are missing, search Honcho memory for "cron" + the name to recover full specs.

---

## 10. Validation checklist (run after any DR action)

Use this every time you change deployment, recover from disaster, or onboard a new instance:

```
☐ portal.html loads at the public URL with basic-auth
☐ At least one deliverable opens (e.g., /army-maps-bid-decision-2026-04-14.html)
☐ /api/health returns ok:true
☐ /api/projects returns ≥1 project
☐ /api/deliverables returns hundreds of files
☐ projects.html loads and shows project cards
☐ Promote button on any deliverable opens dropdown with project list
☐ python3 scripts/portal_lint.py exits 0
☐ vm2-tests.sh passes (21 of 21)
☐ A new cron-generated deliverable from today is in the index
☐ Dropbox backup folder has a copy of today's deliverables
```

If all 11 boxes are checked, the system is fully operational.

---

## 11. Escalation contacts

- **Repo owner**: VM-CodeRock (varun@changeis.com)
- **Railway**: support@railway.com
- **GitHub**: support@github.com
- **Perplexity Computer**: in-app feedback

---

## 12. Change log

| Date | What | Owner |
|---|---|---|
| 2026-03-25 | Migrated to Railway from GitHub Pages + StaticCrypt | Computer |
| 2026-04-30 | portal.html corruption fix + lint guard added | Computer |
| 2026-05-05 | Project Threads MVP shipped (helper, API, button, projects.html) | Computer |
| 2026-05-05 | Architecture + DR runbook written | Computer |
