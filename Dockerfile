FROM python:3.11-slim

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p code-indexer

EXPOSE 7860

WORKDIR /app/code-indexer

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "7860"]