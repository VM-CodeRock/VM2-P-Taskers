# VM2 Projects API — sidecar service
# Runs alongside the nginx static-file server. nginx proxies /api/* here.
FROM python:3.12-slim

# Install git (needed to commit/push from the API)
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps
COPY api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Application code
COPY api/projects_api.py /app/projects_api.py
COPY api/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# The repo will be cloned at runtime by entrypoint.sh into /repo (so the
# image stays decoupled from any single repo state). project_helper.py
# gets imported from /repo/scripts/.
ENV REPO_PATH=/repo
# Railway provides PORT as an env var; default to 8000 for local dev
ENV PORT=8000

EXPOSE 8000

# entrypoint.sh handles repo clone/pull, then exec's the CMD.
# We use sh -c so $PORT (set by Railway) gets expanded at runtime.
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["sh", "-c", "uvicorn projects_api:app --host 0.0.0.0 --port ${PORT:-8000}"]
