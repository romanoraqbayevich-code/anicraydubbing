import asyncio
import logging
import os
import aiosqlite
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

# --- BOT SOZLAMALARI ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "8890621891:AAFX0yKQ81saY144zaFiBfGmAu75vi4cnmM")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8369095793"))  # Asosiy admin (Owner) ID si
DB_NAME = "anime_bot.db"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

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

# --- BAZA BILAN ISHLASH ---
async def init_db():
    async with aiosqlite.connect(DB_NAME) as conn:
        # Users
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY
            )
        """)
        # Admins
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY
            )
        """)
        # Anime
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS anime (
                code TEXT PRIMARY KEY,
                title TEXT
            )
        """)
        # Episodes
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                anime_code TEXT,
                ep_num INTEGER,
                file_id TEXT
            )
        """)
        # Channels
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                channel_id INTEGER PRIMARY KEY,
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

# --- KLAVIATURALAR ---
def admin_menu():
    kb = [
        [KeyboardButton(text="➕ Anime qo‘shish"), KeyboardButton(text="➕ Qism qo‘shish")],
        [KeyboardButton(text="🗑 Anime o‘chirish"), KeyboardButton(text="📢 Kanallar boshqaruvi")],
        [KeyboardButton(text="👤 Adminlar boshqaruvi"), KeyboardButton(text="🤖 Avto-kanal sozlash")],
        [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="⚙️ Bot holatini boshqarish")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- RENDER KEEP-ALIVE SERVER (24/7) ---
async def health_check(request):
    return web.Response(text="Bot is running active 24/7!", status=200)

async def start_background_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Web server started on port {port}")

# --- HANDLERLAR ---

@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
        await conn.commit()

    if await is_admin(message.from_user.id):
        await message.answer("Assalomu alaykum, Admin! Boshqaruv menyusi:", reply_markup=admin_menu())
    else:
        await message.answer("Assalomu alaykum! Anime kodini yuboring:")

# --- ADMINLAR BOSHQARUVI (QO'SHISH / O'CHIRISH) ---

@dp.message(F.text == "👤 Adminlar boshqaruvi")
async def admins_management(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⚠️ Adminlarni faqat botning asosiy egasi boshqara oladi!")
        return

    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT user_id FROM admins") as cursor:
            admins = await cursor.fetchall()

    text = f"👤 **Bot Adminlari Boshqaruvi:**\n\n👑 **Asosiy Admin (Owner):** `{ADMIN_ID}`\n\n"
    ikb_list = []

    if admins:
        text += "🛠 **Yordamchi Adminlar:**\n"
        for (adm_id,) in admins:
            text += f"🔹 Admin ID: `{adm_id}`\n"
            ikb_list.append([InlineKeyboardButton(text=f"❌ O'chirish: {adm_id}", callback_data=f"deladmin_{adm_id}")])
    else:
        text += "*(Hozircha yordamchi adminlar yo'q)*\n"

    ikb_list.append([InlineKeyboardButton(text="➕ Yangi admin qo'shish", callback_data="add_new_admin")])
    ikb = InlineKeyboardMarkup(inline_keyboard=ikb_list)

    await message.answer(text, reply_markup=ikb, parse_mode="Markdown")

@dp.callback_query(F.data == "add_new_admin")
async def add_admin_start(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        await call.answer("Faqat asosiy admin bajarishi mumkin!", show_alert=True)
        return
    await state.set_state(AdminFSM.add_user_id)
    await call.message.answer("Yangi admin qilmoqchi bo'lgan foydalanuvchining **Telegram ID**sini yuboring:")

@dp.message(AdminFSM.add_user_id)
async def add_admin_save(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ ID faqat raqamlardan iborat bo'lishi kerak! Qayta kiriting:")
        return

    new_admin_id = int(message.text.strip())
    
    if new_admin_id == ADMIN_ID:
        await message.answer("Siz allachachon asosiy adminsiz!")
        await state.clear()
        return

    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (new_admin_id,))
        await conn.commit()

    await message.answer(f"✅ ` {new_admin_id} ` IDli foydalanuvchi Adminlar ro'yxatiga qo'shildi!", parse_mode="Markdown")
    await state.clear()

@dp.callback_query(F.data.startswith("deladmin_"))
async def delete_admin(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("Faqat asosiy admin bajarishi mumkin!", show_alert=True)
        return

    target_id = int(call.data.split("_")[1])
    
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("DELETE FROM admins WHERE user_id = ?", (target_id,))
        await conn.commit()

    await call.answer("🗑 Admin o'chirib tashlandi!", show_alert=True)
    await call.message.delete()
    await call.message.answer(f"❌ `{target_id}` IDli admin o'chirildi.", parse_mode="Markdown")

# --- STATISTIKA ---
@dp.message(F.text == "📊 Statistika")
async def stats_cmd(message: types.Message):
    if not await is_admin(message.from_user.id):
        return
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT COUNT(*) FROM users") as c1:
            u_count = (await c1.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM anime") as c2:
            a_count = (await c2.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM episodes") as c3:
            e_count = (await c3.fetchone())[0]

    await message.answer(f"📊 **Bot Statistikasi:**\n\n👥 Foydalanuvchilar: {u_count}\n🎬 Anime seriallar: {a_count}\n📹 Jami qismlar: {e_count}", parse_mode="Markdown")

# --- ANIME QO'SHISH ---
@dp.message(F.text == "➕ Anime qo‘shish")
async def add_anime_start(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    await state.set_state(AnimeFSM.title)
    await message.answer("Anime nomini kiriting:")

@dp.message(AnimeFSM.title)
async def add_anime_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(AnimeFSM.code)
    await message.answer("Ushbu anime uchun unikal KOD kiriting (masalan: `101`):")

@dp.message(AnimeFSM.code)
async def add_anime_code(message: types.Message, state: FSMContext):
    data = await state.get_data()
    code = message.text.strip()
    title = data['title']

    async with aiosqlite.connect(DB_NAME) as conn:
        try:
            await conn.execute("INSERT INTO anime (code, title) VALUES (?, ?)", (code, title))
            await conn.commit()
            await message.answer(f"✅ Anime saqlandi!\n\nNomi: {title}\nKodi: `{code}`", parse_mode="Markdown")
        except Exception as e:
            await message.answer(f"❌ Xatolik: Ushbu kod allaqachon mavjud bo'lishi mumkin! ({e})")
    await state.clear()

# --- QISM QO'SHISH ---
@dp.message(F.text == "➕ Qism qo‘shish")
async def add_ep_start(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    await state.set_state(EpisodeFSM.code)
    await message.answer("Qaysi anime kodiga qism qo'shmoqchisiz? Kodni kiriting:")

@dp.message(EpisodeFSM.code)
async def add_ep_code(message: types.Message, state: FSMContext):
    code = message.text.strip()
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT title FROM anime WHERE code = ?", (code,)) as cursor:
            anime = await cursor.fetchone()
            if not anime:
                await message.answer("❌ Bunday kodli anime topilmadi! Qayta kiriting:")
                return
    await state.update_data(code=code)
    await state.set_state(EpisodeFSM.ep_num)
    await message.answer("Nechanchi qismligini kiriting (masalan: `1`):")

@dp.message(EpisodeFSM.ep_num)
async def add_ep_num(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Qism raqami faqat son bo'lishi kerak:")
        return
    await state.update_data(ep_num=int(message.text))
    await state.set_state(EpisodeFSM.file_id)
    await message.answer("Endi ushbu qismning VIDEOSINI yuboring:")

@dp.message(EpisodeFSM.file_id, F.video)
async def add_ep_file(message: types.Message, state: FSMContext):
    file_id = message.video.file_id
    data = await state.get_data()
    
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("INSERT INTO episodes (anime_code, ep_num, file_id) VALUES (?, ?, ?)", 
                           (data['code'], data['ep_num'], file_id))
        await conn.commit()

    await message.answer(f"✅ Qism saqlandi!\nAnime kodi: `{data['code']}`\nQism: {data['ep_num']}", parse_mode="Markdown")
    await state.clear()

# --- ANIME QIDIRISH (FOYDALANUVCHILAR UCHUN) ---
@dp.message(F.text & ~F.text.startswith("/"))
async def search_anime(message: types.Message):
    code = message.text.strip()
    
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT title FROM anime WHERE code = ?", (code,)) as cursor:
            anime = await cursor.fetchone()

        if not anime:
            return  # Admin menyusidagi boshqa tugmalar bo'lsa javob bermaydi

        async with conn.execute("SELECT ep_num, file_id FROM episodes WHERE anime_code = ? ORDER BY ep_num ASC", (code,)) as cursor:
            episodes = await cursor.fetchall()

    if not episodes:
        await message.answer(f"🎬 **{anime[0]}** animedan qismlar topilmadi.")
        return

    text = f"🎬 **{anime[0]}**\n\nQismni tanlang:"
    ikb_list = []
    row = []
    for ep_num, file_id in episodes:
        row.append(InlineKeyboardButton(text=f"{ep_num}-qism", callback_data=f"play_{code}_{ep_num}"))
        if len(row) == 3:
            ikb_list.append(row)
            row = []
    if row:
        ikb_list.append(row)

    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=ikb_list), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("play_"))
async def play_episode(call: types.CallbackQuery):
    _, code, ep_num = call.data.split("_")
    
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT file_id FROM episodes WHERE anime_code = ? AND ep_num = ?", (code, int(ep_num))) as cursor:
            res = await cursor.fetchone()

    if res:
        await call.message.answer_video(video=res[0], caption=f"📹 Qism: {ep_num}")
        await call.answer()
    else:
        await call.answer("❌ Video topilmadi!", show_alert=True)

# --- BOTNI ISHGA TUSHIRISH ---
async def main():
    logging.basicConfig(level=logging.INFO)
    await init_db()
    
    # 24/7 Render serverini ishga tushirish
    await start_background_web_server()
    
    print("Bot muvaffaqiyatli ishga tushdi...")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
