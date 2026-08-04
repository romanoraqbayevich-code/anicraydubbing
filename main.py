import asyncio
import logging
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, 
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
import aiosqlite
import database as db

BOT_TOKEN = os.getenv("BOT_TOKEN", "8890621891:AAFX0yKQ81saY144zaFiBfGmAu75vi4cnmM")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8369095793"))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- Render Uxlab Qolmasligi Uchun Web Server ---
async def handle_ping(request):
    return web.Response(text="Anime Bot Is Active!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

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

class AutoChannelFSM(StatesGroup):
    channel_id = State()

class DeleteFSM(StatesGroup):
    code = State()

class BroadcastFSM(StatesGroup):
    text = State()

# --- Klaviaturalar ---
def admin_menu():
    kb = [
        [KeyboardButton(text="➕ Anime qo‘shish"), KeyboardButton(text="➕ Qism qo‘shish")],
        [KeyboardButton(text="🗑 Anime o‘chirish"), KeyboardButton(text="📢 Kanallar boshqaruvi")],
        [KeyboardButton(text="🤖 Avto-kanal sozlash"), KeyboardButton(text="📊 Statistika")],
        [KeyboardButton(text="📨 Xabar yuborish"), KeyboardButton(text="⚙️ Bot holatini boshqarish")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

async def is_admin(user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True
    async with aiosqlite.connect(db.DB_NAME) as conn:
        async with conn.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone() is not None

async def check_subscription(user_id: int) -> bool:
    async with aiosqlite.connect(db.DB_NAME) as conn:
        async with conn.execute("SELECT channel_id FROM channels") as cursor:
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
            if status and status[0] == "off" and not await is_admin(message.from_user.id):
                await message.answer("🛠 Botda vaqtincha profilaktika ishlari olib borilmoqda.")
                return

        await conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
        await conn.commit()

    if await is_admin(message.from_user.id):
        await message.answer("🔧 **Boshqaruv paneli:**", reply_markup=admin_menu())
    else:
        if not await check_subscription(message.from_user.id):
            async with aiosqlite.connect(db.DB_NAME) as conn:
                async with conn.execute("SELECT invite_link FROM channels") as cursor:
                    links = await cursor.fetchall()
            
            ikb_list = [[InlineKeyboardButton(text=f"📢 {i+1}-Kanal", url=link[0])] for i, link in enumerate(links)]
            ikb_list.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")])
            ikb = InlineKeyboardMarkup(inline_keyboard=ikb_list)
            
            await message.answer("⚠️ Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling:", reply_markup=ikb)
            return

        await message.answer("👋 Xush kelibsiz! Ko'rmoqchi bo'lgan anime **KODI**ni yuboring:")

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(call: types.CallbackQuery):
    if await check_subscription(call.from_user.id):
        await call.message.delete()
        await call.message.answer("✅ Rahmat! Endi anime kodini yuborishingiz mumkin.")
    else:
        await call.answer("❌ Hali barcha kanallarga a'zo bo'lmadingiz!", show_alert=True)

# --- BOT HOLATI (YOQISH / O'CHIRISH) ---
@dp.message(F.text == "⚙️ Bot holatini boshqarish")
async def bot_status_menu(message: types.Message):
    if not await is_admin(message.from_user.id): return
    ikb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 Botni Yoqish", callback_data="set_bot_active")],
        [InlineKeyboardButton(text="🔴 Botni O'chirish", callback_data="set_bot_off")]
    ])
    await message.answer("⚙️ **Bot holatini tanlang:**", reply_markup=ikb)

@dp.callback_query(F.data.startswith("set_bot_"))
async def set_bot_status(call: types.CallbackQuery):
    status = "active" if call.data == "set_bot_active" else "off"
    async with aiosqlite.connect(db.DB_NAME) as conn:
        await conn.execute("UPDATE settings SET value = ? WHERE key = 'bot_status'", (status,))
        await conn.commit()
    await call.message.edit_text(f"✅ Bot holati o'zgartirildi: **{status.upper()}**")

# --- ANIME QO'SHISH ---
@dp.message(F.text == "➕ Anime qo‘shish")
async def add_anime_start(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id): return
    await state.set_state(AnimeFSM.code)
    await message.answer("Anime uchun unikal **KOD** kiriting (masalan: 105):")

@dp.message(AnimeFSM.code)
async def add_anime_code(message: types.Message, state: FSMContext):
    await state.update_data(code=message.text.strip())
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

@dp.message(AnimeFSM.poster)
async def add_anime_poster(message: types.Message, state: FSMContext):
    if not message.photo:
        await message.answer("❌ Iltimos, faqat **RASM** yuboring!")
        return
        
    data = await state.get_data()
    photo_id = message.photo[-1].file_id
    
    try:
        async with aiosqlite.connect(db.DB_NAME) as conn:
            await conn.execute(
                "INSERT INTO animes (code, title, description, poster_id) VALUES (?, ?, ?, ?)",
                (data['code'], data['title'], data['description'], photo_id)
            )
            await conn.commit()
        await message.answer(f"✅ **{data['title']}** (Kodi: `{data['code']}`) saqlandi!")
    except Exception as e:
        await message.answer("❌ Bu kod bazada mavjud! Boshqa kod bilan qaytadan urining.")
    await state.clear()

# --- QISM QO'SHISH VA AVTO-POSTING ---
@dp.message(F.text == "➕ Qism qo‘shish")
async def add_ep_start(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id): return
    await state.set_state(EpisodeFSM.anime_code)
    await message.answer("Qism qo'shiladigan anime **KODI**ni kiriting:")

@dp.message(EpisodeFSM.anime_code)
async def add_ep_code(message: types.Message, state: FSMContext):
    await state.update_data(anime_code=message.text.strip())
    await state.set_state(EpisodeFSM.season)
    await message.answer("Fasl raqamini kiriting (masalan: 1):")

@dp.message(EpisodeFSM.season)
async def add_ep_season(message: types.Message, state: FSMContext):
    await state.update_data(season=int(message.text))
    await state.set_state(EpisodeFSM.episode)
    await message.answer("Qism raqamini kiriting (masalan: 1):")

@dp.message(EpisodeFSM.episode)
async def add_ep_num(message: types.Message, state: FSMContext):
    await state.update_data(episode=int(message.text))
    await state.set_state(EpisodeFSM.file_id)
    await message.answer("Qism **VIDEO**sini yuboring:")

@dp.message(EpisodeFSM.file_id)
async def add_ep_file(message: types.Message, state: FSMContext):
    video_id = None
    if message.video:
        video_id = message.video.file_id
    elif message.document:
        video_id = message.document.file_id
    else:
        await message.answer("❌ Iltimos, **VIDEO** yoki video fayl yuboring!")
        return
    
    data = await state.get_data()
    
    async with aiosqlite.connect(db.DB_NAME) as conn:
        await conn.execute(
            "INSERT INTO episodes (anime_code, season, episode_num, file_id) VALUES (?, ?, ?, ?)",
            (data['anime_code'], data['season'], data['episode'], video_id)
        )
        await conn.commit()
        
        # Anime ma'lumotlarini va Avto-kanalni olish
        async with conn.execute("SELECT title, poster_id FROM animes WHERE code = ?", (data['anime_code'],)) as c1:
            anime_info = await c1.fetchone()
        async with conn.execute("SELECT value FROM settings WHERE key='auto_channel'") as c2:
            auto_ch = await c2.fetchone()

    await message.answer(f"✅ `{data['anime_code']}` kodli animega {data['season']}-Fasl {data['episode']}-Qism qo'shildi!")

    # 🤖 AVTO-POSTING KANALGA
    if auto_ch and anime_info:
        ch_id = auto_ch[0]
        title, poster_id = anime_info
        
        if data['episode'] == 1:
            caption = f"📚 **YANGI FASL!**\n\n🎬 **Anime:** {title}\n🗓 **{data['season']}-Fasl 1-Qism** tayyor!\n\n🤖 Bot orqali to'liq ko'rish."
            try: await bot.send_photo(chat_id=ch_id, photo=poster_id, caption=caption)
            except Exception: pass
        else:
            caption = f"🎬 **YANGI QISM!**\n\n🎬 **Anime:** {title}\n▶️ **{data['season']}-Fasl {data['episode']}-Qism** e'lon qilindi!\n\n🤖 Botga kirib tomosha qiling."
            try: await bot.send_video(chat_id=ch_id, video=video_id, caption=caption)
            except Exception: pass

    await state.clear()

# --- ANIME O'CHIRISH ---
@dp.message(F.text == "🗑 Anime o‘chirish")
async def del_anime_start(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id): return
    await state.set_state(DeleteFSM.code)
    await message.answer("O'chirmoqchi bo'lgan anime **KODI**ni yuboring:")

@dp.message(DeleteFSM.code)
async def del_anime_finish(message: types.Message, state: FSMContext):
    code = message.text.strip()
    async with aiosqlite.connect(db.DB_NAME) as conn:
        await conn.execute("DELETE FROM animes WHERE code = ?", (code,))
        await conn.execute("DELETE FROM episodes WHERE anime_code = ?", (code,))
        await conn.commit()
    await message.answer(f"🗑 **{code}** kodli anime to'liq o'chirildi!")
    await state.clear()

# --- AVTO-KANAL SOZLASH ---
@dp.message(F.text == "🤖 Avto-kanal sozlash")
async def auto_ch_start(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id): return
    await state.set_state(AutoChannelFSM.channel_id)
    await message.answer("Postlar avtomatik tushadigan kanal ID'sini kiriting (masalan: `@kanal_username` yoki `-100123456789`):")

@dp.message(AutoChannelFSM.channel_id)
async def auto_ch_save(message: types.Message, state: FSMContext):
    ch_id = message.text.strip()
    async with aiosqlite.connect(db.DB_NAME) as conn:
        await conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('auto_channel', ?)", (ch_id,))
        await conn.commit()
    await message.answer(f"✅ **{ch_id}** avto-post kanali sifatida biriktirildi!")
    await state.clear()

# --- MAJBURIY KANALLAR BOSHQARUVI ---
@dp.message(F.text == "📢 Kanallar boshqaruvi")
async def channels_menu(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id): return
    await state.set_state(ChannelFSM.channel_id)
    await message.answer("Kanal ID yoki usernamesini kiriting (masalan: `@mychannel`):")

@dp.message(ChannelFSM.channel_id)
async def ch_id_save(message: types.Message, state: FSMContext):
    await state.update_data(channel_id=message.text.strip())
    await state.set_state(ChannelFSM.invite_link)
    await message.answer("Kanal taklif havolasini (invite link) kiriting:")

@dp.message(ChannelFSM.invite_link)
async def ch_link_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(db.DB_NAME) as conn:
        await conn.execute("INSERT INTO channels (channel_id, invite_link) VALUES (?, ?)", (data['channel_id'], message.text.strip()))
        await conn.commit()
    await message.answer("✅ Kanal majburiy obunaga qo'shildi!")
    await state.clear()

# --- STATISTIKA ---
@dp.message(F.text == "📊 Statistika")
async def show_stats(message: types.Message):
    if not await is_admin(message.from_user.id): return
    async with aiosqlite.connect(db.DB_NAME) as conn:
        async with conn.execute("SELECT COUNT(*) FROM users") as c1: u_cnt = (await c1.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM animes") as c2: a_cnt = (await c2.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM episodes") as c3: e_cnt = (await c3.fetchone())[0]
        
    await message.answer(f"📊 **Statistika:**\n\n👤 A'zolar: **{u_cnt}**\n🎬 Animelar: **{a_cnt}**\n🎞 Qismlar: **{e_cnt}**")

# --- ANIME QIDIRISH VA TUGMALAR ---
@dp.message(F.text)
async def search_anime(message: types.Message):
    code = message.text.strip()
    async with aiosqlite.connect(db.DB_NAME) as conn:
        async with conn.execute("SELECT title, description, poster_id FROM animes WHERE code = ?", (code,)) as cursor:
            anime = await cursor.fetchone()
            
    if anime:
        title, desc, poster = anime
        async with aiosqlite.connect(db.DB_NAME) as conn:
            async with conn.execute("SELECT DISTINCT season FROM episodes WHERE anime_code = ?", (code,)) as cursor:
                seasons = await cursor.fetchall()

        ikb_list = [[InlineKeyboardButton(text=f"🎬 {s[0]}-Fasl", callback_data=f"season_{code}_{s[0]}")] for s in seasons]
        ikb = InlineKeyboardMarkup(inline_keyboard=ikb_list) if ikb_list else None
        
        await message.answer_photo(photo=poster, caption=f"🎬 **{title}**\n\n📝 {desc}", reply_markup=ikb)
    else:
        await message.answer("❌ Bunday kodli anime topilmadi.")

# FASL BOSILGANDA QISMLARNI YUBORISH
@dp.callback_query(F.data.startswith("season_"))
async def show_episodes(call: types.CallbackQuery):
    _, code, season = call.data.split("_")
    async with aiosqlite.connect(db.DB_NAME) as conn:
        async with conn.execute(
            "SELECT episode_num, file_id FROM episodes WHERE anime_code = ? AND season = ?", 
            (code, int(season))
        ) as cursor:
            episodes = await cursor.fetchall()

    if episodes:
        await call.message.answer(f"🎞 **{season}-Fasl qismlari:**")
        for ep_num, file_id in episodes:
            try:
                await bot.send_video(chat_id=call.from_user.id, video=file_id, caption=f"▶️ {season}-Fasl {ep_num}-Qism")
            except Exception:
                await bot.send_document(chat_id=call.from_user.id, document=file_id, caption=f"▶️ {season}-Fasl {ep_num}-Qism")
    else:
        await call.answer("Ushbu faslda hali qismlar yo'q.", show_alert=True)

async def main():
    logging.basicConfig(level=logging.INFO)
    await db.init_db()
    await start_web_server()
    print("Bot muvaffaqiyatli ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
