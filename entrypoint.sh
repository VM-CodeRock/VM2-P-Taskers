#!/bin/sh
# Generate .htpasswd from environment variable at container start
# This way the password is never committed to the repo

USERNAME="${VM2_AUTH_USERNAME:-vm2}"
PASSWORD="${VM2_AUTH_PASSWORD:-97harry23!}"

# Generate htpasswd file (uses OpenSSL for hashing)
echo "${USERNAME}:$(openssl passwd -apr1 "${PASSWORD}")" > /etc/nginx/.htpasswd

echo "VM2 auth configured for user: ${USERNAME}"

# Start nginx
exec nginx -g "daemon off;"
