FROM python:3.11-slim

WORKDIR /app

# Install FFmpeg and system fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-dejavu-core \
    cron \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Setup cron entry inside container
RUN echo "0 8 * * * cd /app && python run.py autopilot --count 5 --niche space --schedule >> /app/output/cron.log 2>&1" > /etc/cron.d/autotube-cron \
    && chmod 0644 /etc/cron.d/autotube-cron \
    && crontab /etc/cron.d/autotube-cron

CMD ["cron", "-f"]
