import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, 
    ReplyKeyboardMarkup, KeyboardButton
)
import aiosqlite
import database as db

BOT_TOKEN = os.getenv("BOT_TOKEN", "8890621891:AAFX0yKQ81saY144zaFiBfGmAu75vi4cnmM")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8369095793"))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- FSM States ---
class AnimeFSM(StatesGroup):
    code = State()
    title = State()
    description = State()
    poster = State()

class EpisodeFSM(StatesGroup):
    anime_code = State()
    season = State()
    episode = State()
    file_id = State()

class ChannelFSM(StatesGroup):
    channel_id = State()
    invite_link = State()
    c_type = State()

class AutoChannelFSM(StatesGroup):
    channel_id = State()

class BroadcastFSM(StatesGroup):
    message = State()

# --- Klaviaturalar ---
def admin_menu():
    kb = [
        [KeyboardButton(text="➕ Anime qo‘shish"), KeyboardButton(text="➕ Qism qo‘shish")],
        [KeyboardButton(text="✏️ Anime tahrirlash"), KeyboardButton(text="🗑 Anime o‘chirish")],
        [KeyboardButton(text="📢 Kanallar boshqaruvi"), KeyboardButton(text="🤖 Avto-kanal sozlash")],
        [KeyboardButton(text="🔗 Qo‘shimcha havolalar"), KeyboardButton(text="📊 Statistika")],
        [KeyboardButton(text="📨 Xabar yuborish"), KeyboardButton(text="👮 Adminlarni boshqarish")],
        [KeyboardButton(text="⚙️ Bot holatini boshqarish")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

async def check_subscription(user_id: int) -> bool:
    """Majburiy a'zolikni tekshirish"""
    async with aiosqlite.connect(db.DB_NAME) as conn:
        async with conn.execute("SELECT channel_id FROM channels WHERE type != 'request'") as cursor:
            channels = await cursor.fetchall()
            
    for (ch_id,) in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch_id, user_id=user_id)
            if member.status in ["left", "kicked"]:
                return False
        except Exception:
            continue
    return True

# --- Handlers ---

@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    # Bot statusini tekshirish
    async with aiosqlite.connect(db.DB_NAME) as conn:
        async with conn.execute("SELECT value FROM settings WHERE key='bot_status'") as cursor:
            status = await cursor.fetchone()
            if status and status[0] == "off" and message.from_user.id != ADMIN_ID:
                await message.answer("🛠 Botda vaqtincha texnik ishlar olib borilmoqda. Birozdan so'ng urinib ko'ring.")
                return

        # Userni saqlash
        await conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
        await conn.commit()

    if message.from_user.id == ADMIN_ID:
        await message.answer("🔧 **Boshqaruv paneli:**", reply_markup=admin_menu())
    else:
        # Majburiy obunani tekshirish
        if not await check_subscription(message.from_user.id):
            async with aiosqlite.connect(db.DB_NAME) as conn:
                async with conn.execute("SELECT invite_link FROM channels") as cursor:
                    links = await cursor.fetchall()
            
            ikb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"Kanal {i+1}", url=link[0])] for i, link in enumerate(links)
            ] + [[InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")]])
            
            await message.answer("⚠️ Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling:", reply_markup=ikb)
            return

        await message.answer("👋 Xush kelibsiz! Ko'rmoqchi bo'lgan anime kodini yuboring:")

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(call: types.CallbackQuery):
    if await check_subscription(call.from_user.id):
        await call.message.delete()
        await call.message.answer("✅ Rahmat! Endi anime kodini yuborishingiz mumkin.")
    else:
        await call.answer("❌ Hali barcha kanallarga a'zo bo'lmadingiz!", show_alert=True)

# --- BOT HOLATINI BOSHQARISH ---
@dp.message(F.text == "⚙️ Bot holatini boshqarish")
async def bot_status_menu(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    ikb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 Botni yoqish", callback_data="set_bot_on")],
        [InlineKeyboardButton(text="🔴 Botni o‘chirish", callback_data="set_bot_off")]
    ])
    await message.answer("⚙️ **Bot holatini tanlang:**", reply_markup=ikb)

@dp.callback_query(F.data.startswith("set_bot_"))
async def set_bot_status(call: types.CallbackQuery):
    status = "active" if call.data == "set_bot_on" else "off"
    async with aiosqlite.connect(db.DB_NAME) as conn:
        await conn.execute("UPDATE settings SET value = ? WHERE key = 'bot_status'", (status,))
        await conn.commit()
    await call.message.edit_text(f"✅ Bot holati o'gartirildi: **{status.upper()}**")

# --- ANIME QO'SHISH (FSM) ---
@dp.message(F.text == "➕ Anime qo‘shish")
async def add_anime_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.set_state(AnimeFSM.code)
    await message.answer("Anime uchun unikal **KOD** kiriting (masalan: 105):")

@dp.message(AnimeFSM.code)
async def add_anime_code(message: types.Message, state: FSMContext):
    await state.update_data(code=message.text)
    await state.set_state(AnimeFSM.title)
    await message.answer("Anime **NOMI**ni kiriting:")

@dp.message(AnimeFSM.title)
async def add_anime_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(AnimeFSM.description)
    await message.answer("Anime haqida **TAVSIF** kiriting:")

@dp.message(AnimeFSM.description)
async def add_anime_desc(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    await state.set_state(AnimeFSM.poster)
    await message.answer("Anime **POSTER (rasm)**ini yuboring:")

@dp.message(AnimeFSM.poster, F.photo)
async def add_anime_poster(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photo_id = message.photo[-1].file_id
    
    async with aiosqlite.connect(db.DB_NAME) as conn:
        await conn.execute(
            "INSERT INTO animes (code, title, description, poster_id) VALUES (?, ?, ?, ?)",
            (data['code'], data['title'], data['description'], photo_id)
        )
        await conn.commit()
    
    await message.answer(f"✅ **{data['title']}** muvaffaqiyatli saqlandi!")
    await state.clear()

# --- QISM QO'SHISH & AVTO-POST ---
@dp.message(F.text == "➕ Qism qo‘shish")
async def add_ep_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.set_state(EpisodeFSM.anime_code)
    await message.answer("Qism qo'shiladigan anime **KODI**ni kiriting:")

@dp.message(EpisodeFSM.anime_code)
async def add_ep_code(message: types.Message, state: FSMContext):
    await state.update_data(anime_code=message.text)
    await state.set_state(EpisodeFSM.season)
    await message.answer("Fasl raqamini kiriting (masalan: 1):")

@dp.message(EpisodeFSM.season)
async def add_ep_season(message: types.Message, state: FSMContext):
    await state.update_data(season=int(message.text))
    await state.set_state(EpisodeFSM.episode)
    await message.answer("Qism raqamini kiriting (masalan: 5):")

@dp.message(EpisodeFSM.episode)
async def add_ep_num(message: types.Message, state: FSMContext):
    await state.update_data(episode=int(message.text))
    await state.set_state(EpisodeFSM.file_id)
    await message.answer("Qism **VIDEO**sini yuboring:")

@dp.message(EpisodeFSM.file_id, F.video)
async def add_ep_file(message: types.Message, state: FSMContext):
    data = await state.get_data()
    video_id = message.video.file_id
    
    async with aiosqlite.connect(db.DB_NAME) as conn:
        await conn.execute(
            "INSERT INTO episodes (anime_code, season, episode_num, file_id) VALUES (?, ?, ?, ?)",
            (data['anime_code'], data['season'], data['episode'], video_id)
        )
        await conn.commit()
        
        # Anime ma'lumotlarini olish
        async with conn.execute("SELECT title, poster_id FROM animes WHERE code = ?", (data['anime_code'],)) as cursor:
            anime_info = await cursor.fetchone()
            
        # Avto-kanal sozlamasini olish
        async with conn.execute("SELECT value FROM settings WHERE key='auto_channel'") as cursor:
            auto_ch = await cursor.fetchone()

    await message.answer("✅ Qism bazaga qo'shildi!")

    # 🤖 AVTO-POSTING KANALGA
    if auto_ch and anime_info:
        ch_id = auto_ch[0]
        title, poster_id = anime_info
        
        # Yangi fasl yoki yangi qism posti
        if data['episode'] == 1:
            caption = f"📚 **YANGI FASL!**\n\n🎬 **Anime:** {title}\n🗓 **{data['season']}-Fasl 1-Qism** joylandi!\n\n🤖 Bot orqali to'liq ko'rish."
            try:
                await bot.send_photo(chat_id=ch_id, photo=poster_id, caption=caption)
            except Exception as e:
                logging.error(f"Fasl postida xatolik: {e}")
        else:
            caption = f"🎬 **YANGI QISM!**\n\n🎬 **Anime:** {title}\n▶️ **{data['season']}-Fasl {data['episode']}-Qism** e'lon qilindi!\n\n🤖 Botga kirib tomosha qiling."
            try:
                await bot.send_video(chat_id=ch_id, video=video_id, caption=caption)
            except Exception as e:
                logging.error(f"Qism postida xatolik: {e}")

    await state.clear()

# --- STATISTIKA ---
@dp.message(F.text == "📊 Statistika")
async def show_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    async with aiosqlite.connect(db.DB_NAME) as conn:
        async with conn.execute("SELECT COUNT(*) FROM users") as c1: u_cnt = (await c1.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM animes") as c2: a_cnt = (await c2.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM episodes") as c3: e_cnt = (await c3.fetchone())[0]
        
    await message.answer(
        f"📊 **Ko'p qamrovli statistika:**\n\n"
        f"👤 Foydalanuvchilar: **{u_cnt}** ta\n"
        f"🎬 Animelar: **{a_cnt}** ta\n"
        f"🎞 Qismlar: **{e_cnt}** ta"
    )

# --- AVTO-KANAL ULOVCH ---
@dp.message(F.text == "🤖 Avto-kanal sozlash")
async def auto_channel_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.set_state(AutoChannelFSM.channel_id)
    await message.answer("Anime xabarlari avtomatik tushadigan kanal ID'sini kiriting (Masalan: `@my_anime_channel` yoki `-100123456789`):")

@dp.message(AutoChannelFSM.channel_id)
async def auto_channel_save(message: types.Message, state: FSMContext):
    ch_id = message.text
    async with aiosqlite.connect(db.DB_NAME) as conn:
        await conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('auto_channel', ?)", (ch_id,))
        await conn.commit()
    await message.answer(f"✅ **{ch_id}** avto-posting kanali sifatida biriktirildi!")
    await state.clear()

# --- KOD BO'YICHA ANIME QIDIRISH ---
@dp.message(F.text)
async def search_anime(message: types.Message):
    code = message.text.strip()
    async with aiosqlite.connect(db.DB_NAME) as conn:
        async with conn.execute("SELECT id, title, description, poster_id FROM animes WHERE code = ?", (code,)) as cursor:
            anime = await cursor.fetchone()
            
    if anime:
        _, title, desc, poster = anime
        async with aiosqlite.connect(db.DB_NAME) as conn:
            async with conn.execute("SELECT DISTINCT season FROM episodes WHERE anime_code = ?", (code,)) as cursor:
                seasons = await cursor.fetchall()

        ikb_list = [[InlineKeyboardButton(text=f"{s[0]}-Fasl", callback_data=f"season_{code}_{s[0]}")] for s in seasons]
        ikb = InlineKeyboardMarkup(inline_keyboard=ikb_list)
        
        await message.answer_photo(photo=poster, caption=f"🎬 **{title}**\n\n📝 {desc}", reply_markup=ikb)
    else:
        await message.answer("❌ Bunday kodli anime topilmadi.")

async def main():
    logging.basicConfig(level=logging.INFO)
    await db.init_db()
    print("Bot ishga tushirildi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
