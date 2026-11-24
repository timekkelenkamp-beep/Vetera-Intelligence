# Vetera Intelligence – image voor online hosting (bijv. Render).
# Stap 1: interface bouwen
FROM node:20-bookworm-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npx tsc -b && npx vite build

# Stap 2: server
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    VETERA_DATA_DIR=/data VETERA_ALLOW_REMOTE_ACCESS=true VETERA_AUTO_MONITOR=true
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt
COPY backend/ ./
COPY --from=frontend /src/frontend/dist /app/frontend/dist
RUN useradd --create-home --uid 10001 vetera && mkdir -p /data && chown vetera:vetera /data
USER vetera
EXPOSE 10000
# Render geeft de poort mee in $PORT; --proxy-headers zodat het echte IP-adres (inlogbeperking) bekend is.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000} --proxy-headers --forwarded-allow-ips='*'"]
