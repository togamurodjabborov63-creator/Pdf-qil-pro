"""Konvertatsiya mantiqi: rasm -> PDF (img2pdf + Pillow) va Office -> PDF (LibreOffice)."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import signal
import subprocess
import unicodedata
import uuid
from pathlib import Path
from typing import Sequence

try:
    import pymupdf as fitz  # PyMuPDF (yangi nom)
except ImportError:  # eski versiyalar
    import fitz  # type: ignore
import img2pdf
from PIL import Image, ImageOps

log = logging.getLogger(__name__)


class ConversionError(Exception):
    """Foydalanuvchiga ko'rsatsa bo'ladigan xato."""

    def __init__(self, user_message: str):
        super().__init__(user_message)
        self.user_message = user_message


# ----------------------------------------------------------------- yordamchilar
def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{int(size)} B" if unit == "B" else f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} GB"


def safe_stem(filename: str, default: str = "hujjat") -> str:
    """Foydalanuvchi bergan fayl nomidan xavfsiz nom (kengaytmasiz) yasaydi."""
    stem = Path(filename or "").stem
    stem = unicodedata.normalize("NFC", stem)
    stem = re.sub(r"[^\w\s\-.()]", "", stem, flags=re.UNICODE)
    stem = re.sub(r"\s+", " ", stem).strip(" .")
    return stem[:80] or default


def validate_pdf(path: Path) -> None:
    """PDF mavjud, bo'sh emas va ochiladigan ekanini tekshiradi."""
    if not path.is_file() or path.stat().st_size == 0:
        raise ConversionError("PDF yaratilmadi (fayl bo'sh yoki topilmadi). Faylni tekshirib, qayta urinib ko'ring.")
    try:
        with fitz.open(path) as doc:
            if doc.page_count < 1:
                raise ConversionError("PDF bo'sh chiqdi (0 sahifa). Asl faylda ma'lumot bor-yo'qligini tekshiring.")
    except ConversionError:
        raise
    except Exception as exc:
        log.warning("PDF tekshiruvida xato: %s", exc)
        raise ConversionError("Yaratilgan PDF buzilgan. Faylni qayta yuborib ko'ring.") from exc


# ----------------------------------------------------------------- RASM -> PDF
def _prepare_image(src: Path, workdir: Path, idx: int) -> Path:
    """Rasmni img2pdf qabul qiladigan holatga keltiradi.

    JPEG va oddiy PNG fayllar O'ZGARTIRILMAY (qayta kodlanmasdan) PDFga qo'yiladi.
    Shaffof PNG oq fonga qo'yiladi, WEBP lossless PNG ga o'tkaziladi.
    """
    try:
        with Image.open(src) as im:
            fmt = (im.format or "").upper()
            mode = im.mode
            has_alpha = ("A" in mode) or ("transparency" in im.info)

            if fmt == "JPEG" and mode in ("RGB", "L", "CMYK"):
                return src
            if fmt == "PNG" and not has_alpha and mode in ("RGB", "L"):
                return src

            im.load()
            fixed = ImageOps.exif_transpose(im) or im
            if has_alpha:
                rgba = fixed.convert("RGBA")
                flat = Image.new("RGB", rgba.size, (255, 255, 255))
                flat.paste(rgba, mask=rgba.getchannel("A"))
                result = flat
            elif fixed.mode in ("RGB", "L"):
                result = fixed
            else:
                result = fixed.convert("RGB")

            dst = workdir / f"prepared_{idx:04d}.png"
            result.save(dst, format="PNG", compress_level=6)  # PNG = yo'qotishsiz
            return dst
    except Exception as exc:  # UnidentifiedImageError, DecompressionBombError, ...
        log.warning("Rasmni tayyorlashda xato (%s): %s", src.name, exc)
        raise ConversionError(f"{idx}-rasmni o'qib bo'lmadi. U buzilgan yoki juda katta bo'lishi mumkin.") from exc


def images_to_pdf(image_paths: Sequence[Path], out_path: Path, workdir: Path, layout: str = "original") -> None:
    """Rasmlarni bitta PDFga birlashtiradi (berilgan tartibda).

    layout="original" - har sahifa rasmning asl nisbatida;
    layout="a4"       - har sahifa A4, rasm sahifaga sig'diriladi (kichraytiriladi, kattalashtirilmaydi emas - nisbat saqlanadi).
    """
    if not image_paths:
        raise ConversionError("Rasm topilmadi.")

    prepared = [str(_prepare_image(p, workdir, i)) for i, p in enumerate(image_paths, 1)]

    kwargs = {}
    if layout == "a4":
        a4 = (img2pdf.mm_to_pt(210), img2pdf.mm_to_pt(297))
        kwargs["layout_fun"] = img2pdf.get_layout_fun(a4, fit=img2pdf.FitMode.into, auto_orient=True)

    try:
        data = img2pdf.convert(prepared, **kwargs)
    except Exception as exc:
        log.exception("img2pdf xatosi")
        raise ConversionError("Rasmlarni PDFga aylantirib bo'lmadi. Boshqa rasm bilan urinib ko'ring.") from exc

    out_path.write_bytes(data)
    validate_pdf(out_path)


