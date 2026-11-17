# syntax=docker/dockerfile:1
FROM python:3.15-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip wheel --wheel-dir /wheels .

FROM python:3.15-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MPLCONFIGDIR=/tmp/mpl
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin reporter \
 && mkdir -p /app/data/input /app/data/output /app/data/audit /app/config \
 && chown -R reporter /app/data
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links /wheels excel-reporting && rm -rf /wheels
WORKDIR /app
USER 10001
# Run with: --read-only --cap-drop ALL --security-opt no-new-privileges --network none
# and mount config (ro), input (ro), output + audit (rw).
ENTRYPOINT ["excel-reporting"]
CMD ["--help"]
