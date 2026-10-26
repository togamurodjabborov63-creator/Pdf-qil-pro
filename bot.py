"""Telegram PDF konvertor boti: Rasm / Word / PowerPoint -> PDF."""
from __future__ import annotations

import asyncio
import logging
import re
import shutil
import sys
import time
import uuid
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import load_settings
from converters import (
    ConversionError,
    human_size,
    images_to_pdf,
    office_to_pdf,
    safe_stem,
)

SETTINGS = load_settings()
log = logging.getLogger("pdfbot")

# ----------------------------------------------------------------- matnlar
BTN_IMAGE = "📄 Rasm → PDF"
BTN_WORD = "📝 Word → PDF"
BTN_PPT = "📊 PowerPoint → PDF"
BTN_HELP = "❓ Yordam"

MENU = ReplyKeyboardMarkup([[BTN_IMAGE], [BTN_WORD, BTN_PPT], [BTN_HELP]], resize_keyboard=True)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
WORD_EXTS = {".doc", ".docx"}
PPT_EXTS = {".ppt", ".pptx"}
MIME_TO_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
MODE_TITLES = {"image": "Rasm → PDF", "word": "Word → PDF", "ppt": "PowerPoint → PDF"}
TELEGRAM_SEND_LIMIT = 49 * 1024 * 1024

WELCOME = (
    "Assalomu alaykum! 👋\n\n"
    "Men fayllarni PDFga aylantiruvchi bepul botman:\n"
    "📄 Rasm (JPG, PNG, WEBP) → PDF\n"
    "📝 Word (DOC, DOCX) → PDF\n"
    "📊 PowerPoint (PPT, PPTX) → PDF\n\n"
    "Pastdagi menyudan tanlang yoki faylni to'g'ridan-to'g'ri yuboring."
)

HELP_TEXT = (
    "❓ Yordam\n\n"
    "📄 Rasm → PDF: bir yoki bir nechta rasm yuboring (yuborgan tartibingizda joylashadi), "
    "so'ng «✅ PDF yaratish» tugmasini bosing. Sahifa: asl nisbat yoki A4.\n"
    "💡 Eng yuqori sifat uchun rasmni «Fayl» (Document) sifatida yuboring — oddiy rasmni Telegram o'zi siqib qo'yadi.\n\n"
    "📝 Word → PDF: .doc yoki .docx faylni yuboring.\n"
    "📊 PowerPoint → PDF: .ppt yoki .pptx faylni yuboring.\n\n"
    f"Fayl hajmi: {SETTINGS.max_file_mb} MB gacha. Rasmlar: {SETTINGS.max_images} tagacha.\n"
    "Jarayonni bekor qilish: /cancel\n\n"
    "Eslatma: PDF hajmi asl fayl hajmidan farq qilishi mumkin — formatlar turlicha ishlaydi."
)

SUPPORTED_TEXT = (
    "Qo'llab-quvvatlanadigan formatlar:\n"
    "• Rasm: JPG, JPEG, PNG, WEBP\n• Word: DOC, DOCX\n• PowerPoint: PPT, PPTX"
)


# ----------------------------------------------------------------- loglar
_TOKEN_RE = re.compile(r"\d{6,}:[A-Za-z0-9_-]{30,}")


class SafeFormatter(logging.Formatter):
    """Log matnidan bot tokenini yashiradi (traceback ichidan ham)."""

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        text = text.replace(SETTINGS.bot_token, "***TOKEN***")
        return _TOKEN_RE.sub("***TOKEN***", text)


