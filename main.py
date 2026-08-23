import asyncio
import logging
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
import aiosqlite

# ----------------------------------------------------------------------
# 1. SOZLAMALAR
# ----------------------------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "8890621891:AAFX0yKQ81saY144zaFiBfGmAu75vi4cnmM")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8369095793"))
DB_NAME = "anime_database.db"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

# ----------------------------------------------------------------------
# 2. BAZA (AIOSQLITE)
# ----------------------------------------------------------------------
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
        await db.execute("CREATE TABLE IF NOT EXISTS animes (code TEXT PRIMARY KEY, title TEXT)")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                anime_code TEXT,
                season INTEGER,
                episode INTEGER,
                file_id TEXT,
                poster_id TEXT
            )
        """)
        await db.execute("CREATE TABLE IF NOT EXISTS channels (channel_id INTEGER PRIMARY KEY, link TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS links (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, url TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)")
        await db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        
        await db.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (ADMIN_ID,))
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('bot_status', 'ON')")
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('auto_channel', '')")
        await db.commit()

async def is_admin(user_id: int) -> bool:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,)) as cursor:
            res = await cursor.fetchone()
            return res is not None or user_id == ADMIN_ID

async def get_setting(key: str) -> str:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
            res = await cursor.fetchone()
            return res[0] if res else ""

async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        await db.commit()

# ----------------------------------------------------------------------
# 3. MAJBURIIY OBUNA
# ----------------------------------------------------------------------
async def check_subscriptions(user_id: int) -> tuple[bool, InlineKeyboardMarkup]:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT channel_id, link FROM channels") as cursor:
            channels = await cursor.fetchall()
    
    unsubscribed_buttons = []
    for c_id, link in channels:
        try:
            member = await bot.get_chat_member(chat_id=c_id, user_id=user_id)
            if member.status in ["left", "kicked"]:
                unsubscribed_buttons.append([InlineKeyboardButton(text="📢 Kanalga a'zo bo'lish", url=link)])
        except Exception:
            pass

    if unsubscribed_buttons:
        unsubscribed_buttons.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")])
        return False, InlineKeyboardMarkup(inline_keyboard=unsubscribed_buttons)
    return True, None

# ----------------------------------------------------------------------
# 4. FSM HOLATLARI
# ----------------------------------------------------------------------
class AddAnimeSG(StatesGroup):
    code = State()
    title = State()

class EditAnimeSG(StatesGroup):
    code = State()
    new_title = State()

class AddEpisodeSG(StatesGroup):
    code = State()
    season = State()
    episode = State()
    video = State()
    poster = State()

class AddBatchEpisodeSG(StatesGroup):
    code = State()
    season = State()
    total_episodes = State()
    current_episode = State()
    files = State()
    poster = State()

class AddChannelSG(StatesGroup):
    data = State()

class AddLinkSG(StatesGroup):
    data = State()

class SetAutoChannelSG(StatesGroup):
    channel_id = State()

class BroadcastSG(StatesGroup):
    message = State()

class AdminManageSG(StatesGroup):
    user_id = State()

# ----------------------------------------------------------------------
# 5. USER HANDLERLARI
# ----------------------------------------------------------------------
@router.message(CommandStart())
async def start_cmd(message: Message, command: CommandObject, state: FSMContext):
    await state.clear()
    if await get_setting("bot_status") == "OFF" and not await is_admin(message.from_user.id):
        await message.answer("⚠️ Bot vaqtincha texnik ishlar tufayli to'xtatilgan.")
        return

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
        await db.commit()

    is_sub, kb = await check_subscriptions(message.from_user.id)
    if not is_sub:
        await message.answer("❌ Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling:", reply_markup=kb)
        return

    args = command.args
    if args:
        await send_anime_panel(message, args)
        return

    await send_main_menu(message)

async def send_main_menu(message: Message):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT title, url FROM links") as cursor:
            links = await cursor.fetchall()
            
    kb_list = [[InlineKeyboardButton(text=title, url=url)] for title, url in links]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=kb_list) if kb_list else None
    
    text = "👋 Xush kelibsiz! Anime kodini yuboring:"
    if await is_admin(message.from_user.id):
        admin_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="👑 Admin Panel")]], resize_keyboard=True)
        await message.answer(text, reply_markup=reply_markup)
        await message.answer("Admin paneldan foydalanishingiz mumkin:", reply_markup=admin_kb)
    else:
        await message.answer(text, reply_markup=reply_markup)

@router.callback_query(F.data == "check_sub")
async def check_sub_cb(callback: CallbackQuery):
    is_sub, kb = await check_subscriptions(callback.from_user.id)
    if is_sub:
        await callback.message.delete()
        await callback.message.answer("✅ Rahmat! Endi botdan foydalanishingiz mumkin.")
        await send_main_menu(callback.message)
    else:
        await callback.answer("❌ Hali barcha kanallarga a'zo bo'lmadingiz!", show_alert=True)

async def send_anime_panel(message: Message, code: str):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT title FROM animes WHERE code = ?", (code,)) as cursor:
            anime = await cursor.fetchone()
            
        if not anime:
            await message.answer("❌ Bu kod bo'yicha anime topilmadi.")
            return

        async with db.execute("SELECT DISTINCT season, episode FROM episodes WHERE anime_code = ? ORDER BY season, episode", (code,)) as cursor:
            episodes = await cursor.fetchall()

    if not episodes:
        await message.answer(f"🎬 <b>{anime[0]}</b>\n\n⚠️ Bu animega hali qismlar yuklanmagan.")
        return

    kb_list = []
    row = []
    for season, ep in episodes:
        row.append(InlineKeyboardButton(text=f"{season}-fasl {ep}-qism", callback_data=f"get_ep:{code}:{season}:{ep}"))
        if len(row) == 2:
            kb_list.append(row)
            row = []
    if row: kb_list.append(row)

    await message.answer(f"🎬 <b>{anime[0]}</b>\n\nQismni tanlang:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list))

@router.callback_query(F.data.startswith("get_ep:"))
async def send_episode(callback: CallbackQuery):
    _, code, season, ep = callback.data.split(":")
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT file_id FROM episodes WHERE anime_code=? AND season=? AND episode=?", (code, season, ep)) as cursor:
            res = await cursor.fetchone()
            
    if res:
        await callback.message.reply_video(video=res[0], caption=f"🎬 Kod: {code} | {season}-fasl {ep}-qism")
        await callback.answer()
    else:
        await callback.answer("⚠️ Qism topilmadi.", show_alert=True)

@router.message(F.text & ~F.text.startswith("/"))
async def code_search(message: Message, state: FSMContext):
    if await state.get_state() is not None: return
    is_sub, kb = await check_subscriptions(message.from_user.id)
    if not is_sub:
        await message.answer("❌ Avval kanallarga a'zo bo'ling:", reply_markup=kb)
        return
    await send_anime_panel(message, message.text.strip())

# ----------------------------------------------------------------------
# 6. ADMIN PANEL (TO'LIQ BOSHQA RUTERLAR)
# ----------------------------------------------------------------------
@router.message(F.text == "👑 Admin Panel")
async def admin_panel_cmd(message: Message):
    if not await is_admin(message.from_user.id): return
    bot_status = await get_setting("bot_status")
    status_text = "🟢 Yoqilgan" if bot_status == "ON" else "🔴 To'xtatilgan"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Anime Qo'shish", callback_data="adm_add_anime"), InlineKeyboardButton(text="✏️ Tahrirlash", callback_data="adm_edit_anime")],
        [InlineKeyboardButton(text="➕ Qism Qo'shish (Yakka)", callback_data="adm_add_ep"), InlineKeyboardButton(text="📦 12-qism Paket Yuklash", callback_data="adm_add_batch")],
        [InlineKeyboardButton(text="📢 Majburiy Kanallar", callback_data="adm_channels"), InlineKeyboardButton(text="🔗 Havolalar", callback_data="adm_links")],
        [InlineKeyboardButton(text="⚙️ Avto-Kanal Sozlash", callback_data="adm_auto_channel"), InlineKeyboardButton(text="📨 Broadcast", callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="📊 Statistika", callback_data="adm_stats"), InlineKeyboardButton(text="👥 Adminlar Boshqaruvi", callback_data="adm_manage_admins")],
        [InlineKeyboardButton(text=f"⚙️ Bot Holati: {status_text}", callback_data="adm_toggle_status")]
    ])
    await message.answer("<b>👑 Admin Boshqaruv Paneli</b>\n\n*(Anime o'chirish uchun: <code>/del_KOD</code> yuboring)*", reply_markup=kb)

@router.callback_query(F.data == "adm_toggle_status")
async def toggle_status(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id): return
    curr = await get_setting("bot_status")
    new_st = "OFF" if curr == "ON" else "ON"
    await set_setting("bot_status", new_st)
    await callback.answer(f"Bot holati {new_st} ga o'zgartirildi.")
    await admin_panel_cmd(callback.message)

# --- Anime Qo'shish & Tahrirlash & O'chirish ---
@router.callback_query(F.data == "adm_add_anime")
async def add_anime_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Anime uchun unikal KOD kiriting (masalan: 101):")
    await state.set_state(AddAnimeSG.code)

@router.message(AddAnimeSG.code)
async def add_anime_code(message: Message, state: FSMContext):
    await state.update_data(code=message.text.strip())
    await message.answer("Anime nomini kiriting:")
    await state.set_state(AddAnimeSG.title)

@router.message(AddAnimeSG.title)
async def add_anime_title(message: Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO animes (code, title) VALUES (?, ?)", (data['code'], message.text.strip()))
        await db.commit()
    await message.answer(f"✅ Anime saqlandi!\nKod: <code>{data['code']}</code>\nNomi: {message.text.strip()}")
    await state.clear()

@router.callback_query(F.data == "adm_edit_anime")
async def edit_anime_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Nomi o'zgartiriladigan anime KODini kiriting:")
    await state.set_state(EditAnimeSG.code)

@router.message(EditAnimeSG.code)
async def edit_anime_code(message: Message, state: FSMContext):
    await state.update_data(code=message.text.strip())
    await message.answer("Yangi nomni kiriting:")
    await state.set_state(EditAnimeSG.new_title)

@router.message(EditAnimeSG.new_title)
async def edit_anime_title(message: Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE animes SET title = ? WHERE code = ?", (message.text.strip(), data['code']))
        await db.commit()
    await message.answer(f"✏️ Kod <code>{data['code']}</code> bo'lgan anime nomi yangilandi.")
    await state.clear()

@router.message(Command("del_"))
async def delete_anime_cmd(message: Message):
    if not await is_admin(message.from_user.id): return
    code = message.text.replace("/del_", "").strip()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM animes WHERE code = ?", (code,))
        await db.execute("DELETE FROM episodes WHERE anime_code = ?", (code,))
        await db.commit()
    await message.answer(f"🗑 Kodi <code>{code}</code> bo'lgan anime va barcha qismlari o'chirildi.")

# --- Yakka Qism Qo'shish ---
@router.callback_query(F.data == "adm_add_ep")
async def add_ep_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Anime kodini kiriting:")
    await state.set_state(AddEpisodeSG.code)

@router.message(AddEpisodeSG.code)
async def add_ep_code(message: Message, state: FSMContext):
    await state.update_data(code=message.text.strip())
    await message.answer("Fasl raqamini kiriting (masalan: 1):")
    await state.set_state(AddEpisodeSG.season)

@router.message(AddEpisodeSG.season)
async def add_ep_season(message: Message, state: FSMContext):
    await state.update_data(season=int(message.text.strip()))
    await message.answer("Qism raqamini kiriting:")
    await state.set_state(AddEpisodeSG.episode)

@router.message(AddEpisodeSG.episode)
async def add_ep_num(message: Message, state: FSMContext):
    await state.update_data(episode=int(message.text.strip()))
    await message.answer("Video faylni yuboring:")
    await state.set_state(AddEpisodeSG.video)

@router.message(AddEpisodeSG.video, F.video)
async def add_ep_video(message: Message, state: FSMContext):
    await state.update_data(video=message.video.file_id)
    await message.answer("Ushbu qism uchun poster (rasm) yuboring:")
    await state.set_state(AddEpisodeSG.poster)

@router.message(AddEpisodeSG.poster, F.photo)
async def add_ep_poster(message: Message, state: FSMContext):
    data = await state.get_data()
    poster_id = message.photo[-1].file_id

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO episodes (anime_code, season, episode, file_id, poster_id) VALUES (?, ?, ?, ?, ?)",
                         (data['code'], data['season'], data['episode'], data['video'], poster_id))
        async with db.execute("SELECT title FROM animes WHERE code = ?", (data['code'],)) as cursor:
            anime_title = await cursor.fetchone()
        await db.commit()

    title = anime_title[0] if anime_title else "Anime"
    await message.answer("✅ Qism saqlandi!")

    auto_ch = await get_setting("auto_channel")
    if auto_ch:
        me = await bot.get_me()
        btn = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🍿 Tomosha qilish", url=f"https://t.me/{me.username}?start={data['code']}")]])
        caption = f"🎬 <b>{title}</b>\n📌 {data['season']}-fasl {data['episode']}-qism joylandi!\n\n🔑 Kod: <code>{data['code']}</code>"
        try: await bot.send_photo(chat_id=auto_ch, photo=poster_id, caption=caption, reply_markup=btn)
        except Exception as e: await message.answer(f"⚠️ Avto-postda xatolik: {e}")

    await state.clear()

# --- 12-Qism Paket Yuklash ---
@router.callback_query(F.data == "adm_add_batch")
async def add_batch_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Anime kodini kiriting:")
    await state.set_state(AddBatchEpisodeSG.code)

@router.message(AddBatchEpisodeSG.code)
async def add_batch_code(message: Message, state: FSMContext):
    await state.update_data(code=message.text.strip())
    await message.answer("Fasl raqamini kiriting:")
    await state.set_state(AddBatchEpisodeSG.season)

@router.message(AddBatchEpisodeSG.season)
async def add_batch_season(message: Message, state: FSMContext):
    await state.update_data(season=int(message.text.strip()))
    await message.answer("Jami nechta qism yuklaysiz? (masalan: 12):")
    await state.set_state(AddBatchEpisodeSG.total_episodes)

@router.message(AddBatchEpisodeSG.total_episodes)
async def add_batch_total(message: Message, state: FSMContext):
    total = int(message.text.strip())
    await state.update_data(total_episodes=total, current_episode=1, files=[])
    await message.answer("1-qism videosini yuboring:")
    await state.set_state(AddBatchEpisodeSG.files)

@router.message(AddBatchEpisodeSG.files, F.video)
async def add_batch_files(message: Message, state: FSMContext):
    data = await state.get_data()
    files = data['files']
    files.append(message.video.file_id)

    curr = data['current_episode'] + 1
    total = data['total_episodes']

    if curr <= total:
        await state.update_data(current_episode=curr, files=files)
        await message.answer(f"{curr}-qism videosini yuboring:")
    else:
        await state.update_data(files=files)
        await message.answer("Barcha videolar qabul qilindi. Umumiy poster (rasm) yuboring:")
        await state.set_state(AddBatchEpisodeSG.poster)

@router.message(AddBatchEpisodeSG.poster, F.photo)
async def add_batch_poster(message: Message, state: FSMContext):
    data = await state.get_data()
    poster_id = message.photo[-1].file_id

    async with aiosqlite.connect(DB_NAME) as db:
        for idx, file_id in enumerate(data['files'], 1):
            await db.execute("INSERT INTO episodes (anime_code, season, episode, file_id, poster_id) VALUES (?, ?, ?, ?, ?)",
                             (data['code'], data['season'], idx, file_id, poster_id))
        async with db.execute("SELECT title FROM animes WHERE code = ?", (data['code'],)) as cursor:
            anime_title = await cursor.fetchone()
        await db.commit()

    title = anime_title[0] if anime_title else "Anime"
    await message.answer("✅ Barcha qismlar bazaga yuklandi!")

    auto_ch = await get_setting("auto_channel")
    if auto_ch:
        me = await bot.get_me()
        btn = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🍿 Barcha qismlarni ko'rish", url=f"https://t.me/{me.username}?start={data['code']}")]])
        caption = f"🔥 <b>{title}</b>\n✨ {data['season']}-fasl (1-{data['total_episodes']} qismlar) to'liq joylandi!\n\n🔑 Kod: <code>{data['code']}</code>"
        try: await bot.send_photo(chat_id=auto_ch, photo=poster_id, caption=caption, reply_markup=btn)
        except Exception as e: await message.answer(f"⚠️ Avto-postda xatolik: {e}")

    await state.clear()

# --- Avto-Kanal, Majburiy Kanallar, Linklar ---
@router.callback_query(F.data == "adm_auto_channel")
async def set_auto_ch_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Avto-post kanali ID-sini kiriting (masalan: -100123456789):")
    await state.set_state(SetAutoChannelSG.channel_id)

@router.message(SetAutoChannelSG.channel_id)
async def set_auto_ch_done(message: Message, state: FSMContext):
    await set_setting("auto_channel", message.text.strip())
    await message.answer(f"✅ Avto-kanal saqlandi: {message.text.strip()}")
    await state.clear()

@router.callback_query(F.data == "adm_channels")
async def add_channel_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Majburiy kanal ma'lumotlarini kiriting (Format: `ID|LINK`):\n\nMisol: `-100123456789|https://t.me/kanal_link`")
    await state.set_state(AddChannelSG.data)

@router.message(AddChannelSG.data)
async def add_channel_done(message: Message, state: FSMContext):
    try:
        c_id, link = message.text.split("|")
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("INSERT OR REPLACE INTO channels (channel_id, link) VALUES (?, ?)", (int(c_id.strip()), link.strip()))
            await db.commit()
        await message.answer("✅ Majburiy kanal saqlandi.")
    except Exception:
        await message.answer("❌ Format noto'g'ri. Misol: `-10012345|https://t.me/link`")
    await state.clear()

@router.callback_query(F.data == "adm_links")
async def add_link_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Bosh menyudagi tugma uchun ma'lumot kiriting (Format: `TUGMA NOMI|LINK`):\n\nMisol: `Guruhimiz|https://t.me/group_link`")
    await state.set_state(AddLinkSG.data)

@router.message(AddLinkSG.data)
async def add_link_done(message: Message, state: FSMContext):
    try:
        title, url = message.text.split("|")
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("INSERT INTO links (title, url) VALUES (?, ?)", (title.strip(), url.strip()))
            await db.commit()
        await message.answer("✅ Havola tugmasi saqlandi.")
    except Exception:
        await message.answer("❌ Format noto'g'ri.")
    await state.clear()

# --- Adminlar Boshqaruvi ---
@router.callback_query(F.data == "adm_manage_admins")
async def manage_admins(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Faqat asosiy Admin yangi admin qo'sha oladi!", show_alert=True)
        return
    await callback.message.answer("Yangi Admin Telegram ID-sini kiriting:")
    await state.set_state(AdminManageSG.user_id)

@router.message(AdminManageSG.user_id)
async def add_admin_done(message: Message, state: FSMContext):
    try:
        new_id = int(message.text.strip())
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (new_id,))
            await db.commit()
        await message.answer(f"✅ User ID: <code>{new_id}</code> admin qilindi.")
    except Exception:
        await message.answer("❌ Noto'g'ri ID format.")
    await state.clear()

# --- Broadcast & Statistika ---
@router.callback_query(F.data == "adm_broadcast")
async def broadcast_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Barcha foydalanuvchilarga yuboriladigan xabarni kiriting:")
    await state.set_state(BroadcastSG.message)

@router.message(BroadcastSG.message)
async def broadcast_send(message: Message, state: FSMContext):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM users") as cursor: users = await cursor.fetchall()
    count = 0
    await message.answer("🚀 Reklama tarqatilmoqda...")
    for u in users:
        try:
            await message.copy_to(chat_id=u[0])
            count += 1
            if count % 20 == 0: await asyncio.sleep(1)
        except Exception: pass
    await message.answer(f"✅ Xabar {count} kishiga yuborildi.")
    await state.clear()

@router.callback_query(F.data == "adm_stats")
async def show_stats(callback: CallbackQuery):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c1: u_count = (await c1.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM animes") as c2: a_count = (await c2.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM episodes") as c3: e_count = (await c3.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM channels") as c4: ch_count = (await c4.fetchone())[0]
    await callback.message.answer(f"📊 <b>Bot Statistikasi:</b>\n\n👤 Foydalanuvchilar: {u_count}\n🎬 Animelar: {a_count}\n🎞 Qismlar: {e_count}\n📢 Majburiy Kanallar: {ch_count}")

# ----------------------------------------------------------------------
# 7. AIOHTTP SERVER & RUNNER
# ----------------------------------------------------------------------
async def handle_ping(request):
    return web.Response(text="Bot runs smoothly!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    await init_db()
    await start_web_server()
    print("Bot va Server faol!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot to'xtatildi.")