# ----------------------------------------------------------------- OFFICE -> PDF
def _export_options(kind: str, mode: str) -> str:
    """LibreOffice PDF eksport filtri. Rasmlar siqilmaydi va piksellari kamaytirilmaydi."""
    if mode == "default":
        return "pdf"
    filter_name = "writer_pdf_Export" if kind == "word" else "impress_pdf_Export"
    options = {"ReduceImageResolution": {"type": "boolean", "value": "false"}}
    if mode == "lossless":
        options["UseLosslessCompression"] = {"type": "boolean", "value": "true"}
    else:  # quality
        options["UseLosslessCompression"] = {"type": "boolean", "value": "false"}
        options["Quality"] = {"type": "long", "value": "100"}
    return f"pdf:{filter_name}:{json.dumps(options, separators=(',', ':'))}"


async def _kill_tree(proc: asyncio.subprocess.Process) -> None:
    """LibreOffice va uning bola jarayonlarini to'liq o'chiradi."""
    try:
        if os.name == "nt":
            if proc.returncode is None:
                killer = await asyncio.create_subprocess_exec(
                    "taskkill", "/F", "/T", "/PID", str(proc.pid),
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                await killer.wait()
        else:
            os.killpg(proc.pid, signal.SIGKILL)  # butun jarayonlar guruhi
    except (ProcessLookupError, PermissionError, OSError):
        pass
    try:
        await asyncio.wait_for(proc.wait(), timeout=5)
    except Exception:
        pass


def _check_signature(src: Path) -> None:
    """Fayl ichi kengaytmasiga mos ekanini tekshiradi (LibreOffice buzilgan faylni oddiy matn deb ochib yuboradi)."""
    with src.open("rb") as handle:
        head = handle.read(8)
    ext = src.suffix.lower()
    if ext in (".docx", ".pptx"):
        ok = head.startswith(b"PK")
    else:  # .doc, .ppt (eski OLE format)
        ok = head.startswith(b"\xd0\xcf\x11\xe0") or head.startswith(b"{\\rtf")  # RTF ham .doc sifatida uchraydi
    if not ok:
        raise ConversionError(
            f"Fayl haqiqiy {ext.upper()} emas yoki buzilgan (kengaytma ichidagi ma'lumotga mos kelmaydi)."
        )


async def office_to_pdf(
    src: Path,
    kind: str,
    soffice_path: str,
    pdf_export: str,
    timeout: int,
) -> Path:
    """DOC/DOCX/PPT/PPTX -> PDF (LibreOffice headless). Natija: src bilan bir papkadagi out/ ichida."""
    if not soffice_path:
        raise ConversionError(
            "Serverda LibreOffice o'rnatilmagan, shuning uchun Word/PowerPoint konvertatsiyasi hozir ishlamaydi."
        )
    if not src.is_file() or src.stat().st_size == 0:
        raise ConversionError("Fayl bo'sh yoki yuklab olinmadi. Qayta yuborib ko'ring.")
    _check_signature(src)

    workdir = src.parent
    out_dir = workdir / "out"
    profile_dir = workdir / f"lo_profile_{uuid.uuid4().hex[:8]}"  # har bir ish uchun alohida profil
    out_dir.mkdir(exist_ok=True)

    cmd = [
        soffice_path,
        "--headless", "--invisible", "--nologo", "--norestore",
        "--nolockcheck", "--nodefault", "--nofirststartwizard",
        f"-env:UserInstallation={profile_dir.resolve().as_uri()}",
        "--convert-to", _export_options(kind, pdf_export),
        "--outdir", str(out_dir),
        str(src),
    ]

    popen_kwargs: dict = {}
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    else:
        popen_kwargs["start_new_session"] = True

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, **popen_kwargs
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        await _kill_tree(proc)
        raise ConversionError(
            f"Konvertatsiya {timeout} soniyada tugamadi. Fayl juda murakkab yoki katta bo'lishi mumkin."
        )
    except asyncio.CancelledError:
        await _kill_tree(proc)
        raise
    finally:
        if os.name != "nt":  # qolib ketgan bola jarayonlar bo'lsa, tozalaymiz
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass

    out_pdf = out_dir / f"{src.stem}.pdf"
    if proc.returncode != 0 or not out_pdf.is_file():
        log.error(
            "LibreOffice xatosi (kod=%s): stdout=%s stderr=%s",
            proc.returncode,
            stdout.decode(errors="replace")[:500],
            stderr.decode(errors="replace")[:500],
        )
        raise ConversionError(
            "Faylni PDFga aylantirib bo'lmadi. Fayl buzilgan, parol bilan himoyalangan yoki "
            "qo'llab-quvvatlanmaydigan elementlarga ega bo'lishi mumkin."
        )

    validate_pdf(out_pdf)
    return out_pdf
