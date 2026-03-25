FROM nginx:alpine

# Install openssl for htpasswd generation
RUN apk add --no-cache openssl

# Copy nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Copy all site files
COPY . /usr/share/nginx/html/

# Clean up non-web files from html dir
RUN rm -f /usr/share/nginx/html/Dockerfile \
    /usr/share/nginx/html/nginx.conf \
    /usr/share/nginx/html/entrypoint.sh \
    /usr/share/nginx/html/.staticrypt.json \
    /usr/share/nginx/html/.gitignore

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
