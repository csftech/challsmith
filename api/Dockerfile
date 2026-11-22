FROM python:3.15-alpine AS base
# proxy build args (HTTP_PROXY etc.) are predefined: used by RUN, not kept in the image
RUN apk add --no-cache git docker-cli docker-cli-buildx
WORKDIR /app
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY api/alembic.ini .
COPY api/alembic alembic
COPY api/challsmith_api challsmith_api
COPY templates/ /app/templates/

FROM base AS test
COPY api/requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY api/tests tests

FROM base AS runtime
EXPOSE 8000
# one worker: the import preview (Task 7) lives in process memory
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn challsmith_api.main:app --host 0.0.0.0 --port 8000 --workers 1"]
