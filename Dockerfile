FROM python:3.12-slim

# Install ffmpeg system-wide
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create downloads directory
RUN mkdir -p downloads

EXPOSE 10000

CMD gunicorn --bind 0.0.0.0:${PORT:-10000} --workers 2 --threads 4 --timeout 300 app:app
