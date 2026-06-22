FROM python:3.13-slim

# Don't write .pyc files; flush logs immediately
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install deps first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App source
COPY . .

EXPOSE 8000

# Apply DB migrations, then serve with Gunicorn managing Uvicorn workers.
# $PORT is honored by most platforms (Render/Railway/Cloud Run); defaults to 8000.
CMD alembic upgrade head && \
    gunicorn main:app \
        --worker-class uvicorn.workers.UvicornWorker \
        --workers ${WEB_CONCURRENCY:-2} \
        --bind 0.0.0.0:${PORT:-8000} \
        --timeout 60
