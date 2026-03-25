#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# VM2 System Test Suite
# Validates all invariants of the VM2 automated task pipeline.
# Run: bash vm2-tests.sh [--repo-dir /path/to/VM2-P-Taskers]
# ═══════════════════════════════════════════════════════════════════

set -uo pipefail

# ── Configuration ──
REPO_DIR="${1:-/home/user/workspace/VM2-P-Taskers}"
PASS=0
FAIL=0
WARN=0
ERRORS=""

# Colors (if terminal supports them)
if [[ -t 1 ]]; then
    GREEN='\033[0;32m'
    RED='\033[0;31m'
    YELLOW='\033[0;33m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    NC='\033[0m'
else
    GREEN='' RED='' YELLOW='' CYAN='' BOLD='' NC=''
fi

# ── Test Runner ──
pass() {
    echo -e "  ${GREEN}✓ PASS${NC}  $1"
    PASS=$((PASS + 1))
}

fail() {
    echo -e "  ${RED}✗ FAIL${NC}  $1"
    ERRORS="${ERRORS}\n  - $1: $2"
    FAIL=$((FAIL + 1))
}

warn() {
    echo -e "  ${YELLOW}⚠ WARN${NC}  $1"
    WARN=$((WARN + 1))
}

section() {
    echo ""
    echo -e "${CYAN}${BOLD}── $1 ──${NC}"
}

# ═══════════════════════════════════════════════════════════════════
section "1. ENCRYPTION CHECKS"
# ═══════════════════════════════════════════════════════════════════

# Test 1.1: No StaticCrypt remnants
# NOTE: We check for 'class="staticrypt-html"' in the <html> tag, not just
# the string anywhere in the file. Compliance audits and architecture docs
# may legitimately reference the term in body text.
echo "  Checking for StaticCrypt encryption..."
ENCRYPTED=$(grep -rl 'class="staticrypt-html"' "${REPO_DIR}"/*.html 2>/dev/null || true)
if [[ -z "$ENCRYPTED" ]]; then
    pass "No StaticCrypt-encrypted files found"
else
    COUNT=$(echo "$ENCRYPTED" | wc -l)
    fail "Found $COUNT encrypted file(s)" "$ENCRYPTED"
fi

# Test 1.2: All HTML files start with <!DOCTYPE or <!doctype (case-insensitive)
echo "  Checking DOCTYPE declarations..."
BAD_DOCTYPE=""
for f in "${REPO_DIR}"/*.html; do
    FIRST=$(head -c 15 "$f" 2>/dev/null | tr '[:upper:]' '[:lower:]')
    if [[ "$FIRST" != "<!doctype html>"* ]]; then
        BAD_DOCTYPE="${BAD_DOCTYPE}$(basename "$f") "
    fi
done
if [[ -z "$BAD_DOCTYPE" ]]; then
    pass "All HTML files start with <!DOCTYPE html>"
else
    fail "Files missing DOCTYPE" "$BAD_DOCTYPE"
fi

# ═══════════════════════════════════════════════════════════════════
section "2. INDEX INTEGRITY"
# ═══════════════════════════════════════════════════════════════════

INDEX_FILE="${REPO_DIR}/index.html"

# Test 2.1: index.html exists
if [[ -f "$INDEX_FILE" ]]; then
    pass "index.html exists"
else
    fail "index.html not found" "Expected at ${INDEX_FILE}"
fi

# Test 2.2: Every deliverable HTML file has an index entry
echo "  Cross-referencing files with index entries..."
MISSING_FROM_INDEX=""
DELIVERABLE_COUNT=0
for f in "${REPO_DIR}"/*.html; do
    BASENAME=$(basename "$f")
    # Skip index and kanban
    [[ "$BASENAME" == "index.html" ]] && continue
    [[ "$BASENAME" == "kanban.html" ]] && continue
    ((DELIVERABLE_COUNT++))
    if ! grep -q "href=\"${BASENAME}\"" "$INDEX_FILE" 2>/dev/null; then
        MISSING_FROM_INDEX="${MISSING_FROM_INDEX}${BASENAME} "
    fi
done

if [[ -z "$MISSING_FROM_INDEX" ]]; then
    pass "All $DELIVERABLE_COUNT deliverables have index entries"
else
    MISSING_COUNT=$(echo "$MISSING_FROM_INDEX" | wc -w)
    fail "$MISSING_COUNT file(s) missing from index" "$MISSING_FROM_INDEX"
fi

# Test 2.3: Index row count matches file count
INDEX_ROWS=$(grep -c '<tr data-type' "$INDEX_FILE" 2>/dev/null || echo "0")
if [[ "$INDEX_ROWS" -eq "$DELIVERABLE_COUNT" ]]; then
    pass "Index row count ($INDEX_ROWS) matches deliverable count ($DELIVERABLE_COUNT)"
else
    fail "Index rows ($INDEX_ROWS) != file count ($DELIVERABLE_COUNT)" "Rebuild index with build_index.py"
fi

# Test 2.4: Index contains valid HTML structure
if grep -q '<table class="deliverables-table"' "$INDEX_FILE" 2>/dev/null; then
    pass "Index has valid table structure"
else
    fail "Index missing deliverables table" "Index may be corrupted"
fi

# ═══════════════════════════════════════════════════════════════════
section "3. FILE INTEGRITY"
# ═══════════════════════════════════════════════════════════════════

# Test 3.1: No empty HTML files
echo "  Checking for empty files..."
EMPTY_FILES=""
for f in "${REPO_DIR}"/*.html; do
    SIZE=$(stat -f%z "$f" 2>/dev/null || stat -c%s "$f" 2>/dev/null || echo "0")
    if [[ "$SIZE" -lt 100 ]]; then
        EMPTY_FILES="${EMPTY_FILES}$(basename "$f") "
    fi
done
if [[ -z "$EMPTY_FILES" ]]; then
    pass "No empty or near-empty HTML files"
else
    fail "Empty/tiny files found" "$EMPTY_FILES"
fi

# Test 3.2: All files are valid UTF-8
echo "  Checking UTF-8 encoding..."
BAD_ENCODING=""
for f in "${REPO_DIR}"/*.html; do
    if ! iconv -f UTF-8 -t UTF-8 "$f" > /dev/null 2>&1; then
        BAD_ENCODING="${BAD_ENCODING}$(basename "$f") "
    fi
done
if [[ -z "$BAD_ENCODING" ]]; then
    pass "All HTML files are valid UTF-8"
else
    fail "Invalid UTF-8 encoding" "$BAD_ENCODING"
fi

# Test 3.3: No binary padding (StaticCrypt artifact)
echo "  Checking for binary padding artifacts..."
BINARY_PAD=""
for f in "${REPO_DIR}"/*.html; do
    # Check if first bytes are non-printable (binary padding from old encryption)
    FIRST_BYTE=$(xxd -l 1 -p "$f" 2>/dev/null)
    # Valid HTML starts with '<' which is 3c in hex
    if [[ -n "$FIRST_BYTE" && "$FIRST_BYTE" != "3c" && "$FIRST_BYTE" != "0a" && "$FIRST_BYTE" != "ef" ]]; then
        BINARY_PAD="${BINARY_PAD}$(basename "$f")(0x${FIRST_BYTE}) "
    fi
done
if [[ -z "$BINARY_PAD" ]]; then
    pass "No binary padding artifacts detected"
else
    fail "Binary padding found in files" "$BINARY_PAD"
fi

# ═══════════════════════════════════════════════════════════════════
section "4. RAILWAY CONFIGURATION"
# ═══════════════════════════════════════════════════════════════════

# Test 4.1: Dockerfile exists and is valid
DOCKERFILE="${REPO_DIR}/Dockerfile"
if [[ -f "$DOCKERFILE" ]]; then
    if grep -q 'FROM nginx:alpine' "$DOCKERFILE" && \
       grep -q 'EXPOSE 8080' "$DOCKERFILE" && \
       grep -q 'ENTRYPOINT' "$DOCKERFILE"; then
        pass "Dockerfile exists with correct base image, port, and entrypoint"
    else
        fail "Dockerfile incomplete" "Missing nginx:alpine, EXPOSE 8080, or ENTRYPOINT"
    fi
else
    fail "Dockerfile not found" "Expected at ${DOCKERFILE}"
fi

# Test 4.2: nginx.conf exists and has auth
NGINX_CONF="${REPO_DIR}/nginx.conf"
if [[ -f "$NGINX_CONF" ]]; then
    if grep -q 'auth_basic' "$NGINX_CONF" && \
       grep -q 'auth_basic_user_file' "$NGINX_CONF" && \
       grep -q 'listen 8080' "$NGINX_CONF"; then
        pass "nginx.conf has auth_basic, user_file, and port 8080"
    else
        fail "nginx.conf incomplete" "Missing auth_basic, user_file, or listen directive"
    fi
else
    fail "nginx.conf not found" "Expected at ${NGINX_CONF}"
fi

# Test 4.3: entrypoint.sh exists and generates htpasswd
ENTRYPOINT="${REPO_DIR}/entrypoint.sh"
if [[ -f "$ENTRYPOINT" ]]; then
    if grep -q 'VM2_AUTH_PASSWORD' "$ENTRYPOINT" && \
       grep -q 'htpasswd' "$ENTRYPOINT" && \
       grep -q 'nginx' "$ENTRYPOINT"; then
        pass "entrypoint.sh reads env vars, generates htpasswd, starts nginx"
    else
        fail "entrypoint.sh incomplete" "Missing password var, htpasswd gen, or nginx start"
    fi
else
    fail "entrypoint.sh not found" "Expected at ${ENTRYPOINT}"
fi

# Test 4.4: Dockerfile excludes sensitive files from html dir
# The rm command may span multiple lines with backslash continuations
DOCKERFILE_CONTENT=$(cat "$DOCKERFILE")
if echo "$DOCKERFILE_CONTENT" | grep -q 'Dockerfile' && \
   echo "$DOCKERFILE_CONTENT" | grep -q 'nginx.conf' && \
   echo "$DOCKERFILE_CONTENT" | grep -q 'entrypoint.sh'; then
    pass "Dockerfile references cleanup of config files from html directory"
else
    warn "Dockerfile may serve config files publicly — check rm -f lines"
fi

# Test 4.5: Security headers present
if grep -q 'X-Content-Type-Options' "$NGINX_CONF" && \
   grep -q 'X-Frame-Options' "$NGINX_CONF"; then
    pass "nginx.conf includes security headers"
else
    warn "Missing security headers in nginx.conf"
fi

# Test 4.6: Gzip enabled
if grep -q 'gzip on' "$NGINX_CONF"; then
    pass "Gzip compression enabled"
else
    warn "Gzip not enabled in nginx.conf"
fi

# ═══════════════════════════════════════════════════════════════════
section "5. NAMING CONVENTIONS"
# ═══════════════════════════════════════════════════════════════════

# Test 5.1: All deliverable files follow slug-YYYY-MM-DD.html pattern
echo "  Checking filename conventions..."
BAD_NAMES=""
for f in "${REPO_DIR}"/*.html; do
    BASENAME=$(basename "$f")
    [[ "$BASENAME" == "index.html" ]] && continue
    [[ "$BASENAME" == "kanban.html" ]] && continue
    # Must match: lowercase-slug-YYYY-MM-DD.html
    if ! echo "$BASENAME" | grep -qP '^[a-z0-9][-a-z0-9]*-\d{4}-\d{2}-\d{2}\.html$'; then
        BAD_NAMES="${BAD_NAMES}${BASENAME} "
    fi
done
if [[ -z "$BAD_NAMES" ]]; then
    pass "All filenames follow slug-YYYY-MM-DD.html convention"
else
    BADCOUNT=$(echo "$BAD_NAMES" | wc -w)
    warn "$BADCOUNT file(s) don't match strict naming pattern: $BAD_NAMES"
fi

# Test 5.2: No spaces or uppercase in filenames
BAD_CHARS=""
for f in "${REPO_DIR}"/*.html; do
    BASENAME=$(basename "$f")
    if echo "$BASENAME" | grep -qP '[A-Z ]'; then
        BAD_CHARS="${BAD_CHARS}${BASENAME} "
    fi
done
if [[ -z "$BAD_CHARS" ]]; then
    pass "No uppercase letters or spaces in filenames"
else
    fail "Filenames with uppercase or spaces" "$BAD_CHARS"
fi

# ═══════════════════════════════════════════════════════════════════
section "6. BRAND STYLE COMPLIANCE (SPOT CHECK)"
# ═══════════════════════════════════════════════════════════════════

# Test 6.1: Spot-check 5 random deliverables for VM2 brand markers
echo "  Spot-checking deliverables for brand consistency..."
BRAND_ISSUES=""
# Get 5 random deliverable files (not index/kanban)
SAMPLE_FILES=$(ls "${REPO_DIR}"/*.html | grep -v 'index.html' | grep -v 'kanban.html' | shuf -n 5 2>/dev/null || ls "${REPO_DIR}"/*.html | grep -v 'index.html' | grep -v 'kanban.html' | head -5)
for f in $SAMPLE_FILES; do
    BN=$(basename "$f")
    # Check for theme toggle or dark mode support
    HAS_THEME=$(grep -c -E 'data-theme|theme-toggle|toggleTheme' "$f" 2>/dev/null | tr -d '[:space:]' || echo "0")
    if [[ "$HAS_THEME" -lt 1 ]]; then
        BRAND_ISSUES="${BRAND_ISSUES}${BN}(no-theme-toggle) "
    fi
done
if [[ -z "$BRAND_ISSUES" ]]; then
    pass "Spot-checked 5 files: all have theme toggle / dark mode"
else
    warn "Brand style issues: $BRAND_ISSUES"
fi

# Test 6.2: Check for accent color in sample files
ACCENT_ISSUES=""
for f in $SAMPLE_FILES; do
    BN=$(basename "$f")
    HAS_ACCENT=$(grep -ci 'c53a3a' "$f" 2>/dev/null | tr -d '[:space:]' || echo "0")
    if [[ "$HAS_ACCENT" -lt 1 ]]; then
        ACCENT_ISSUES="${ACCENT_ISSUES}${BN} "
    fi
done
if [[ -z "$ACCENT_ISSUES" ]]; then
    pass "Spot-checked 5 files: all use #c53a3a accent color"
else
    warn "Files missing accent color: $ACCENT_ISSUES"
fi

# ═══════════════════════════════════════════════════════════════════
section "7. GIT REPOSITORY HEALTH"
# ═══════════════════════════════════════════════════════════════════

# Test 7.1: Clean working tree (no uncommitted changes)
cd "$REPO_DIR"
DIRTY=$(git status --porcelain 2>/dev/null | head -5)
if [[ -z "$DIRTY" ]]; then
    pass "Git working tree is clean"
else
    warn "Uncommitted changes detected: $(echo "$DIRTY" | wc -l) file(s)"
fi

# Test 7.2: On main branch
BRANCH=$(git branch --show-current 2>/dev/null)
if [[ "$BRANCH" == "main" ]]; then
    pass "On main branch"
else
    fail "Not on main branch" "Currently on: $BRANCH"
fi

# Test 7.3: Remote is set correctly
REMOTE=$(git remote get-url origin 2>/dev/null || echo "none")
if echo "$REMOTE" | grep -qi 'VM-CodeRock/VM2-P-Taskers\|vm-coderock/vm2-p-taskers'; then
    pass "Remote origin points to VM-CodeRock/VM2-P-Taskers"
else
    fail "Remote origin incorrect" "$REMOTE"
fi

# ═══════════════════════════════════════════════════════════════════
section "8. RAILWAY HEALTH CHECK"
# ═══════════════════════════════════════════════════════════════════

# Test 8.1: Check if Railway URL responds (requires curl)
# This test is best-effort — may fail in sandboxed environments
echo "  Attempting Railway health check (may skip if no network)..."
RAILWAY_URL="${RAILWAY_URL:-}"
if [[ -n "$RAILWAY_URL" ]]; then
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$RAILWAY_URL" 2>/dev/null || echo "000")
    if [[ "$HTTP_CODE" == "401" ]]; then
        pass "Railway responds with 401 (auth required) — correct behavior"
    elif [[ "$HTTP_CODE" == "200" ]]; then
        warn "Railway responds 200 without auth — check auth_basic config"
    elif [[ "$HTTP_CODE" == "000" ]]; then
        warn "Could not reach Railway URL (network restricted or URL not set)"
    else
        warn "Railway returned HTTP $HTTP_CODE"
    fi
else
    warn "RAILWAY_URL not set — skipping health check. Set env var to enable."
fi


# ═══════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════

echo ""
echo -e "${BOLD}═══════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  TEST SUMMARY${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════════════${NC}"
echo ""
TOTAL=$((PASS + FAIL + WARN))
echo -e "  ${GREEN}Passed:${NC}   $PASS"
echo -e "  ${RED}Failed:${NC}   $FAIL"
echo -e "  ${YELLOW}Warnings:${NC} $WARN"
echo -e "  Total:    $TOTAL"
echo ""

if [[ "$FAIL" -eq 0 ]]; then
    echo -e "  ${GREEN}${BOLD}✓ ALL TESTS PASSED${NC}"
    echo ""
    exit 0
else
    echo -e "  ${RED}${BOLD}✗ $FAIL TEST(S) FAILED${NC}"
    echo -e "  ${RED}Failures:${ERRORS}${NC}"
    echo ""
    exit 1
fi