def setup_logging() -> None:
    fmt = SafeFormatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    try:
        SETTINGS.log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(SETTINGS.log_dir / "bot.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        )
    except OSError as exc:
        print(f"Ogohlantirish: log fayl yaratib bo'lmadi ({exc}); faqat konsolga yoziladi.")
    for h in handlers:
        h.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers = handlers
    # Bu kutubxonalar URL (ichida token bor) ni logga yozadi - o'chirib qo'yamiz
    for noisy in ("httpx", "httpcore", "telegram.ext.Application", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# ----------------------------------------------------------------- yordamchilar
def _user_dir(user_id: int) -> Path:
    path = SETTINGS.temp_dir / str(user_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _get_session(user_id: int, ctx: ContextTypes.DEFAULT_TYPE) -> dict:
    session = ctx.user_data.get("img")
    if session is None:
        folder = _user_dir(user_id) / f"img_{uuid.uuid4().hex[:8]}"
        folder.mkdir(parents=True, exist_ok=True)
        session = {
            "dir": folder, "items": [], "layout": "original",
            "panel_id": None, "n": 0, "updated": time.time(), "from_photo": False,
        }
        ctx.user_data["img"] = session
    return session


def _drop_session(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    session = ctx.user_data.pop("img", None)
    if session:
        shutil.rmtree(session["dir"], ignore_errors=True)


def _cancel_panel_job(ctx: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    if ctx.application.job_queue:
        for job in ctx.application.job_queue.get_jobs_by_name(f"panel_{user_id}"):
            job.schedule_removal()


def _panel_text(session: dict) -> str:
    layout = "A4" if session["layout"] == "a4" else "Asl nisbat"
    text = (
        f"🖼 Qabul qilingan rasmlar: {len(session['items'])} ta\n"
        f"📐 Sahifa o'lchami: {layout}\n\n"
        "Yana rasm yuborishingiz yoki «✅ PDF yaratish» tugmasini bosishingiz mumkin."
    )
    if session["from_photo"]:
        text += "\n\n💡 Eng yuqori sifat uchun rasmlarni «Fayl» (Document) sifatida yuboring."
    return text


def _panel_keyboard(session: dict) -> InlineKeyboardMarkup:
    toggle = "📐 A4 ga o'tkazish" if session["layout"] != "a4" else "📐 Asl nisbatga o'tkazish"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ PDF yaratish", callback_data="img_make")],
        [InlineKeyboardButton(toggle, callback_data="img_layout")],
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="img_cancel")],
    ])


def _schedule_panel(ctx: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> None:
    """Ko'p rasm birdan kelganda bitta panel chiqishi uchun 1.2 soniya kutadi."""
    jq = ctx.application.job_queue
    if jq is None:
        return
    _cancel_panel_job(ctx, user_id)
    jq.run_once(_panel_job, 1.2, name=f"panel_{user_id}", chat_id=chat_id, user_id=user_id)


async def _panel_job(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    job = ctx.job
    user_data = ctx.application.user_data[job.user_id]
    session = user_data.get("img")
    if not session or user_data.get("busy"):
        return
    if session["panel_id"]:
        try:
            await ctx.bot.delete_message(job.chat_id, session["panel_id"])
        except TelegramError:
            pass
    try:
        msg = await ctx.bot.send_message(job.chat_id, _panel_text(session), reply_markup=_panel_keyboard(session))
        session["panel_id"] = msg.message_id
    except TelegramError as exc:
        log.warning("Panel yuborilmadi: %s", exc)


async def _send_pdf(ctx: ContextTypes.DEFAULT_TYPE, chat_id: int, pdf: Path, send_name: str, source_size: int) -> None:
    size = pdf.stat().st_size
    if size > TELEGRAM_SEND_LIMIT:
        raise ConversionError(
            f"PDF tayyor bo'ldi, lekin hajmi {human_size(size)} — Telegram botlar 50 MB dan katta fayl yubora olmaydi. "
            "Faylni kichikroq qismlarga bo'lib yuborib ko'ring."
        )
    caption = (
        "✅ PDF tayyor!\n"
        f"📥 Asl fayl: {human_size(source_size)}\n"
        f"📤 PDF: {human_size(size)}\n"
        "ℹ️ PDF hajmi asl fayldan farq qilishi tabiiy — formatlar turlicha ishlaydi."
    )
    with pdf.open("rb") as handle:
        await ctx.bot.send_document(
            chat_id, document=handle, filename=send_name, caption=caption,
            read_timeout=180, write_timeout=180, connect_timeout=30,
        )


def _rename_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("➡️ Shart emas", callback_data="rn_skip")]])


