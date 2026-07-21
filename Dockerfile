FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p exports app/logs

COPY start.sh .
RUN chmod +x start.sh

# Render provides $PORT at runtime
EXPOSE 8000
CMD ["./start.sh"]