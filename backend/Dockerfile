FROM python:3.11-slim

WORKDIR /app

ARG INSTALL_EXTRAS=

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc default-libmysqlclient-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY config ./config
COPY app ./app
COPY scripts ./scripts

RUN if [ -n "$INSTALL_EXTRAS" ]; then \
      pip install --no-cache-dir -e ".[${INSTALL_EXTRAS}]"; \
    else \
      pip install --no-cache-dir -e .; \
    fi

ENV APP_ENV=production
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