async def _ask_rename(
    ctx: ContextTypes.DEFAULT_TYPE, chat_id: int, pdf: Path, default_name: str,
    source_size: int, cleanup_dir: Path, status_msgs: list,
) -> None:
    """PDF tayyor: «tayyorlanmoqda» xabarini o'chiradi va yangi nom so'raydi."""
    for status in status_msgs:
        try:
            await status.delete()
        except TelegramError:
            pass
    msg = await ctx.bot.send_message(
        chat_id,
        "✅ PDF tayyor!\n\n"
        "✏️ PDF uchun yangi nom berasizmi?\n"
        "Yangi nomni yozib yuboring yoki «Shart emas» tugmasini bosing.\n\n"
        f"Hozirgi nom: {default_name}",
        reply_markup=_rename_keyboard(),
    )
    ctx.user_data["rename"] = {
        "pdf": pdf, "name": default_name, "source_size": source_size,
        "cleanup": cleanup_dir, "msg_id": msg.message_id, "updated": time.time(),
    }


async def _finish_rename(ctx: ContextTypes.DEFAULT_TYPE, chat_id: int, new_name: str | None) -> None:
    """PDFni (yangi yoki avvalgi nom bilan) yuboradi va vaqtinchalik fayllarni o'chiradi."""
    state = ctx.user_data.pop("rename", None)
    if not state:
        return
    try:
        await ctx.bot.delete_message(chat_id, state["msg_id"])
    except TelegramError:
        pass
    send_name = state["name"]
    if new_name:
        send_name = f"{safe_stem(new_name, default=Path(state['name']).stem)}.pdf"
    try:
        await _send_pdf(ctx, chat_id, state["pdf"], send_name, state["source_size"])
    except ConversionError as exc:
        await ctx.bot.send_message(chat_id, f"⚠️ {exc.user_message}")
    except TelegramError as exc:
        log.warning("PDF yuborilmadi: %s", exc)
        await ctx.bot.send_message(chat_id, "⚠️ PDFni yuborib bo'lmadi. Faylni qayta yuborib ko'ring.")
    except Exception:
        log.exception("PDF yuborishda kutilmagan xato")
        await ctx.bot.send_message(chat_id, "⚠️ Kutilmagan xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring.")
    finally:
        shutil.rmtree(state["cleanup"], ignore_errors=True)
        ctx.user_data.pop("mode", None)
        await ctx.bot.send_message(chat_id, "Yana nima qilamiz? Menyudan tanlang 👇", reply_markup=MENU)


