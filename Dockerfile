# visual-studio - constrained e-commerce visual asset generation service.
# The default wiring uses the fully-functional MockProvider, so this image runs
# with no GPU and no external network. Real Seedream / GPT-Image adapters are
# structured stubs (raise NotImplementedError) and are wired via env vars.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    VISUAL_DB_PATH=/data/visual_studio.db \
    VISUAL_OUTPUT_DIR=/data/outputs \
    VISUAL_PROVIDER=mock \
    VISUAL_HOST=0.0.0.0 \
    VISUAL_PORT=8011

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Persist generated artifacts and the SQLite db outside the image.
RUN mkdir -p /data/outputs
VOLUME ["/data"]

EXPOSE 8011

CMD ["python", "-m", "visual_studio"]
