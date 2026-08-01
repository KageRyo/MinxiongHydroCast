FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN python -m pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 mhc \
    && mkdir -p /var/lib/minxiong-hydrocast \
    && chown -R mhc:mhc /var/lib/minxiong-hydrocast

USER mhc
VOLUME ["/var/lib/minxiong-hydrocast"]
EXPOSE 8080

ENTRYPOINT ["mhc"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8080"]

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2)"]