async def _rename_pending(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    if ctx.user_data.get("rename"):
        await update.effective_message.reply_text(
            "✏️ Avval PDF nomini hal qiling: yangi nom yozing yoki «Shart emas» tugmasini bosing."
        )
        return True
    return False


async def cb_rename_skip(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not ctx.user_data.get("rename"):
        await query.answer("Bu so'rov eskirgan.", show_alert=True)
        return
    await query.answer()
    await _finish_rename(ctx, update.effective_chat.id, None)


async def _guard_switch(update: Update, ctx: ContextTypes.DEFAULT_TYPE, target: str) -> bool:
    if await _rename_pending(update, ctx):
        return False
    if ctx.user_data.get("busy"):
        await update.message.reply_text("⏳ Oldingi faylingiz tayyorlanmoqda. Iltimos, kuting.")
        return False
    session = ctx.user_data.get("img")
    if session and session["items"] and target != "image":
        await update.message.reply_text(
            "Sizda tugallanmagan rasmlar bor. Avval «✅ PDF yaratish» ni bosing yoki /cancel yuboring."
        )
        return False
    return True


async def _mode_ok(update: Update, ctx: ContextTypes.DEFAULT_TYPE, kind: str) -> bool:
    mode = ctx.user_data.get("mode")
    if mode and mode != kind:
        await update.effective_message.reply_text(
            f"Siz hozir «{MODE_TITLES[mode]}» rejimidasiz, lekin boshqa turdagi fayl yubordingiz.\n"
            "To'g'ri menyu tugmasini bosing (yoki /cancel yuborib qayta boshlang)."
        )
        return False
    return True


# ----------------------------------------------------------------- buyruqlar va menyu
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(WELCOME, reply_markup=MENU)


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT, reply_markup=MENU)


async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if ctx.user_data.get("busy"):
        await update.message.reply_text("⏳ Konvertatsiya boshlanib bo'ldi, uni to'xtatib bo'lmaydi. Biroz kuting.")
        return
    _cancel_panel_job(ctx, update.effective_user.id)
    _drop_session(ctx)
    pending = ctx.user_data.pop("rename", None)
    if pending:
        shutil.rmtree(pending["cleanup"], ignore_errors=True)
    ctx.user_data.pop("mode", None)
    await update.message.reply_text("❌ Bekor qilindi. Menyudan yangi amal tanlang.", reply_markup=MENU)


async def menu_image(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard_switch(update, ctx, "image"):
        return
    ctx.user_data["mode"] = "image"
    await update.message.reply_text(
        "📄 Rasm → PDF\n\nRasm(lar) yuboring (JPG, PNG, WEBP). Bir nechta rasm yuborsangiz, "
        "ular yuborgan tartibingizda bitta PDFga birlashadi.\n"
        "💡 Eng yaxshi sifat uchun rasmlarni «Fayl» (Document) sifatida yuboring."
    )


async def menu_word(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard_switch(update, ctx, "word"):
        return
    ctx.user_data["mode"] = "word"
    await update.message.reply_text(f"📝 Word → PDF\n\n.doc yoki .docx faylni yuboring ({SETTINGS.max_file_mb} MB gacha).")


async def menu_ppt(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard_switch(update, ctx, "ppt"):
        return
    ctx.user_data["mode"] = "ppt"
    await update.message.reply_text(f"📊 PowerPoint → PDF\n\n.ppt yoki .pptx faylni yuboring ({SETTINGS.max_file_mb} MB gacha).")


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if ctx.user_data.get("rename"):  # foydalanuvchi PDF uchun yangi nom yozdi
        await _finish_rename(ctx, update.effective_chat.id, update.message.text)
        return
    await update.message.reply_text("Menyudan amalni tanlang yoki PDFga aylantiriladigan faylni yuboring.", reply_markup=MENU)


async def on_other(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text("Bu turdagi xabarni qayta ishlay olmayman.\n\n" + SUPPORTED_TEXT)


# ----------------------------------------------------------------- RASM
async def _add_image(update: Update, ctx: ContextTypes.DEFAULT_TYPE, file_id: str, ext: str, size: int | None, is_photo: bool) -> None:
    msg = update.effective_message
    user_id = update.effective_user.id

    if size and size > SETTINGS.max_file_bytes:
        await msg.reply_text(f"⚠️ Rasm juda katta ({human_size(size)}). Ruxsat: {SETTINGS.max_file_mb} MB gacha.")
        return
    if await _rename_pending(update, ctx):
        return
    if ctx.user_data.get("busy"):
        await msg.reply_text("⏳ Oldingi faylingiz tayyorlanmoqda. Iltimos, kuting.")
        return
    if not await _mode_ok(update, ctx, "image"):
        return

    session = _get_session(user_id, ctx)
    if len(session["items"]) >= SETTINGS.max_images:
        await msg.reply_text(f"⚠️ Eng ko'pi bilan {SETTINGS.max_images} ta rasm qo'shish mumkin. «✅ PDF yaratish» ni bosing.")
        return

    session["n"] += 1
    path = session["dir"] / f"{session['n']:04d}{ext}"
    try:
        tg_file = await ctx.bot.get_file(file_id)
        await tg_file.download_to_drive(path)
    except TelegramError as exc:
        log.warning("Rasm yuklab olinmadi: %s", exc)
        await msg.reply_text("⚠️ Rasmni yuklab olib bo'lmadi (hajmi katta bo'lishi mumkin). Qayta yuborib ko'ring.")
        return

    if ctx.user_data.get("img") is not session:  # yuklash paytida bekor qilingan
        path.unlink(missing_ok=True)
        return

    session["items"].append((msg.message_id, path, path.stat().st_size))  # message_id = yuborilish tartibi
    session["updated"] = time.time()
    session["from_photo"] = session["from_photo"] or is_photo
    ctx.user_data["mode"] = "image"
    _schedule_panel(ctx, update.effective_chat.id, user_id)


async def on_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    photo = update.message.photo[-1]  # eng katta o'lcham
    await _add_image(update, ctx, photo.file_id, ".jpg", photo.file_size, is_photo=True)


async def cb_layout(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    session = ctx.user_data.get("img")
    if not session:
        await query.answer("Rasmlar topilmadi.", show_alert=True)
        return
    await query.answer()
    session["layout"] = "original" if session["layout"] == "a4" else "a4"
    try:
        await query.edit_message_text(_panel_text(session), reply_markup=_panel_keyboard(session))
    except TelegramError:
        pass


async def cb_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if ctx.user_data.get("busy"):
        await query.answer("Konvertatsiya boshlanib bo'ldi, kuting.", show_alert=True)
        return
    await query.answer()
    _cancel_panel_job(ctx, update.effective_user.id)
    _drop_session(ctx)
    ctx.user_data.pop("mode", None)
    try:
        await query.edit_message_text("❌ Bekor qilindi. Rasmlar o'chirildi.")
    except TelegramError:
        pass
    await ctx.bot.send_message(update.effective_chat.id, "Menyudan yangi amalni tanlang.", reply_markup=MENU)


async def cb_make_pdf(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    session = ctx.user_data.get("img")
    if not session or not session["items"]:
        await query.answer("Avval rasm yuboring.", show_alert=True)
        return
    if ctx.user_data.get("busy"):
        await query.answer("Allaqachon tayyorlanmoqda...", show_alert=True)
        return
    await query.answer()

    ctx.user_data["busy"] = True
    chat_id = update.effective_chat.id
    _cancel_panel_job(ctx, update.effective_user.id)
    session["panel_id"] = None
    try:
        await query.edit_message_text("⏳ Faylingiz tayyorlanmoqda...")
    except TelegramError:
        pass

    items = sorted(session["items"], key=lambda item: item[0])  # yuborilgan tartib
    paths = [p for _, p, _ in items]
    source_size = sum(s for _, _, s in items)
    out = session["dir"] / "result.pdf"
    name = f"Rasmlar_{len(paths)}ta_{datetime.now():%Y%m%d_%H%M}.pdf"
    handed_off = False
    try:
        async with ctx.application.bot_data["sem"]:
            await asyncio.wait_for(
                asyncio.to_thread(images_to_pdf, paths, out, session["dir"], session["layout"]),
                timeout=SETTINGS.convert_timeout,
            )
        # PDF tayyor: «tayyorlanmoqda» xabari o'chadi va yangi nom so'raladi
        await _ask_rename(ctx, chat_id, out, name, source_size, session["dir"], [query.message])
        handed_off = True
        ctx.user_data.pop("img", None)  # sessiya tugadi, papka nom hal bo'lgach o'chiriladi
    except asyncio.TimeoutError:
        await ctx.bot.send_message(chat_id, "⚠️ Vaqt tugadi. Kamroq rasm bilan urinib ko'ring.")
    except ConversionError as exc:
        await ctx.bot.send_message(chat_id, f"⚠️ {exc.user_message}")
    except Exception:
        log.exception("Rasm->PDF kutilmagan xato")
        await ctx.bot.send_message(chat_id, "⚠️ Kutilmagan xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring.")
    finally:
        ctx.user_data["busy"] = False
        if not handed_off:
            try:
                await query.message.delete()
            except TelegramError:
                pass
            _drop_session(ctx)
            ctx.user_data.pop("mode", None)
            await ctx.bot.send_message(chat_id, "Yana nima qilamiz? Menyudan tanlang 👇", reply_markup=MENU)


# ----------------------------------------------------------------- WORD / POWERPOINT
async def _handle_office(update: Update, ctx: ContextTypes.DEFAULT_TYPE, doc, kind: str, ext: str) -> None:
    msg = update.effective_message
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if doc.file_size and doc.file_size > SETTINGS.max_file_bytes:
        await msg.reply_text(f"⚠️ Fayl juda katta ({human_size(doc.file_size)}). Ruxsat: {SETTINGS.max_file_mb} MB gacha.")
        return
    if await _rename_pending(update, ctx):
        return
    if ctx.user_data.get("busy"):
        await msg.reply_text("⏳ Oldingi faylingiz tayyorlanmoqda. Iltimos, kuting.")
        return
    if not await _mode_ok(update, ctx, kind):
        return

    ctx.user_data["busy"] = True
    status = await msg.reply_text("✅ Fayl qabul qilindi.\n⏳ Faylingiz tayyorlanmoqda...")
    workdir = _user_dir(user_id) / uuid.uuid4().hex[:10]
    workdir.mkdir(parents=True, exist_ok=True)
    handed_off = False
    try:
        src = workdir / f"input{ext}"  # ichki nom xavfsiz; foydalanuvchi nomi faqat PDF nomi uchun
        tg_file = await ctx.bot.get_file(doc.file_id)
        await tg_file.download_to_drive(src)
        source_size = src.stat().st_size

        async with ctx.application.bot_data["sem"]:
            pdf = await office_to_pdf(src, kind, SETTINGS.soffice_path, SETTINGS.pdf_export, SETTINGS.convert_timeout)

        default_name = f"{safe_stem(doc.file_name or '')}.pdf"
        # PDF tayyor: «tayyorlanmoqda» xabari o'chadi va yangi nom so'raladi
        await _ask_rename(ctx, chat_id, pdf, default_name, source_size, workdir, [status])
        handed_off = True
    except ConversionError as exc:
        await ctx.bot.send_message(chat_id, f"⚠️ {exc.user_message}")
    except TelegramError as exc:
        log.warning("Telegram xatosi: %s", exc)
        await ctx.bot.send_message(chat_id, "⚠️ Faylni yuklab olish yoki yuborishda xato bo'ldi. Qayta urinib ko'ring.")
    except Exception:
        log.exception("Office->PDF kutilmagan xato")
        await ctx.bot.send_message(chat_id, "⚠️ Kutilmagan xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring.")
    finally:
        ctx.user_data["busy"] = False
        if not handed_off:
            shutil.rmtree(workdir, ignore_errors=True)
            ctx.user_data.pop("mode", None)
            try:
                await status.delete()
            except TelegramError:
                pass


async def on_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    doc = update.message.document
    ext = Path(doc.file_name or "").suffix.lower()
    if not ext and doc.mime_type:
        ext = MIME_TO_EXT.get(doc.mime_type, "")

    if ext in IMAGE_EXTS:
        await _add_image(update, ctx, doc.file_id, ext, doc.file_size, is_photo=False)
    elif ext in WORD_EXTS:
        await _handle_office(update, ctx, doc, "word", ext)
    elif ext in PPT_EXTS:
        await _handle_office(update, ctx, doc, "ppt", ext)
    else:
        shown = ext or "noma'lum"
        await update.message.reply_text(f"⚠️ «{shown}» formatini qabul qila olmayman.\n\n{SUPPORTED_TEXT}")


# ----------------------------------------------------------------- xatolar, ishga tushirish
async def on_error(update: object, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("Handlerda xato", exc_info=ctx.error)
    if isinstance(update, Update) and update.effective_chat:
        try:
            await ctx.bot.send_message(update.effective_chat.id, "⚠️ Xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring.")
        except TelegramError:
            pass


async def cleanup_stale(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Uzoq vaqt tegilmagan rasm sessiyalarini o'chiradi."""
    now = time.time()
    ttl = SETTINGS.session_ttl_min * 60
    for _uid, data in list(ctx.application.user_data.items()):
        session = data.get("img")
        if session and not data.get("busy") and now - session["updated"] > ttl:
            shutil.rmtree(session["dir"], ignore_errors=True)
            data.pop("img", None)
            data.pop("mode", None)
        pending = data.get("rename")
        if pending and now - pending["updated"] > ttl:  # nom javobi kelmadi - tozalaymiz
            shutil.rmtree(pending["cleanup"], ignore_errors=True)
            data.pop("rename", None)
            data.pop("mode", None)


async def post_init(app) -> None:
    app.bot_data["sem"] = asyncio.Semaphore(SETTINGS.max_parallel)
    shutil.rmtree(SETTINGS.temp_dir, ignore_errors=True)  # oldingi ishdan qolgan vaqtinchalik fayllar
    SETTINGS.temp_dir.mkdir(parents=True, exist_ok=True)
    if app.job_queue:
        app.job_queue.run_repeating(cleanup_stale, interval=600, first=600)
    me = await app.bot.get_me()
    log.info("Bot ishga tushdi: @%s | rejim=%s", me.username, SETTINGS.mode)
    if not SETTINGS.soffice_path:
        log.warning("LibreOffice topilmadi! Word/PowerPoint ishlamaydi, faqat rasm->PDF ishlaydi.")
    else:
        log.info("LibreOffice: %s", SETTINGS.soffice_path)


def main() -> None:
    setup_logging()
    app = (
        ApplicationBuilder()
        .token(SETTINGS.bot_token)
        .concurrent_updates(True)
        .connect_timeout(30)
        .read_timeout(60)
        .write_timeout(120)
        .pool_timeout(30)
        .post_init(post_init)
        .build()
    )

    private = filters.ChatType.PRIVATE
    app.add_handler(CommandHandler("start", cmd_start, filters=private))
    app.add_handler(CommandHandler("help", cmd_help, filters=private))
    app.add_handler(CommandHandler("cancel", cmd_cancel, filters=private))

    app.add_handler(MessageHandler(private & filters.Text([BTN_IMAGE]), menu_image))
    app.add_handler(MessageHandler(private & filters.Text([BTN_WORD]), menu_word))
    app.add_handler(MessageHandler(private & filters.Text([BTN_PPT]), menu_ppt))
    app.add_handler(MessageHandler(private & filters.Text([BTN_HELP]), cmd_help))

    app.add_handler(MessageHandler(private & filters.PHOTO, on_photo))
    app.add_handler(MessageHandler(private & filters.Document.ALL, on_document))

    app.add_handler(CallbackQueryHandler(cb_make_pdf, pattern="^img_make$"))
    app.add_handler(CallbackQueryHandler(cb_layout, pattern="^img_layout$"))
    app.add_handler(CallbackQueryHandler(cb_cancel, pattern="^img_cancel$"))
    app.add_handler(CallbackQueryHandler(cb_rename_skip, pattern="^rn_skip$"))

    app.add_handler(MessageHandler(private & filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(
        MessageHandler(private & ~filters.COMMAND & ~filters.TEXT & ~filters.PHOTO & ~filters.Document.ALL, on_other)
    )
    app.add_error_handler(on_error)

    if SETTINGS.mode == "webhook":
        log.info("Webhook rejimi: port %s", SETTINGS.port)
        app.run_webhook(
            listen="0.0.0.0",
            port=SETTINGS.port,
            url_path="telegram",
            webhook_url=f"{SETTINGS.webhook_url}/telegram",
            secret_token=SETTINGS.webhook_secret or None,
            drop_pending_updates=True,
        )
    else:
        log.info("Polling rejimi (to'xtatish: Ctrl+C)")
        app.run_polling(drop_pending_updates=True)

import platform

if platform.system() == "Windows":
    SOFFICE_PATH = r"C:\Program Files\LibreOffice\program\soffice.exe"
else:
    SOFFICE_PATH = "/usr/bin/soffice"

if __name__ == "__main__":
    main()
