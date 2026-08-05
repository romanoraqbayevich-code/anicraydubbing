import asyncio
import logging
import os
import aiosqlite
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

# --- CONFIGURATSIYA ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "8890621891:AAFX0yKQ81saY144zaFiBfGmAu75vi4cnmM")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8369095793"))
DB_NAME = "anime_bot.db"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Bot holati (Global o'zgaruvchi)
BOT_ACTIVE = True

# --- FSM STATES ---
class AdminFSM(StatesGroup):
    add_user_id = State()

class AnimeFSM(StatesGroup):
    title = State()
    code = State()

class EpisodeFSM(StatesGroup):
    code = State()
    ep_num = State()
    file_id = State()
    photo = State()

class ChannelFSM(StatesGroup):
    channel_id = State()
    username = State()
    invite_link = State()

class DeleteAnimeFSM(StatesGroup):
    code = State()

# --- DATABASE INIT ---
async def init_db():
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
        await conn.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)")
        await conn.execute("CREATE TABLE IF NOT EXISTS anime (code TEXT PRIMARY KEY, title TEXT)")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                anime_code TEXT,
                ep_num INTEGER,
                file_id TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                channel_id INTEGER PRIMARY KEY,
                username TEXT,
                invite_link TEXT
            )
        """)
        await conn.commit()

async def is_admin(user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,)) as cursor:
            res = await cursor.fetchone()
            return res is not None

async def check_subscribes(user_id: int):
    """Kanallar, Guruhlar va Zayavkalarni to'g'ri tekshirish funksiyasi"""
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT channel_id, invite_link FROM channels") as cursor:
            channels = await cursor.fetchall()
            
    unsubbed = []
    for ch_id, link in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch_id, user_id=user_id)
            if member.status in ["left", "kicked"]:
                unsubbed.append((ch_id, link))
        except Exception as e:
            print(f"Obuna tekshirishda xatolik ({ch_id}): {e}")
            unsubbed.append((ch_id, link))
            
    return unsubbed

# --- MENYULAR ---
def admin_menu():
    kb = [
        [KeyboardButton(text="➕ Anime qo‘shish"), KeyboardButton(text="➕ Qism qo‘shish")],
        [KeyboardButton(text="🗑 Anime o‘chirish"), KeyboardButton(text="📢 Kanallar boshqaruvi")],
        [KeyboardButton(text="👤 Adminlar boshqaruvi"), KeyboardButton(text="🤖 Avto-kanal sozlash")],
        [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="⚙️ Bot holatini boshqarish")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- 24/7 SERVER ---
async def health_check(request):
    return web.Response(text="Bot Active 24/7", status=200)

async def start_background_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

# --- START HANDLER ---
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
        await conn.commit()

    if await is_admin(message.from_user.id):
        await message.answer("🛠 Admin menyusiga xush kelibsiz:", reply_markup=admin_menu())
        return

    if not BOT_ACTIVE:
        await message.answer("⚠️ Botda profilaktika/texnik ishlar olib borilmoqda. Birozdan so'ng urinib ko'ring!")
        return

    # Obunani tekshirish
    unsubbed = await check_subscribes(message.from_user.id)
    if unsubbed:
        ikb = []
        for idx, (_, link) in enumerate(unsubbed, 1):
            ikb.append([InlineKeyboardButton(text=f"📢 {idx}-Kanalga a'zo bo'lish", url=link)])
        ikb.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")])
        await message.answer("⚠️ Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling:", reply_markup=InlineKeyboardMarkup(inline_keyboard=ikb))
        return

    await message.answer("Assalomu alaykum! Anime kodini yuboring:")

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(call: types.CallbackQuery):
    unsubbed = await check_subscribes(call.from_user.id)
    if not unsubbed:
        await call.message.delete()
        await call.message.answer("✅ Rahmat! Obuna tasdiqlandi. Endi anime kodini yuborishingiz mumkin:")
    else:
        await call.answer("❌ Siz hali barcha kanallarga a'zo bo'lmadingiz!", show_alert=True)

# --- ⚙️ BOT HOLATINI BOSHQARISH ---
@dp.message(F.text == "⚙️ Bot holatini boshqarish")
async def toggle_bot_status(message: types.Message):
    if not await is_admin(message.from_user.id): return
    global BOT_ACTIVE
    BOT_ACTIVE = not BOT_ACTIVE
    status = "🟢 FAOL (ON)" if BOT_ACTIVE else "🔴 TO'XTATILGAN (OFF)"
    await message.answer(f"⚙️ Bot holati o'zgartirildi!\nHozirgi holat: **{status}**", parse_mode="Markdown")

# --- 📢 KANALLAR BOSHQARUVI ---
@dp.message(F.text == "📢 Kanallar boshqaruvi")
async def channels_mgmt(message: types.Message):
    if not await is_admin(message.from_user.id): return
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT channel_id, username, invite_link FROM channels") as cursor:
            ch_list = await cursor.fetchall()
    
    text = "📢 **Majburiy kanallar ro'yxati:**\n\n"
    ikb = []
    if ch_list:
        for ch_id, username, link in ch_list:
            text += f"🔹 ID: `{ch_id}` | Username: {username} | Link: {link}\n"
            ikb.append([InlineKeyboardButton(text=f"❌ O'chirish {ch_id}", callback_data=f"delchan_{ch_id}")])
    else:
        text += "*(Hozircha majburiy kanallar yo'q)*\n"
    
    ikb.append([InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="add_channel")])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=ikb), parse_mode="Markdown")

@dp.callback_query(F.data == "add_channel")
async def add_channel_start(call: types.CallbackQuery, state: FSMContext):
    if not await is_admin(call.from_user.id): return
    await state.set_state(ChannelFSM.channel_id)
    await call.message.answer(
        "⚠️ **MUHIM:** Davom etishdan oldin botni kanalingizga **ADMIN** qilib tayinlang va post joylash huquqini bering!\n\n"
        "1️⃣ Kanalning **ID**sini kiriting (Masalan: `-100123456789`):",
        parse_mode="Markdown"
    )

@dp.message(ChannelFSM.channel_id)
async def add_channel_id(message: types.Message, state: FSMContext):
    await state.update_data(channel_id=message.text.strip())
    await state.set_state(ChannelFSM.username)
    await message.answer("2️⃣ Endi kanalning **Username**ini kiriting (Masalan: `@myanimechannel`):")

@dp.message(ChannelFSM.username)
async def add_channel_username(message: types.Message, state: FSMContext):
    username = message.text.strip()
    if not username.startswith("@"):
        username = f"@{username}"
    await state.update_data(username=username)
    await state.set_state(ChannelFSM.invite_link)
    await message.answer("3️⃣ Endi kanalning **Invite Linki (Taklif havolasi)**ni kiriting (Masalan: `https://t.me/+abc...`):")

@dp.message(ChannelFSM.invite_link)
async def add_channel_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ch_id = int(data['channel_id'])
    username = data['username']
    link = message.text.strip()
    
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("INSERT OR REPLACE INTO channels (channel_id, username, invite_link) VALUES (?, ?, ?)", (ch_id, username, link))
        await conn.commit()
    
    await message.answer("✅ Kanal muvaffaqiyatli saqlandi!")
    await state.clear()

@dp.callback_query(F.data.startswith("delchan_"))
async def del_channel(call: types.CallbackQuery):
    if not await is_admin(call.from_user.id): return
    ch_id = int(call.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("DELETE FROM channels WHERE channel_id = ?", (ch_id,))
        await conn.commit()
    await call.answer("🗑 Kanal o'chirildi!", show_alert=True)
    await call.message.delete()

# --- 🗑 ANIME O'CHIRISH ---
@dp.message(F.text == "🗑 Anime o‘chirish")
async def delete_anime_start(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id): return
    await state.set_state(DeleteAnimeFSM.code)
    await message.answer("O'chirmoqchi bo'lgan animening **KODINI** kiriting:")

@dp.message(DeleteAnimeFSM.code)
async def delete_anime_confirm(message: types.Message, state: FSMContext):
    code = message.text.strip()
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("DELETE FROM anime WHERE code = ?", (code,))
        await conn.execute("DELETE FROM episodes WHERE anime_code = ?", (code,))
        await conn.commit()
    await message.answer(f"🗑 Kodi `{code}` bo'lgan anime va uning barcha qismlari bazadan o'chirildi!", parse_mode="Markdown")
    await state.clear()

# --- 🤖 AVTO-KANAL TUSHUNTIRISH ---
@dp.message(F.text == "🤖 Avto-kanal sozlash")
async def auto_channel_info(message: types.Message):
    if not await is_admin(message.from_user.id): return
    text = (
        "🤖 **Avto-kanal sozlamalari haqida:**\n\n"
        "1. Botni kanalingizga **ADMIN** qiling.\n"
        "2. **'📢 Kanallar boshqaruvi'** bo'limidan kanal ID, Username va Invite Linkini saqlang.\n"
        "3. **'➕ Anime qo'shish'** yoki **'➕ Qism qo'shish'** tugmalari orqali ma'lumot yuklasangiz, bot avtomatik ravishda kanalingizga e'lon (post) joylab beradi!"
    )
    await message.answer(text, parse_mode="Markdown")

# --- ➕ ANIME QO'SHISH VA AVTO-POSTING ---
@dp.message(F.text == "➕ Anime qo‘shish")
async def add_anime_start(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id): return
    await state.set_state(AnimeFSM.title)
    await message.answer("Anime nomini kiriting:")

@dp.message(AnimeFSM.title)
async def add_anime_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(AnimeFSM.code)
    await message.answer("Anime uchun unikal **KOD** kiriting (masalan: `101`):")

@dp.message(AnimeFSM.code)
async def add_anime_code(message: types.Message, state: FSMContext):
    data = await state.get_data()
    code = message.text.strip()
    title = data['title']
    
    async with aiosqlite.connect(DB_NAME) as conn:
        try:
            await conn.execute("INSERT INTO anime (code, title) VALUES (?, ?)", (code, title))
            await conn.commit()
            
            async with conn.execute("SELECT channel_id, username FROM channels") as cursor:
                channels = await cursor.fetchall()
                
            await message.answer(f"✅ Anime saqlandi!\n\nNomi: {title}\nKodi: `{code}`", parse_mode="Markdown")
            
            # Kanalga yangi anime haqida avto-post yuborish
            bot_info = await bot.get_me()
            post_text = (
                f"🔥 **YANGI ANIME QO'SHILDI!**\n\n"
                f"🎬 **Nomi:** {title}\n"
                f"🔑 **Kodi:** `{code}`\n\n"
                f"🍿 *Qismlar yuklanmoqda! Tomosha qilish uchun botimizga kiring:*"
            )
            
            for ch_id, ch_username in channels:
                ikb_buttons = [
                    [InlineKeyboardButton(text="🎬 Botga o'tish", url=f"https://t.me/{bot_info.username}?start=start")]
                ]
                if ch_username:
                    clean_username = ch_username.replace("@", "")
                    ikb_buttons.append([InlineKeyboardButton(text="📢 Asosiy Kanalimiz", url=f"https://t.me/{clean_username}")])
                    
                ikb = InlineKeyboardMarkup(inline_keyboard=ikb_buttons)
                try:
                    await bot.send_message(chat_id=ch_id, text=post_text, reply_markup=ikb, parse_mode="Markdown")
                except Exception as e:
                    print(f"Kanalga post joylashda xatolik ({ch_id}): {e}")

        except Exception as e:
            await message.answer(f"❌ Xatolik: Bunday kod bor! ({e})")
            
    await state.clear()

# --- ➕ QISM QO'SHISH VA AVTO-POSTING ---
@dp.message(F.text == "➕ Qism qo‘shish")
async def add_ep_start(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id): return
    await state.set_state(EpisodeFSM.code)
    await message.answer("Qaysi anime kodiga qism qo'shmoqchisiz? Kodni kiriting:")

@dp.message(EpisodeFSM.code)
async def add_ep_code(message: types.Message, state: FSMContext):
    code = message.text.strip()
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT title FROM anime WHERE code = ?", (code,)) as cursor:
            anime = await cursor.fetchone()
            if not anime:
                await message.answer("❌ Bunday kodli anime topilmadi!")
                return
    await state.update_data(code=code, anime_title=anime[0])
    await state.set_state(EpisodeFSM.ep_num)
    await message.answer("Qism raqamini kiriting (masalan: `1`):")

@dp.message(EpisodeFSM.ep_num)
async def add_ep_num(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return
    await state.update_data(ep_num=int(message.text))
    await state.set_state(EpisodeFSM.file_id)
    await message.answer("Endi ushbu qismning **VIDEOSINI** yuboring:")

@dp.message(EpisodeFSM.file_id, F.video)
async def add_ep_file(message: types.Message, state: FSMContext):
    await state.update_data(file_id=message.video.file_id)
    await state.set_state(EpisodeFSM.photo)
    await message.answer("📸 Endi ushbu anime uchun **POSTER (RASM)** yuboring (Kanalga avto-post qilish uchun):")

@dp.message(EpisodeFSM.photo, F.photo)
async def add_ep_photo_and_post(message: types.Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    data = await state.get_data()
    
    code = data['code']
    ep_num = data['ep_num']
    file_id = data['file_id']
    title = data['anime_title']

    # Bazaga saqlash
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("INSERT INTO episodes (anime_code, ep_num, file_id) VALUES (?, ?, ?)", 
                           (code, ep_num, file_id))
        await conn.commit()
        
        async with conn.execute("SELECT channel_id, username FROM channels") as cursor:
            channels = await cursor.fetchall()

    await message.answer(f"✅ Qism saqlandi!\n\nAnime: {title}\nKodi: `{code}`\nQism: {ep_num}", parse_mode="Markdown")

    # Kanalga avto-post qilish
    bot_info = await bot.get_me()
    post_text = (
        f"🎬 **{title}**\n\n"
        f"🔹 **Qism:** {ep_num}-qism\n"
        f"🔑 **Anime kodi:** `{code}`\n\n"
        f"🍿 *Ushbu qismni tomosha qilish uchun pastdagi tugmani bosing va botga kodingizni yuboring!*"
    )

    for ch_id, ch_username in channels:
        ikb_buttons = [
            [InlineKeyboardButton(text="🎬 Botda tomosha qilish", url=f"https://t.me/{bot_info.username}?start=start")]
        ]
        if ch_username:
            clean_username = ch_username.replace("@", "")
            ikb_buttons.append([InlineKeyboardButton(text="📢 Asosiy Kanalimiz", url=f"https://t.me/{clean_username}")])
            
        ikb = InlineKeyboardMarkup(inline_keyboard=ikb_buttons)

        try:
            await bot.send_photo(chat_id=ch_id, photo=photo_id, caption=post_text, reply_markup=ikb, parse_mode="Markdown")
        except Exception as e:
            print(f"Kanalga post joylashda xatolik ({ch_id}): {e}")

    await state.clear()

# --- 👤 ADMINLAR BOSHQARUVI VA STATISTIKA ---
@dp.message(F.text == "📊 Statistika")
async def stats_cmd(message: types.Message):
    if not await is_admin(message.from_user.id): return
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT COUNT(*) FROM users") as c1: u = (await c1.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM anime") as c2: a = (await c2.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM episodes") as c3: e = (await c3.fetchone())[0]
    await message.answer(f"📊 **Statistika:**\n\n👥 Foydalanuvchilar: {u}\n🎬 Animelar: {a}\n📹 Qismlar: {e}", parse_mode="Markdown")

@dp.message(F.text == "👤 Adminlar boshqaruvi")
async def admins_mgmt(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT user_id FROM admins") as cursor: admins = await cursor.fetchall()
    text = f"👤 **Adminlar:**\n👑 Owner: `{ADMIN_ID}`\n"
    ikb = []
    for (adm_id,) in admins:
        ikb.append([InlineKeyboardButton(text=f"❌ O'chirish {adm_id}", callback_data=f"deladmin_{adm_id}")])
    ikb.append([InlineKeyboardButton(text="➕ Admin qo'shish", callback_data="add_new_admin")])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=ikb), parse_mode="Markdown")

@dp.callback_query(F.data == "add_new_admin")
async def add_admin_start(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    await state.set_state(AdminFSM.add_user_id)
    await call.message.answer("Yangi admin Telegram **ID**sini yuboring:")

@dp.message(AdminFSM.add_user_id)
async def add_admin_save(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return
    new_id = int(message.text.strip())
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (new_id,))
        await conn.commit()
    await message.answer(f"✅ Admin qo'shildi: `{new_id}`", parse_mode="Markdown")
    await state.clear()

@dp.callback_query(F.data.startswith("deladmin_"))
async def del_admin(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    target_id = int(call.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("DELETE FROM admins WHERE user_id = ?", (target_id,))
        await conn.commit()
    await call.answer("O'chirildi!")
    await call.message.delete()

# --- QIDIRUV (FOYDALANUVCHI UCHUN) ---
@dp.message(F.text & ~F.text.startswith("/"))
async def search_anime(message: types.Message):
    if not BOT_ACTIVE and not await is_admin(message.from_user.id):
        await message.answer("⚠️ Botda profilaktika ketmoqda.")
        return

    unsubbed = await check_subscribes(message.from_user.id)
    if unsubbed and not await is_admin(message.from_user.id):
        await start_cmd(message)
        return

    code = message.text.strip()
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT title FROM anime WHERE code = ?", (code,)) as cursor:
            anime = await cursor.fetchone()
        if not anime: return
        async with conn.execute("SELECT ep_num FROM episodes WHERE anime_code = ? ORDER BY ep_num ASC", (code,)) as cursor:
            episodes = await cursor.fetchall()

    if not episodes:
        await message.answer(f"🎬 **{anime[0]}** animedan qismlar yo'q.")
        return

    ikb_list, row = [], []
    for (ep_num,) in episodes:
        row.append(InlineKeyboardButton(text=f"{ep_num}-qism", callback_data=f"play_{code}_{ep_num}"))
        if len(row) == 3:
            ikb_list.append(row)
            row = []
    if row: ikb_list.append(row)

    await message.answer(f"🎬 **{anime[0]}**\nQismni tanlang:", reply_markup=InlineKeyboardMarkup(inline_keyboard=ikb_list), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("play_"))
async def play_ep(call: types.CallbackQuery):
    _, code, ep_num = call.data.split("_")
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT file_id FROM episodes WHERE anime_code = ? AND ep_num = ?", (code, int(ep_num))) as cursor:
            res = await cursor.fetchone()
    if res:
        await call.message.answer_video(video=res[0], caption=f"📹 Qism: {ep_num}")
        await call.answer()

async def main():
    logging.basicConfig(level=logging.INFO)
    await init_db()
    await start_background_web_server()
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
