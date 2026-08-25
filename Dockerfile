# Cookie Vault - 自托管多平台 Cookie 保险库
# 基于 Playwright 官方镜像（自带 Chromium）
FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy

WORKDIR /app

# 系统依赖（playwright 镜像已含大部分）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/main.py /app/main.py
COPY frontend /app/static

ENV DATA_DIR=/data
ENV STATIC_DIR=/app/static
ENV PYTHONUNBUFFERED=1

EXPOSE 8101
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8101"]
