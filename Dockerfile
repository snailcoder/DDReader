FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY schema.json ./schema.json

EXPOSE 8001

ENV DRDD_BASE_DIR=/data/drdd
ENV DRDD_TASKS_DIR=/data/drdd/tasks
ENV MINERU_API_URL=http://mineru-api:8000

CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8001"]
