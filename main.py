import logging
import asyncio
import aiosqlite
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# ----------------- SOZLAMALAR -----------------
TOKEN = "8890621891:AAFX0yKQ81saY144zaFiBfGmAu75vi4cnmM"  # Bot tokeningizni kiriting
ADMIN_ID = 8369095793  # O'zingizning Telegram ID'ingizni kiriting
DB_NAME = "anime_bot.db"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ----------------- FSM STATES -----------------
class AddAnime(StatesGroup):
    code = State()
    part = State()
    video = State()
    poster = State()

class AddChannel(StatesGroup):
    channel_id = State()
    username = State()
    invite_link = State()

class Broadcast(StatesGroup):
    message = State()

# ----------------- BAZA BILAN ISHLASH -----------------
async def init_db():
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS anime (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                part TEXT,
                video_id TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                channel_id INTEGER PRIMARY KEY,
                username TEXT,
                invite_link TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY
            )
        """)
        await conn.commit()

# ----------------- TUGMALAR (KEYBOARDS) -----------------
def admin_keyboard():
    kb = [
        [KeyboardButton(text="➕ Qism qo'shish"), KeyboardButton(text="📢 Kanallar boshqaruvi")],
        [KeyboardButton(text="📣 Reklama yuborish"), KeyboardButton(text="📊 Statistika")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def channel_manage_keyboard():
    kb = [
        [KeyboardButton(text="➕ Kanal qo'shish"), KeyboardButton(text="🗑 Kanal o'chirish")],
        [KeyboardButton(text="📜 Kanallar ro'yxati"), KeyboardButton(text="⬅️ Orqaga")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# ----------------- MAJBURAN OBUNA TEKSHIRISH -----------------
async def check_subscribes(user_id: int):
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT channel_id, invite_link FROM channels") as cursor:
            channels = await cursor.fetchall()
            
    unsubbed = []
    for ch_id, link in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch_id, user_id=user_id)
            if member.status in ["left", "kicked"]:
                unsubbed.append((ch_id, link))
        except Exception:
            # Bot reklama kanalida/guruhida admin bo'lmasa xatolik bermaydi
            pass
            
    return unsubbed

async def get_sub_keyboard(unsubbed):
    buttons = []
    for i, (_, link) in enumerate(unsubbed, 1):
        buttons.append([InlineKeyboardButton(text=f"📢 {i}-Kanalga obuna bo'lish", url=link)])
    buttons.append([InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ----------------- HANDLERLAR -----------------

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
        await conn.commit()

    unsubbed = await check_subscribes(message.from_user.id)
    if unsubbed:
        kb = await get_sub_keyboard(unsubbed)
        await message.answer("⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:", reply_markup=kb)
        return

    if message.from_user.id == ADMIN_ID:
        await message.answer("Xush kelibsiz, Admin!", reply_markup=admin_keyboard())
    else:
        await message.answer("Xush kelibsiz! Anime ko'rish uchun anime kodini yuboring (Masalan: 101):")

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(call: types.CallbackQuery):
    unsubbed = await check_subscribes(call.from_user.id)
    if unsubbed:
        await call.answer("❌ Hali barcha kanallarga obuna bo'lmadingiz!", show_alert=True)
    else:
        await call.message.delete()
        await call.message.answer("✅ Obuna tasdiqlandi! Endi anime kodini yuborishingiz mumkin:")

# --- ANIME QIDIRUV ---
@dp.message(F.text & ~F.text.startswith("/"))
async def search_anime(message: types.Message):
    if message.from_user.id == ADMIN_ID and message.text in ["➕ Qism qo'shish", "📢 Kanallar boshqaruvi", "📣 Reklama yuborish", "📊 Statistika", "➕ Kanal qo'shish", "🗑 Kanal o'chirish", "📜 Kanallar ro'yxati", "⬅️ Orqaga"]:
        return

    unsubbed = await check_subscribes(message.from_user.id)
    if unsubbed:
        kb = await get_sub_keyboard(unsubbed)
        await message.answer("⚠️ Botdan foydalanish uchun kanallarga obuna bo'ling:", reply_markup=kb)
        return

    code = message.text.strip()
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT part, video_id FROM anime WHERE code = ?", (code,)) as cursor:
            results = await cursor.fetchall()

    if not results:
        await message.answer("❌ Bu kod bo'yicha hech qanday anime topilmadi.")
        return

    for part, video_id in results:
        await message.answer_video(video=video_id, caption=f"🎬 Anime kodi: {code}\n🎞 Qism: {part}\n\n🤖 Bot: @{ (await bot.get_me()).username }")

# --- ADMIN PANEL ---
@dp.message(F.text == "⬅️ Orqaga", F.from_user.id == ADMIN_ID)
async def back_to_admin(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Bosh menyu:", reply_markup=admin_keyboard())

@dp.message(F.text == "📊 Statistika", F.from_user.id == ADMIN_ID)
async def show_stats(message: types.Message):
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT COUNT(*) FROM users") as c1:
            users_count = (await c1.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM anime") as c2:
            anime_count = (await c2.fetchone())[0]

    await message.answer(f"📊 **Bot statistikasi:**\n\n👤 Foydalanuvchilar: {users_count} ta\n🎬 Yuklangan animelar: {anime_count} ta")

# --- QISM QO'SHISH VA AVTO-POST ---
@dp.message(F.text == "➕ Qism qo'shish", F.from_user.id == ADMIN_ID)
async def add_anime_start(message: types.Message, state: FSMContext):
    await state.set_state(AddAnime.code)
    await message.answer("Anime kodini kiriting (Masalan: 101):")

@dp.message(AddAnime.code)
async def add_anime_code(message: types.Message, state: FSMContext):
    await state.update_data(code=message.text.strip())
    await state.set_state(AddAnime.part)
    await message.answer("Qism raqamini kiriting (Masalan: 1):")

@dp.message(AddAnime.part)
async def add_anime_part(message: types.Message, state: FSMContext):
    await state.update_data(part=message.text.strip())
    await state.set_state(AddAnime.video)
    await message.answer("Anime videosini yuboring:")

@dp.message(AddAnime.video, F.video)
async def add_anime_video(message: types.Message, state: FSMContext):
    await state.update_data(video_id=message.video.file_id)
    await state.set_state(AddAnime.poster)
    await message.answer("📸 Endi ushbu qism uchun POSTER (Rasm) yuboring:")

@dp.message(AddAnime.poster, F.photo)
async def add_anime_poster(message: types.Message, state: FSMContext):
    data = await state.get_data()
    code = data['code']
    part = data['part']
    video_id = data['video_id']
    poster_id = message.photo[-1].file_id

    # Bazaga saqlash
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("INSERT INTO anime (code, part, video_id) VALUES (?, ?, ?)", (code, part, video_id))
        await conn.commit()

    await message.answer("✅ Anime muvaffaqiyatli saqlandi! Avto-post yuborilmoqda...")

    # AVTO-POST YUBORISH
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT channel_id FROM channels") as cursor:
            channels = await cursor.fetchall()

    bot_info = await bot.get_me()
    post_text = f"🔥 **Yangi Qism Joylandi!**\n\n🎬 Anime kodi: `{code}`\n🎞 Qism: `{part}`\n\n👇 Videoni tomosha qilish uchun botga kiring:"
    btn = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Videoni ko'rish", url=f"https://t.me/{bot_info.username}?start={code}")]
    ])

    for (ch_id,) in channels:
        try:
            await bot.send_photo(chat_id=ch_id, photo=poster_id, caption=post_text, reply_markup=btn, parse_mode="Markdown")
        except Exception as e:
            print(f"Avto-post xatosi ({ch_id}): {e}")

    await state.clear()

# --- KANALLAR BOSHOARUVI ---
@dp.message(F.text == "📢 Kanallar boshqaruvi", F.from_user.id == ADMIN_ID)
async def channel_manage(message: types.Message):
    await message.answer("Kanallar boshqaruvi bo'limi:", reply_markup=channel_manage_keyboard())

@dp.message(F.text == "➕ Kanal qo'shish", F.from_user.id == ADMIN_ID)
async def add_channel_start(message: types.Message, state: FSMContext):
    await state.set_state(AddChannel.channel_id)
    await message.answer("Kanal yoki Guruh ID-sini kiriting (Masalan: -100123456789):")

@dp.message(AddChannel.channel_id)
async def add_channel_id(message: types.Message, state: FSMContext):
    await state.update_data(channel_id=int(message.text.strip()))
    await state.set_state(AddChannel.username)
    await message.answer("Kanal username-ini kiriting (Masalan: @kanal_nomi):")

@dp.message(AddChannel.username)
async def add_channel_username(message: types.Message, state: FSMContext):
    await state.update_data(username=message.text.strip())
    await state.set_state(AddChannel.invite_link)
    await message.answer("Kanal taklif havolasini (invite link) kiriting:")

@dp.message(AddChannel.invite_link)
async def add_channel_link(message: types.Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("INSERT OR REPLACE INTO channels (channel_id, username, invite_link) VALUES (?, ?, ?)",
                           (data['channel_id'], data['username'], message.text.strip()))
        await conn.commit()

    await message.answer("✅ Kanal muvaffaqiyatli qo'shildi!", reply_markup=channel_manage_keyboard())
    await state.clear()

# ----------------- MAIN RUN -----------------
async def main():
    await init_db()
    print("Bot muvaffaqiyatli ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
