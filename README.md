# Telegram Anime Bot (Render Ready)

Ushbu loyiha Telegram bot orqali animelarni boshqarish va tomosha qilish uchun mo'ljallangan.

## Tarkibi:
- `main.py` - Botning asosiy kodi va barcha buyruqlar
- `database.py` - SQLite ma'lumotlar bazasi tuzilmasi
- `requirements.txt` - Kerakli kutubxonalar
- `Procfile` - Render.com platformasiga ishga tushirish ko'rsatmasi

## Render.com da ishga tushirish:
1. Ushbu arxivni ochib, GitHub omboringizga (repository) yuklang.
2. Render.com saytida **New Background Worker** yarating.
3. GitHub omborni ulang.
4. **Environment Variables** bo'limida quyidagilarni kiriting:
   - `BOT_TOKEN`: BotFather'dan olingan token
   - `ADMIN_ID`: Telegram ID raqamingiz
5. Deploy tugmasini bosing.
