FROM python:3.15-alpine AS base
# proxy build args (HTTP_PROXY etc.) are predefined: used by RUN, not kept in the image
RUN apk add --no-cache git docker-cli docker-cli-buildx
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/alembic.ini .
COPY backend/alembic alembic
COPY backend/app app
COPY templates/ /app/templates/

FROM base AS test
COPY backend/requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY backend/tests tests

FROM base AS runtime
EXPOSE 8000
# one worker: the import preview (Task 7) lives in process memory
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1"]
