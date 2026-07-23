FROM docker.io/library/python:3.13.5-slim-bookworm@sha256:4c2cf9917bd1cbacc5e9b07320025bdb7cdf2df7b0ceaccb55e9dd7e30987419

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --system --gid 10001 rollup \
    && useradd --system --uid 10001 --gid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin rollup

WORKDIR /app
COPY rollup/requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir --require-hashes --requirement /app/requirements.txt

COPY rollup/live_rollup.py rollup/codex_live_rollup.py rollup/healthcheck.py /app/

USER 10001:10001
ENTRYPOINT ["python", "/app/live_rollup.py"]
