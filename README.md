# ربات پیشنهاد کلیپ (IRAF TV)

فایل صوتی/ویدیویی مصاحبه (تا ۲۰ مگابایت، یا لینک Google Drive با دسترسی «Anyone with the link») را برای ربات بفرست؛
ربات حدود ۱۰ بازه‌ی پیشنهادی با زمان دقیق شروع/پایان را به‌صورت متن برمی‌گرداند. قوانین انتخاب در `rules.md` است و هر وقت خواستی ویرایشش کن.

## راه‌اندازی (یک‌بار)
1. در تلگرام با @BotFather ربات جدید بساز و توکن را بردار.
2. شناسه‌ی عددی چت خودت را بگیر (مثلاً با @userinfobot).
3. کلید رایگان Gemini را از https://aistudio.google.com/apikey بگیر.
4. یک ریپوی **عمومی** جدید در گیت‌هاب بساز و این کد را در آن push کن.
5. در Settings → Secrets and variables → Actions این سه secret را بساز: `BOT_TOKEN`، `GEMINI_API_KEY`، `ALLOWED_CHAT_IDS` (چند شناسه با کاما جدا شود).
6. یک Personal Access Token (دسترسی Actions: read/write) بساز و در cron-job.org یک job هر ۵ دقیقه با
   `POST https://api.github.com/repos/<OWNER>/<REPO>/actions/workflows/bot.yml/dispatches`
   بدنه‌ی `{"ref":"main"}` و هدر `Authorization: Bearer <TOKEN>` تنظیم کن.

## تست دستی
- اپیزود «بینش» را بفرست؛ پیشنهادهای ۱ تا ۳ باید با برش‌های دستی (۱۱:۳۴، ۱۵:۰۹، ۳۳:۲۲) هم‌پوشانی داشته باشند.
- اپیزود «باقرخان» را بفرست؛ ۱۸:۱۱، ۱۲:۰۷، ۱۳:۵۰ باید در بین پیشنهادها باشند.
- فایل بیش از ۲۰ مگابایت بدون لینک و لینک خصوصی Drive را امتحان کن؛ باید پیام فارسی راهنما بیاید.
- `GEMINI_API_KEY=... python3 scripts/probe_gemini.py audio.mp3` نشان می‌دهد Gemini زمان کلمه‌ها را می‌دهد یا فقط زمان جمله‌ها.

## تست‌ها
`python3 -m unittest discover -s tests -t .`
