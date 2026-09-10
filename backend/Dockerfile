# Dockerfile — backend, with OCR support.
#
# Render's native Python runtime doesn't give you apt-get access, so
# tesseract-ocr (needed by pytesseract) and poppler-utils (needed by
# pdf2image — it shells out to pdftoppm/pdftocairo) can never be installed
# there. That's the actual, root cause of "OCR unavailable" in your logs —
# not a bug in the Python code, which already has full OCR logic ready to
# run the moment these two system packages exist.
#
# Switching the Render service to a Docker runtime (instructions below)
# is the only way to get real system packages installed.

FROM python:3.12-slim

# System dependencies: tesseract for OCR text recognition, poppler-utils
# for pdf2image's page-rasterization step, plus the usual PDF/image libs.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x docker-entrypoint.sh

# Render sets $PORT at runtime; default to 8000 for local `docker run`.
ENV PORT=8000
EXPOSE 8000

CMD ["./docker-entrypoint.sh"]
