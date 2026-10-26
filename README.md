# 📄 Telegram PDF konvertor boti

Bepul bot: **Rasm → PDF**, **Word (DOC/DOCX) → PDF**, **PowerPoint (PPT/PPTX) → PDF**.

- Rasmlar siqilmaydi: JPEG va oddiy PNG fayllar PDF ichiga **qayta kodlanmasdan** joylanadi.
- Word/PowerPoint LibreOffice orqali o'zgartiriladi (matn qayta yozilmaydi, dizayn saqlanadi).
- Windowsda `polling`, hostingda `webhook` yoki doimiy worker rejimida ishlaydi.

## Loyiha fayllari

| Fayl | Vazifasi |
|---|---|
| `bot.py` | Telegram bot (menyu, tugmalar, fayl qabul qilish) |
| `converters.py` | Rasm→PDF va Office→PDF mantiqi |
| `config.py` | `.env` dan sozlamalarni o'qish |
| `requirements.txt` | Python kutubxonalari |
| `.env.example` | Sozlamalar namunasi (token yo'q) |
| `.gitignore`, `.dockerignore` | Maxfiy fayllarni himoyalash |
| `Dockerfile` | LibreOffice bilan tayyor Docker image |

---

## 1-QISM. Windowsda ishga tushirish (oddiy tilda)

> Hamma buyruqlar **CMD** (Command Prompt) uchun. CMD ochish: `Win` tugmasini bosing → `cmd` yozing → Enter.

### 1. Python o'rnatish
1. https://www.python.org/downloads/ ga kiring, **Python 3.12** (yoki yangiroq barqaror) ni yuklab oling.
2. O'rnatishda birinchi oynada **"Add python.exe to PATH"** katakchasini **albatta belgilang**, so'ng **Install Now**.
3. Tekshirish (istalgan papkada):
   ```
   python --version
   ```
   `Python 3.12.x` chiqsa — tayyor.

### 2. Telegramda bot yaratish va token olish
1. Telegramda **@BotFather** ni toping (yonida ko'k belgi bo'ladi).
2. `/newbot` yuboring.
3. Bot nomini yozing (masalan: `PDF Konvertor`).
4. Username yozing, oxiri `bot` bilan tugashi shart (masalan: `mening_pdf_konvertor_bot`).
5. BotFather uzun **token** beradi (ko'rinishi: `1234567890:AAH...`). Uni **hech kimga bermang**.

### 3. Loyiha papkasini yaratish
Loyiha fayllarini (shu papkadagi hammasini) `C:\pdf_bot` ga joylang. Yoki CMD da:
```
mkdir C:\pdf_bot
cd /d C:\pdf_bot
```
So'ng yuklab olgan fayllarni shu papkaga nusxalang (`bot.py`, `config.py`, `converters.py`, `requirements.txt`, `.env.example`, `.gitignore`, `.dockerignore`, `Dockerfile`, `README.md`).

### 4. Virtual muhit yaratish
**Papka: `C:\pdf_bot`**
```
cd /d C:\pdf_bot
python -m venv venv
venv\Scripts\activate
```
Qator boshida `(venv)` yozuvi chiqsa — muvaffaqiyatli. (Har safar yangi CMD ochganingizda `venv\Scripts\activate` ni qayta yozing.)

### 5. Kutubxonalarni o'rnatish
**Papka: `C:\pdf_bot`, `(venv)` yoqilgan holda**
```
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 6. LibreOffice o'rnatish va tekshirish
1. https://www.libreoffice.org/download/ dan Windows versiyasini yuklab, o'rnating (oddiy "Next, Next").
2. Tekshirish (CMD, istalgan papka):
   ```
   "C:\Program Files\LibreOffice\program\soffice.exe" --version
   ```
   `LibreOffice 7.x` yoki `24.x` kabi yozuv chiqsa — yaxshi.
3. Agar boshqa joyga o'rnatgan bo'lsangiz, keyingi qadamda `.env` ga `SOFFICE_PATH=...` yo'lini yozasiz.

> LibreOffice o'rnatilmasa ham **rasm → PDF ishlaydi**, faqat Word/PowerPoint ishlamaydi.

### 7. `.env` faylini to'ldirish
**Papka: `C:\pdf_bot`**
```
copy .env.example .env
notepad .env
```
Ochilgan faylda faqat shu qatorni o'zgartiring:
```
BOT_TOKEN=1234567890:AAH...sizning_tokeningiz
```
Boshqa qatorlarni o'zgartirish shart emas. Saqlang (`Ctrl+S`) va yoping.
⚠️ Token atrofida qo'shtirnoq yoki ortiqcha bo'shliq qo'ymang.

### 8. Botni ishga tushirish
**Papka: `C:\pdf_bot`, `(venv)` yoqilgan**
```
python bot.py
```
`Bot ishga tushdi: @sizning_botingiz` yozuvi chiqsa — bot ishlayapti. CMD oynasini **yopmang**. To'xtatish: `Ctrl+C`.

### 9. Test qilish
Telegramda botingizni oching → `/start`. Pastdagi **Test ro'yxati** (README oxirida) bo'yicha rasm, DOCX va PPTX bilan sinab ko'ring.

### 10. Xatolarni tuzatish

| Xato / belgi | Sabab va yechim |
|---|---|
| `'python' is not recognized` | Python o'rnatishda PATH belgilanmagan. Python'ni qayta o'rnating va "Add to PATH" ni belgilang. |
| `XATO: BOT_TOKEN topilmadi...` | `.env` yo'q yoki token noto'g'ri. 7-qadamni qayta bajaring. Fayl nomi aynan `.env` bo'lsin (`.env.txt` emas). |
| `Unauthorized` / `InvalidToken` | Token xato yoki BotFather'da yangilangan. `/token` orqali yangisini oling. |
| Bot javob bermayapti | CMD oynasi yopilgan yoki internet yo'q. Bot ishlab turgan CMD ni tekshiring. Bir tokenni ikki joyda (kompyuter + hosting) bir vaqtda ishlatmang (`Conflict` xatosi). |
| "LibreOffice o'rnatilmagan..." | 6-qadam. Yoki `.env` ga `SOFFICE_PATH=C:\Program Files\LibreOffice\program\soffice.exe` yozing. |
| Word/PPT "aylantirib bo'lmadi" | Fayl buzilgan yoki parolli. Boshqa fayl bilan tekshiring. `logs\bot.log` ichida aniq sabab bor. Doimiy chiqsa `.env` da `PDF_IMAGE_EXPORT=default` ni sinab ko'ring (⚠️ bunda rasmlar siqilishi mumkin). |
| "Vaqt tugadi" | Fayl juda murakkab. `.env` da `CONVERT_TIMEOUT=300` qiling. |
| PDF 50 MB dan katta | Telegram botlar 50 MB dan katta fayl yubora olmaydi. Faylni bo'lib yuboring. |
| Fayl 20 MB dan katta | Telegram botlar 20 MB dan katta faylni yuklab ola olmaydi (Telegram chegarasi). |

Loglar: `C:\pdf_bot\logs\bot.log` (token avtomatik yashiriladi).

### 11. GitHub'ga maxfiy ma'lumotlarsiz yuklash
Avval https://git-scm.com/download/win dan Git o'rnating va https://github.com da bo'sh repozitoriy yarating (nomi: `pdf-bot`, **Private** tavsiya etiladi).

**Papka: `C:\pdf_bot`**
```
git init
git add .
git status
```
⚠️ `git status` ro'yxatida **`.env` bo'lmasligi shart** (faqat `.env.example`). `.gitignore` uni avtomatik chiqarib tashlaydi. Agar `.env` ko'rinsa — to'xtang va `.gitignore` borligini tekshiring.
```
git commit -m "PDF bot"
git branch -M main
git remote add origin https://github.com/SIZNING_LOGIN/pdf-bot.git
git push -u origin main
```
Agar token tasodifan GitHub'ga chiqib ketsa: darhol @BotFather → `/revoke` orqali tokenni almashtiring.

---

## 2-QISM. Hostingga joylashtirish (Docker)

### Bepul hosting haqida ochiq gap
- **Hech bir bepul hostingda 24/7 ishlash kafolatlanmagan.** Shartlar tez-tez o'zgaradi — ro'yxatdan o'tishdan oldin xizmatning hozirgi rasmiy sahifasini tekshiring.
- Odatda bepul tarifda: xotira kam (256–512 MB), jarayon uzoq kutishdan keyin **"uxlab qoladi"**, ba'zilari bank kartasi so'raydi, ba'zilari bepul "worker" bermaydi (faqat web-service).
- **LibreOffice xotirani ko'p yeydi** (taxminan 300–500 MB va undan ko'p). 512 MB li hostingda katta Word/PPT fayllar xotira yetishmasligidan to'xtashi mumkin. Shunda `.env` da `MAX_PARALLEL=1` qiling.
- Uxlab qoladigan hostingda birinchi xabarga javob bir necha o'n soniya kechikishi mumkin.
- Eng ishonchli bepul variant: **o'z Windows kompyuteringiz** (yoqilgan va internetga ulangan bo'lsa). Kartadan tasdiqlash qabul qilsangiz, "Always Free" turidagi virtual server (VPS) ham bor — lekin u qo'lda sozlashni talab qiladi.
- Bot hech qanday doimiy disk talab qilmaydi: fayllar `/tmp` da vaqtincha turadi va darhol o'chiriladi.

### 12. Docker orqali joylashtirish (umumiy tartib)
Loyiha GitHub'da bo'lsin (11-qadam). Keyin istalgan Docker qo'llab-quvvatlaydigan hostingda:

1. Hostingda yangi xizmat yarating va **GitHub repozitoriyingizni** ulang; usul sifatida **Dockerfile** ni tanlang.
2. Xizmat turi:
   - **Worker / background service** bor bo'lsa (bepul bo'lsa) → `polling` rejimi:
     ```
     BOT_TOKEN=...tokeningiz
     BOT_MODE=polling
     MAX_PARALLEL=1
     ```
   - Faqat **web service** bo'lsa → `webhook` rejimi:
     ```
     BOT_TOKEN=...tokeningiz
     BOT_MODE=webhook
     WEBHOOK_URL=https://hosting-bergan-manzil.example.com
     WEBHOOK_SECRET=o'zingiz_o'ylab_topgan_uzun_maxfiy_qator
     MAX_PARALLEL=1
     ```
     (`PORT` ni hosting o'zi beradi; bot shu portni eshitadi. `WEBHOOK_URL` — hosting bergan **https** manzil, oxirida `/` siz. Manzilni birinchi deploydan keyin bilib olasiz, so'ng qo'shib qayta deploy qiling.)
3. Muhit o'zgaruvchilarini hostingning **Environment / Variables** bo'limiga kiriting. `.env` faylini yuklamang.
4. Deploy tugmasini bosing. Docker image qurilishi 5–10 daqiqa olishi mumkin (LibreOffice katta).

Docker'ni o'z kompyuteringizda sinab ko'rish (Docker Desktop o'rnatilgan bo'lsa), **papka: `C:\pdf_bot`**:
```
docker build -t pdf-bot .
docker run --rm --env-file .env pdf-bot
```

### 13. Hosting loglarini tekshirish
Hostingning **Logs** bo'limida shu yozuvlar chiqishi kerak:
```
LibreOffice: soffice
Bot ishga tushdi: @sizning_botingiz | rejim=polling   (yoki webhook)
```
Keyin Telegramda `/start` yuboring — menyu chiqsa va Word/PPT test fayllari aylansa, hammasi ishlayapti. Xato bo'lsa, loglardagi `ERROR` qatorlarini o'qing.

Muhim: bitta token bilan bir vaqtda faqat **bitta joyda** ishlating — hostingga o'tganda Windowsdagi botni `Ctrl+C` bilan to'xtating.

---

## Bot qanday ishlaydi (qisqacha)
- **Rasm:** bir nechta rasm → bot yig'adi → «✅ PDF yaratish». Tartib = yuborilish tartibi. Sahifa: *asl nisbat* yoki *A4* (tugma orqali). Shaffof PNG oq fonga qo'yiladi. JPEG/PNG qayta siqilmaydi.
- **Word / PowerPoint:** fayl yuboriladi → LibreOffice (headless) → tekshirilgan PDF qaytariladi, asl va PDF hajmi ko'rsatiladi.
- Har foydalanuvchi uchun alohida vaqtinchalik papka; ish tugagach o'chiriladi. Bir vaqtda bir foydalanuvchida bitta konvertatsiya, umumiy `MAX_PARALLEL` ta.
- Bo'sh yoki buzilgan PDF hech qachon yuborilmaydi.

---

## ✅ Test ro'yxati

### A) Rasm → PDF
- [ ] `/start` — salomlashuv va 4 tugmali menyu chiqdi.
- [ ] «📄 Rasm → PDF» bosildi, ko'rsatma chiqdi.
- [ ] 1 ta JPG **fayl (Document)** sifatida yuborildi → panel chiqdi → «PDF yaratish» → PDF keldi, hajmi ko'rsatildi.
- [ ] 3 ta rasm (JPG, PNG, WEBP) ketma-ket yuborildi → panelda «3 ta» → PDF 3 sahifa, tartib to'g'ri.
- [ ] Shaffof PNG yuborildi → PDFda fon oq, rasm buzilmagan.
- [ ] «A4 ga o'tkazish» → PDF sahifalari A4; «Asl nisbat» → sahifa rasm nisbatida.
- [ ] «Bekor qilish» → rasmlar o'chdi, menyu qaytdi.
- [ ] Rasmlarsiz «PDF yaratish» bosish iloji yo'q (ogohlantirish chiqadi).
- [ ] `.gif` yoki `.pdf` yuborildi → "formatni qabul qila olmayman" xabari.

### B) Word → PDF
- [ ] «📝 Word → PDF» bosildi.
- [ ] O'zbekcha + ruscha + inglizcha matnli, jadval va rasmli `.docx` yuborildi → "Faylingiz tayyorlanmoqda..." → PDF keldi; matn, jadval, rasm, sahifa raqamlari to'g'ri.
- [ ] Eski `.doc` fayl ham aylandi.
- [ ] Buzilgan fayl (masalan, `.txt` nomini `.docx` ga o'zgartirilgan) → tushunarli xato, PDF kelmadi.
- [ ] 20 MB dan katta fayl → hajm haqida xabar.
- [ ] Rasmli hujjatda PDFdagi rasmlar xiralashmagan.

### C) PowerPoint → PDF
- [ ] «📊 PowerPoint → PDF» bosildi.
- [ ] Bir necha slaydli `.pptx` yuborildi → PDFda sahifalar soni = slaydlar soni, tartib to'g'ri.
- [ ] Dizayn, rasmlar va o'lcham saqlangan.
- [ ] Eski `.ppt` fayl ham aylandi.
- [ ] Xabarda asl va PDF hajmi ko'rsatildi.

### D) Umumiy
- [ ] Ikki xil akkauntdan bir vaqtda fayl yuborildi → ikkalasi ham o'z PDFini oldi, bot to'xtamadi.
- [ ] Konvertatsiyadan keyin `%TEMP%\pdf_bot_tmp` ichida fayllar qolmagan.
- [ ] Diskor Task Manager'da ortiqcha `soffice.exe` jarayonlari qolmagan.
- [ ] `logs\bot.log` da bot tokeni ko'rinmaydi.
- [ ] `git status` da `.env` yo'q.
