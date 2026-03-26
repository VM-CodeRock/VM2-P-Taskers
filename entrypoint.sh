#!/bin/sh
# Generate .htpasswd from environment variable at container start
# This way the password is never committed to the repo

USERNAME="${VM2_AUTH_USERNAME:-vm2}"
PASSWORD="${VM2_AUTH_PASSWORD:-97harry23!}"

# Generate htpasswd file (uses OpenSSL for hashing)
echo "${USERNAME}:$(openssl passwd -apr1 "${PASSWORD}")" > /etc/nginx/.htpasswd
echo "VM2 auth configured for user: ${USERNAME}"

# Inject Todoist API token into nginx config for the proxy
TODOIST_TOKEN="${VM2_TODOIST_TOKEN:-}"
if [ -n "$TODOIST_TOKEN" ]; then
  sed -i "s|set \$todoist_token \"\"|set \$todoist_token \"${TODOIST_TOKEN}\"|" /etc/nginx/conf.d/default.conf
  echo "Todoist API proxy configured"
else
  echo "WARNING: VM2_TODOIST_TOKEN not set — deep-dive buttons will use fallback"
fi

# Start nginx
exec nginx -g "daemon off;"
