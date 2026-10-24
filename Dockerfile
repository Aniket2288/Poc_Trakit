FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /code

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app

RUN useradd --create-home appuser && mkdir -p /code/uploads && chown appuser /code/uploads
USER appuser

EXPOSE 8000

# --proxy-headers: behind Nginx, trust X-Forwarded-For so rate limiting sees the real client IP, not Nginx's.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
