# Separate verifier image (Harbor [verifier] environment_mode = "separate").
# The interactive agent process never runs in this container. Its /app artifact is
# restored here and necessarily executed for tests, so that code is dropped to a
# dedicated unprivileged UID while the verifier, oracle, and /tests remain root-only.
# Harbor builds this with tests/ as the build context and does NOT upload tests/ for a
# custom verifier image, so the tests are baked in here.
FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
RUN pip install --no-cache-dir pytest==8.4.1 iniconfig==2.3.0 packaging==26.3 pluggy==1.6.0 pygments==2.21.0
COPY . /tests/
RUN groupadd --gid 10001 verifier-task \
    && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /nonexistent \
        --shell /usr/sbin/nologin verifier-task \
    && groupadd --gid 10002 verifier-meter \
    && useradd --uid 10002 --gid 10002 --no-create-home --home-dir /nonexistent \
        --shell /usr/sbin/nologin verifier-meter \
    && groupadd --gid 10003 verifier-baseline \
    && useradd --uid 10003 --gid 10003 --no-create-home --home-dir /nonexistent \
        --shell /usr/sbin/nologin verifier-baseline \
    && find /tests -type d -exec chmod 0700 {} + \
    && find /tests -type f -exec chmod 0600 {} + \
    && chmod 0700 /tests/test.sh \
    && mkdir -p /app /logs/verifier \
    && chown root:root /app /logs/verifier \
    && chmod 0700 /app /logs/verifier \
    && chown root:root /tmp /var/tmp \
    && chmod 0711 /tmp /var/tmp
WORKDIR /app
