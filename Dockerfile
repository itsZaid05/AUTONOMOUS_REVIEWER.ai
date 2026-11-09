# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends libreoffice-writer libpango-1.0-0 libpangoft2-1.0-0 fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace/AUTONOMOUS_REVIEWER.ai
COPY requirements.txt .
RUN --mount=type=secret,id=proxy_ca PIP_CERT=/run/secrets/proxy_ca sh -c 'if [ -f /run/secrets/proxy_ca ]; then pip install --no-cache-dir -r requirements.txt; else unset PIP_CERT; pip install --no-cache-dir -r requirements.txt; fi'
COPY . .
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
