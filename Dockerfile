FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

# LibreOffice (faqat kerakli qismlari) + o'zbek/rus/ingliz matnlari uchun shriftlar.
# Carlito/Caladea = Calibri/Cambria bilan bir xil o'lchamli shriftlar (Word sahifalari siljimasligi uchun).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-core libreoffice-writer libreoffice-impress \
        fonts-dejavu fonts-liberation fonts-noto-core \
        fonts-crosextra-carlito fonts-crosextra-caladea \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Oddiy (root bo'lmagan) foydalanuvchi bilan ishlaymiz
RUN useradd -m -u 1000 botuser \
    && mkdir -p /app/logs \
    && chown -R botuser:botuser /app
USER botuser

ENV HOME=/home/botuser \
    SOFFICE_PATH=soffice \
    TEMP_DIR=/tmp

CMD ["python", "bot.py"]
