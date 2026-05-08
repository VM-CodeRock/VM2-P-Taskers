#!/bin/sh
# generate_share_key.sh — Generate a strong magic-link key for VM2_PUBLIC_KEYS.
#
# Usage:
#   ./scripts/generate_share_key.sh         # one key
#   ./scripts/generate_share_key.sh 3       # three keys
#
# Output: tagged with today's date prefix for easy rotation tracking.
# Format: k-YYMMDD-<22 chars of base62 randomness>
#
# Treat output like a password. Add to Railway env var VM2_PUBLIC_KEYS
# (comma-separated, keep 1-2 previous keys for grace window).

count="${1:-1}"
i=0
while [ "$i" -lt "$count" ]; do
  date_tag=$(date +%y%m%d)
  rand=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | cut -c1-22)
  printf 'k-%s-%s\n' "$date_tag" "$rand"
  i=$((i + 1))
done
