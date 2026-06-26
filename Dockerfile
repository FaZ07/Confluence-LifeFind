FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Persist cases to a writable volume (cases survive restarts + shareable links).
ENV LIFELINE_DB=/data/lifefind.db
RUN mkdir -p /data
VOLUME /data

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
