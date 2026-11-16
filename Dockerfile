FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN pip install --no-cache-dir boto3 psycopg2-binary
COPY worker.py .
CMD ["python", "-u", "worker.py"]
