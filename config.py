"""Sozlamalarni .env faylidan (yoki hosting muhit o'zgaruvchilaridan) o'qish."""
from __future__ import annotations

import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _get_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise SystemExit(f"XATO: .env faylida {name} butun son bo'lishi kerak (hozir: {raw!r}).")
    return max(value, minimum)


def find_soffice() -> str:
    """LibreOffice (soffice) dasturining yo'lini topadi. Topilmasa bo'sh qator qaytaradi."""
    custom = os.getenv("SOFFICE_PATH", "").strip().strip('"')
    if custom:
        if Path(custom).is_file() or shutil.which(custom):
            return custom
        raise SystemExit(f"XATO: SOFFICE_PATH da ko'rsatilgan fayl topilmadi: {custom}")

    for name in ("soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            return found

    for candidate in (
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ):
        if Path(candidate).is_file():
            return candidate
    return ""


@dataclass(frozen=True)
class Settings:
    bot_token: str
    mode: str                # "polling" yoki "webhook"
    webhook_url: str
    webhook_secret: str
    port: int
    max_file_mb: int
    max_images: int
    convert_timeout: int     # soniya
    max_parallel: int
    session_ttl_min: int
    temp_dir: Path
    log_dir: Path
    soffice_path: str
    pdf_export: str          # "lossless" | "quality" | "default"

    @property
    def max_file_bytes(self) -> int:
        return self.max_file_mb * 1024 * 1024


def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token or not re.fullmatch(r"\d{5,}:[A-Za-z0-9_-]{20,}", token):
        raise SystemExit(
            "XATO: BOT_TOKEN topilmadi yoki noto'g'ri.\n"
            ".env faylini oching va BOT_TOKEN=... qatoriga @BotFather bergan tokenni yozing."
        )

    mode = os.getenv("BOT_MODE", "polling").strip().lower()
    if mode not in ("polling", "webhook"):
        raise SystemExit("XATO: BOT_MODE faqat 'polling' yoki 'webhook' bo'lishi mumkin.")

    webhook_url = os.getenv("WEBHOOK_URL", "").strip().rstrip("/")
    if mode == "webhook" and not webhook_url.startswith("https://"):
        raise SystemExit("XATO: webhook rejimida WEBHOOK_URL https:// bilan boshlanishi kerak.")

    secret = os.getenv("WEBHOOK_SECRET", "").strip()
    if secret and not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", secret):
        raise SystemExit("XATO: WEBHOOK_SECRET faqat harf, raqam, _ va - dan iborat bo'lishi kerak.")

    pdf_export = os.getenv("PDF_IMAGE_EXPORT", "lossless").strip().lower()
    if pdf_export not in ("lossless", "quality", "default"):
        raise SystemExit("XATO: PDF_IMAGE_EXPORT: lossless, quality yoki default bo'lishi kerak.")

    base_tmp = Path(os.getenv("TEMP_DIR", "").strip() or tempfile.gettempdir())
    log_dir = Path(os.getenv("LOG_DIR", "").strip() or (BASE_DIR / "logs"))

    return Settings(
        bot_token=token,
        mode=mode,
        webhook_url=webhook_url,
        webhook_secret=secret,
        port=_get_int("PORT", 8080),
        max_file_mb=min(_get_int("MAX_FILE_MB", 20), 20),  # Telegram bot yuklab olish chegarasi 20 MB
        max_images=_get_int("MAX_IMAGES", 30),
        convert_timeout=_get_int("CONVERT_TIMEOUT", 180, minimum=20),
        max_parallel=_get_int("MAX_PARALLEL", 2),
        session_ttl_min=_get_int("SESSION_TTL_MIN", 30),
        # Faqat shu maxsus papka ichidagi narsalar o'chiriladi
        temp_dir=base_tmp / "pdf_bot_tmp",
        log_dir=log_dir,
        soffice_path=find_soffice(),
        pdf_export=pdf_export,
    )
