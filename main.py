import os
import asyncio
import logging
import aiosqlite
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

# --- CONFIGURATION ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "8848385049:AAFC5C0ko3piaKdarVjnbSXuIGy3m73CHcM")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8369095793"))
DB_NAME = "anime_bot.db"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

BOT_ACTIVE = True

# --- FSM STATES ---
class AnimeState(StatesGroup):
    title = State()
    code = State()

class EditAnimeState(StatesGroup):
    code = State()
    new_title = State()

class EpisodeState(StatesGroup):
    code = State()
    season = State()
    ep_num = State()
    video = State()
    poster = State()

class BulkEpisodeState(StatesGroup):
    code = State()
    season = State()
    start_ep = State()
    videos = State()
    poster = State()

class ChannelState(StatesGroup):
    ch_type = State()
    ch_id = State()
    title = State()
    link = State()

class ExtraLinkState(StatesGroup):
    title = State()
    url = State()

class BroadcastState(StatesGroup):
    message = State()

class AdminState(StatesGroup):
    user_id = State()
    del_user_id = State()

class AutoChannelState(StatesGroup):
    ch_id = State()

# --- DATABASE SETUP ---
async def init_db():
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
        await conn.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)")
        await conn.execute("CREATE TABLE IF NOT EXISTS anime (code TEXT PRIMARY KEY, title TEXT)")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                anime_code TEXT,
                season INTEGER,
                ep_num INTEGER,
                file_id TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ch_id INTEGER,
                ch_type TEXT,
                title TEXT,
                link TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS extra_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                url TEXT
            )
        """)
        await conn.execute("CREATE TABLE IF NOT EXISTS auto_channels (ch_id INTEGER PRIMARY KEY)")
        await conn.commit()

async def is_admin(user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,)) as cursor:
            return (await cursor.fetchone()) is not None

async def check_subscribes(user_id: int):
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT ch_id, link, ch_type FROM channels") as cursor:
            channels = await cursor.fetchall()

    unsubbed = []
    for ch_id, link, ch_type in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch_id, user_id=user_id)
            if member.status in ["left", "kicked"]:
                unsubbed.append((link, ch_type))
        except Exception:
            pass
    return unsubbed

# --- MENUS ---
def admin_menu():
    kb = [
        [KeyboardButton(text="➕ Anime qo‘shish"), KeyboardButton(text="➕ Qism qo‘shish")],
        [KeyboardButton(text="📦 Ko‘p qism qo‘shish"), KeyboardButton(text="✏️ Anime tahrirlash")],
        [KeyboardButton(text="🗑 Anime o‘chirish"), KeyboardButton(text="📢 Majburiy kanallar")],
        [KeyboardButton(text="🔗 Qo'shimcha linklar"), KeyboardButton(text="📢 Avto-kanal biriktirish")],
        [KeyboardButton(text="📨 Xabar yuborish"), KeyboardButton(text="📊 Mukammal Statistika")],
        [KeyboardButton(text="👥 Adminlar ro'yxati"), KeyboardButton(text="👤 Admin qo'shish")],
        [KeyboardButton(text="🗑 Admin o'chirish")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def bulk_finish_kb():
    kb = [[KeyboardButton(text="✅ Yuklashni tugatish")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- RENDER PORT HEALTH CHECK ---
async def health_check(request):
    return web.Response(text="Bot runs smoothly!", status=200)

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

# --- HELPER: SEND ANIME BY CODE ---
async def send_anime_by_code(message_or_call, code: str):
    if isinstance(message_or_call, types.Message):
        send_func = message_or_call.answer
    else:
        send_func = message_or_call.message.answer

    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT title FROM anime WHERE code = ?", (code,)) as cursor:
            anime = await cursor.fetchone()
        if not anime:
            await send_func("❌ Bu kodli anime topilmadi yoki o'chirilgan.")
            return

        async with conn.execute("SELECT season, ep_num FROM episodes WHERE anime_code = ? ORDER BY season ASC, ep_num ASC", (code,)) as cursor:
            episodes = await cursor.fetchall()

    if not episodes:
        await send_func(f"🎬 **{anime[0]}** animedan qismlar topilmadi.", parse_mode="Markdown")
        return

    ikb, row = [], []
    for season, ep_num in episodes:
        row.append(InlineKeyboardButton(text=f"{season}-Fasl {ep_num}-Qism", callback_data=f"play_{code}_{season}_{ep_num}"))
        if len(row) == 2:
            ikb.append(row)
            row = []
    if row: ikb.append(row)

    caption = f"🎬 **{anime[0]}**\nKo'rmoqchi bo'lgan qismingizni tanlang:"
    await send_func(caption, reply_markup=InlineKeyboardMarkup(inline_keyboard=ikb), parse_mode="Markdown")

# --- START COMMAND & DEEP LINK HANDLER ---
@dp.message(CommandStart())
async def start_cmd(message: types.Message, state: FSMContext, command: CommandObject = None):
    await state.clear()
    args = command.args if command else None  # Deep Link code (masalan: ?start=101)

    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
        await conn.commit()

    if not BOT_ACTIVE and not await is_admin(message.from_user.id):
        await message.answer("⚠️ Botda profilaktika ishlari olib borilmoqda. Birozdan so'ng urinib ko'ring.")
        return

    # Obunani tekshirish
    unsubbed = await check_subscribes(message.from_user.id)
    if unsubbed and not await is_admin(message.from_user.id):
        ikb = []
        for idx, (link, ch_type) in enumerate(unsubbed, 1):
            type_label = " (Zayavka)" if ch_type == "zayafka" else ""
            ikb.append([InlineKeyboardButton(text=f"📢 {idx}-Kanalga a'zo bo'lish{type_label}", url=link)])
        
        cb_data = f"check_sub_{args}" if args else "check_sub"
        ikb.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data=cb_data)])
        await message.answer("⚠️ Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling:", reply_markup=InlineKeyboardMarkup(inline_keyboard=ikb))
        return

    # Agar kanal orqali biriktirilgan link (Deep Link) bilan kirsa -> To'g'ridan-to'g'ri animeni chiqaradi
    if args:
        await send_anime_by_code(message, args)
        return

    # Admin bo'lsa panelni chiqaradi
    if await is_admin(message.from_user.id):
        await message.answer("🛠 Admin paneliga xush kelibsiz:", reply_markup=admin_menu())
        return

    # Oddiy start bossa
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT title, url FROM extra_links") as cursor:
            links = await cursor.fetchall()

    text = """Assalomu alaykum! ✨🌸
Xush kelibsiz! Anime kodini yuboring:"""

    ikb = []
    if links:
        for title, url in links:
            ikb.append([InlineKeyboardButton(text=title, url=url)])
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=ikb))
    else:
        await message.answer(text)

@dp.callback_query(F.data.startswith("check_sub"))
async def check_sub_cb(call: types.CallbackQuery):
    unsubbed = await check_subscribes(call.from_user.id)
    parts = call.data.split("_")
    target_code = parts[2] if len(parts) > 2 else None

    if not unsubbed:
        await call.message.delete()
        if target_code:
            await send_anime_by_code(call, target_code)
        else:
            await call.message.answer("✅ Obuna tasdiqlandi! Anime kodini yuborishingiz mumkin:")
    else:
        await call.answer("❌ Barcha kanallarga a'zo bo'lmadingiz!", show_alert=True)

# --- ANIME MANAGEMENT ---
@dp.message(F.text == "➕ Anime qo‘shish")
async def add_anime_start(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id): return
    await state.set_state(AnimeState.title)
    await message.answer("Anime nomini kiriting:")

@dp.message(AnimeState.title)
async def add_anime_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(AnimeState.code)
    await message.answer("Anime uchun **KOD** kiriting (masalan: `101`):")

@dp.message(AnimeState.code)
async def add_anime_code(message: types.Message, state: FSMContext):
    code = message.text.strip()
    data = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as conn:
        try:
            await conn.execute("INSERT INTO anime (code, title) VALUES (?, ?)", (code, data['title']))
            await conn.commit()
            await message.answer(f"✅ Anime saqlandi!\nNomi: {data['title']}\nKodi: `{code}`", reply_markup=admin_menu(), parse_mode="Markdown")
        except Exception:
            await message.answer("❌ Bu kod allaqachon mavjud!")
    await state.clear()

@dp.message(F.text == "✏️ Anime tahrirlash")
async def edit_anime_start(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id): return
    await state.set_state(EditAnimeState.code)
    await message.answer("Tahrirlamoqchi bo'lgan anime **KODINI** kiriting:")

@dp.message(EditAnimeState.code)
async def edit_anime_code(message: types.Message, state: FSMContext):
    code = message.text.strip()
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT title FROM anime WHERE code = ?", (code,)) as cursor:
            anime = await cursor.fetchone()
    if not anime:
        await message.answer("❌ Bunday kodli anime topilmadi!")
        await state.clear()
        return
    await state.update_data(code=code)
    await state.set_state(EditAnimeState.new_title)
    await message.answer(f"Eski nomi: **{anime[0]}**\nYangi nomni kiriting:")

@dp.message(EditAnimeState.new_title)
async def edit_anime_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("UPDATE anime SET title = ? WHERE code = ?", (message.text, data['code']))
        await conn.commit()
    await message.answer("✅ Anime nomi muvaffaqiyatli o'zgartirildi!", reply_markup=admin_menu())
    await state.clear()

@dp.message(F.text == "🗑 Anime o‘chirish")
async def del_anime_cmd(message: types.Message):
    if not await is_admin(message.from_user.id): return
    await message.answer("O'chirish uchun kodingizni yuboring (Masalan: `/del_101`)")

@dp.message(F.text.startswith("/del_"))
async def del_anime_confirm(message: types.Message):
    if not await is_admin(message.from_user.id): return
    code = message.text.replace("/del_", "").strip()
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("DELETE FROM anime WHERE code = ?", (code,))
        await conn.execute("DELETE FROM episodes WHERE anime_code = ?", (code,))
        await conn.commit()
    await message.answer(f"🗑 Kodi `{code}` bo'lgan anime va barcha qismlari o'chirildi!", parse_mode="Markdown")

# --- EPISODE MANAGEMENT & AUTO-POSTING ---
@dp.message(F.text == "➕ Qism qo‘shish")
async def add_ep_start(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id): return
    await state.set_state(EpisodeState.code)
    await message.answer("Anime kodini kiriting:")

@dp.message(EpisodeState.code)
async def add_ep_code(message: types.Message, state: FSMContext):
    code = message.text.strip()
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT title FROM anime WHERE code = ?", (code,)) as cursor:
            anime = await cursor.fetchone()
    if not anime:
        await message.answer("❌ Anime topilmadi!")
        await state.clear()
        return
    await state.update_data(code=code, title=anime[0])
    await state.set_state(EpisodeState.season)
    await message.answer("Fasl raqamini kiriting (masalan: `1`):")

@dp.message(EpisodeState.season)
async def add_ep_season(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return
    await state.update_data(season=int(message.text))
    await state.set_state(EpisodeState.ep_num)
    await message.answer("Qism raqamini kiriting:")

@dp.message(EpisodeState.ep_num)
async def add_ep_num(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return
    await state.update_data(ep_num=int(message.text))
    await state.set_state(EpisodeState.video)
    await message.answer("📹 Videoni yuboring:")

@dp.message(EpisodeState.video, F.video)
async def add_ep_video(message: types.Message, state: FSMContext):
    await state.update_data(file_id=message.video.file_id)
    await state.set_state(EpisodeState.poster)
    await message.answer("📸 Kanalga avto-post uchun **POSTER (RASM)** yuboring:")

@dp.message(EpisodeState.poster, F.photo)
async def add_ep_finish(message: types.Message, state: FSMContext):
    poster_id = message.photo[-1].file_id
    data = await state.get_data()
    code, season, ep_num, file_id, title = data['code'], data['season'], data['ep_num'], data['file_id'], data['title']

    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT COUNT(*) FROM episodes WHERE anime_code = ? AND season = ?", (code, season)) as cursor:
            count = (await cursor.fetchone())[0]

        await conn.execute("INSERT INTO episodes (anime_code, season, ep_num, file_id) VALUES (?, ?, ?, ?)", (code, season, ep_num, file_id))
        await conn.commit()

        async with conn.execute("SELECT ch_id FROM auto_channels") as cursor:
            auto_ch = await cursor.fetchall()

    await message.answer("✅ Qism saqlandi va avto-postlar yuborildi!", reply_markup=admin_menu())

    bot_info = await bot.get_me()
    ikb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🎬 Botda tomosha qilish", url=f"https://t.me/{bot_info.username}?start={code}")
    ]])

    for (ch_id,) in auto_ch:
        try:
            if count == 0:
                season_text = f"🔥 **YANGI FASL PREMYERASI!**\n\n🎬 **Nomi:** {title}\n🗓 **Fasl:** {season}-Fasl\n🔑 **Kodi:** `{code}`"
                await bot.send_photo(chat_id=ch_id, photo=poster_id, caption=season_text, reply_markup=ikb, parse_mode="Markdown")

            ep_text = f"🎬 **{title}**\n\n📌 **{season}-Fasl | {ep_num}-Qism**\n🔑 **Anime kodi:** `{code}`"
            await bot.send_photo(chat_id=ch_id, photo=poster_id, caption=ep_text, reply_markup=ikb, parse_mode="Markdown")
        except Exception as e:
            print(f"Auto post error: {e}")

    await state.clear()

# --- BULK EPISODE UPLOAD (KO'P QISM QO'SHISH) ---
@dp.message(F.text == "📦 Ko‘p qism qo‘shish")
async def bulk_ep_start(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id): return
    await state.set_state(BulkEpisodeState.code)
    await message.answer("Anime kodini kiriting:")

@dp.message(BulkEpisodeState.code)
async def bulk_ep_code(message: types.Message, state: FSMContext):
    code = message.text.strip()
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT title FROM anime WHERE code = ?", (code,)) as cursor:
            anime = await cursor.fetchone()
    if not anime:
        await message.answer("❌ Anime topilmadi!")
        await state.clear()
        return
    await state.update_data(code=code, title=anime[0])
    await state.set_state(BulkEpisodeState.season)
    await message.answer("Fasl raqamini kiriting (masalan: `1`):")

@dp.message(BulkEpisodeState.season)
async def bulk_ep_season(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return
    await state.update_data(season=int(message.text))
    await state.set_state(BulkEpisodeState.start_ep)
    await message.answer("Nechinchi qismdan boshlab yuklaysiz? (masalan: `1`):")

@dp.message(BulkEpisodeState.start_ep)
async def bulk_ep_start_num(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return
    await state.update_data(start_ep=int(message.text), videos=[])
    await state.set_state(BulkEpisodeState.videos)
    await message.answer(
        "📹 Endi videolarni **tartib bilan, birin-ketin** yuboring "
        "(1-qism, 2-qism, 3-qism...).\n\n"
        "Barchasini yuborib bo'lgach, pastdagi «✅ Yuklashni tugatish» tugmasini bosing.",
        reply_markup=bulk_finish_kb(),
        parse_mode="Markdown"
    )

@dp.message(BulkEpisodeState.videos, F.video)
async def bulk_ep_collect_video(message: types.Message, state: FSMContext):
    data = await state.get_data()
    videos = data.get('videos', [])
    videos.append(message.video.file_id)
    await state.update_data(videos=videos)
    start_ep = data['start_ep']
    await message.answer(f"✅ {start_ep + len(videos) - 1}-qism qabul qilindi. (Jami: {len(videos)} ta)\nDavom eting yoki tugating.")

@dp.message(BulkEpisodeState.videos, F.text == "✅ Yuklashni tugatish")
async def bulk_ep_finish_upload(message: types.Message, state: FSMContext):
    data = await state.get_data()
    videos = data.get('videos', [])
    if not videos:
        await message.answer("❌ Hech qanday video yuklanmadi! Kamida bitta video yuboring.")
        return
    await state.set_state(BulkEpisodeState.poster)
    await message.answer(
        f"📸 {len(videos)} ta qism uchun kanalga avto-post qilinadigan **POSTER (RASM)**ni yuboring:",
        reply_markup=types.ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )

@dp.message(BulkEpisodeState.videos)
async def bulk_ep_wrong_input(message: types.Message):
    await message.answer("⚠️ Iltimos, video yuboring yoki «✅ Yuklashni tugatish» tugmasini bosing.")

@dp.message(BulkEpisodeState.poster, F.photo)
async def bulk_ep_save(message: types.Message, state: FSMContext):
    poster_id = message.photo[-1].file_id
    data = await state.get_data()
    code, season, start_ep, videos, title = data['code'], data['season'], data['start_ep'], data['videos'], data['title']

    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT COUNT(*) FROM episodes WHERE anime_code = ? AND season = ?", (code, season)) as cursor:
            existing_count = (await cursor.fetchone())[0]

        for i, file_id in enumerate(videos):
            ep_num = start_ep + i
            await conn.execute("INSERT INTO episodes (anime_code, season, ep_num, file_id) VALUES (?, ?, ?, ?)", (code, season, ep_num, file_id))
        await conn.commit()

        async with conn.execute("SELECT ch_id FROM auto_channels") as cursor:
            auto_ch = await cursor.fetchall()

    end_ep = start_ep + len(videos) - 1
    await message.answer(
        f"✅ {len(videos)} ta qism ({start_ep}-{end_ep}) saqlandi va avto-postlar yuborildi!",
        reply_markup=admin_menu()
    )

    bot_info = await bot.get_me()
    ikb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🎬 Botda tomosha qilish", url=f"https://t.me/{bot_info.username}?start={code}")
    ]])

    for (ch_id,) in auto_ch:
        try:
            if existing_count == 0:
                season_text = f"🔥 **YANGI FASL PREMYERASI!**\n\n🎬 **Nomi:** {title}\n🗓 **Fasl:** {season}-Fasl\n🔑 **Kodi:** `{code}`"
                await bot.send_photo(chat_id=ch_id, photo=poster_id, caption=season_text, reply_markup=ikb, parse_mode="Markdown")

            if len(videos) > 1:
                ep_text = f"🎬 **{title}**\n\n📌 **{season}-Fasl | {start_ep}-{end_ep}-Qismlar**\n🔑 **Anime kodi:** `{code}`"
            else:
                ep_text = f"🎬 **{title}**\n\n📌 **{season}-Fasl | {start_ep}-Qism**\n🔑 **Anime kodi:** `{code}`"
            await bot.send_photo(chat_id=ch_id, photo=poster_id, caption=ep_text, reply_markup=ikb, parse_mode="Markdown")
        except Exception as e:
            print(f"Auto post error: {e}")

    await state.clear()

# --- CHANNEL MANAGEMENT ---
@dp.message(F.text == "📢 Majburiy kanallar")
async def channels_cmd(message: types.Message):
    if not await is_admin(message.from_user.id): return
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT id, title, ch_type FROM channels") as cursor:
            chs = await cursor.fetchall()

    text = "📢 **Majburiy kanallar ro'yxati:**\n\n"
    ikb = []
    if chs:
        for cid, ctitle, ctype in chs:
            text += f"🔹 **{ctitle}** ({ctype.capitalize()})\n"
            ikb.append([InlineKeyboardButton(text=f"❌ O'chirish: {ctitle}", callback_data=f"delch_{cid}")])
    else:
        text += "Hozircha majburiy kanallar yo'q.\n"

    ikb.append([InlineKeyboardButton(text="➕ Ommaviy kanal", callback_data="addch_ommaviy")])
    ikb.append([InlineKeyboardButton(text="➕ Shaxsiy kanal", callback_data="addch_shaxsiy")])
    ikb.append([InlineKeyboardButton(text="➕ Zayavka kanal", callback_data="addch_zayafka")])

    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=ikb), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("addch_"))
async def add_ch_type(call: types.CallbackQuery, state: FSMContext):
    ch_type = call.data.split("_")[1]
    await state.update_data(ch_type=ch_type)
    await state.set_state(ChannelState.ch_id)
    await call.message.answer("Kanal **ID**sini kiriting (masalan: `-100123456789`):")

@dp.message(ChannelState.ch_id)
async def add_ch_id(message: types.Message, state: FSMContext):
    await state.update_data(ch_id=int(message.text.strip()))
    await state.set_state(ChannelState.title)
    await message.answer("Kanal nomini kiriting:")

@dp.message(ChannelState.title)
async def add_ch_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(ChannelState.link)
    await message.answer("Kanal **LINKI**ni kiriting (Masalan: `https://t.me/...`):")

@dp.message(ChannelState.link)
async def add_ch_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("INSERT INTO channels (ch_id, ch_type, title, link) VALUES (?, ?, ?, ?)",
                           (data['ch_id'], data['ch_type'], data['title'], message.text.strip()))
        await conn.commit()
    await message.answer("✅ Majburiy kanal saqlandi!", reply_markup=admin_menu())
    await state.clear()

@dp.callback_query(F.data.startswith("delch_"))
async def del_ch(call: types.CallbackQuery):
    cid = int(call.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("DELETE FROM channels WHERE id = ?", (cid,))
        await conn.commit()
    await call.answer("🗑 Kanal muvaffaqiyatli o'chirildi!", show_alert=True)
    await call.message.delete()

# --- EXTRA LINKS MANAGEMENT ---
@dp.message(F.text == "🔗 Qo'shimcha linklar")
async def extra_links_cmd(message: types.Message):
    if not await is_admin(message.from_user.id): return
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT id, title, url FROM extra_links") as cursor:
            links = await cursor.fetchall()

    text = "🔗 **Qo'shimcha linklar (tugmalar):**\n\n"
    ikb = []
    if links:
        for lid, ltitle, lurl in links:
            text += f"🔹 [{ltitle}]({lurl})\n"
            ikb.append([InlineKeyboardButton(text=f"🗑 O'chirish: {ltitle}", callback_data=f"dellink_{lid}")])
    else:
        text += "Hozircha qo'shimcha linklar yo'q.\n"

    ikb.append([InlineKeyboardButton(text="➕ Yangi link qo'shish", callback_data="add_extralink")])

    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=ikb), parse_mode="Markdown", disable_web_page_preview=True)

@dp.callback_query(F.data.startswith("dellink_"))
async def del_link_callback(call: types.CallbackQuery):
    lid = int(call.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("DELETE FROM extra_links WHERE id = ?", (lid,))
        await conn.commit()
    await call.answer("🗑 Link o'chirildi!", show_alert=True)
    await call.message.delete()

@dp.callback_query(F.data == "add_extralink")
async def add_link_start_cb(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(ExtraLinkState.title)
    await call.message.answer("Tugma matnini kiriting (Masalan: `💬 Bizning guruh`):")
    await call.answer()

@dp.message(ExtraLinkState.title)
async def extra_link_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(ExtraLinkState.url)
    await message.answer("URL manzilni kiriting:")

@dp.message(ExtraLinkState.url)
async def extra_link_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("INSERT INTO extra_links (title, url) VALUES (?, ?)", (data['title'], message.text.strip()))
        await conn.commit()
    await message.answer("✅ Qo'shimcha link saqlandi!", reply_markup=admin_menu())
    await state.clear()

# --- AUTO CHANNEL ---
@dp.message(F.text == "📢 Avto-kanal biriktirish")
async def auto_channel_cmd(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id): return
    await state.set_state(AutoChannelState.ch_id)
    await message.answer("Avto-post yuboriladigan kanal **ID**sini kiriting (Masalan: `-100123456789`):")

@dp.message(AutoChannelState.ch_id)
async def auto_channel_save(message: types.Message, state: FSMContext):
    try:
        ch_id = int(message.text.strip())
        async with aiosqlite.connect(DB_NAME) as conn:
            await conn.execute("INSERT OR REPLACE INTO auto_channels (ch_id) VALUES (?)", (ch_id,))
            await conn.commit()
        await message.answer(f"✅ Avto-kanal (`{ch_id}`) muvaffaqiyatli biriktirildi!", reply_markup=admin_menu(), parse_mode="Markdown")
    except ValueError:
        await message.answer("❌ Kanal IDsi faqat raqamlardan iborat bo'lishi kerak! Qayta kiriting:")
        return
    await state.clear()

# --- BROADCASTING ---
@dp.message(F.text == "📨 Xabar yuborish")
async def broad_start(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id): return
    await state.set_state(BroadcastState.message)
    await message.answer("Barcha foydalanuvchilarga yuboriladigan xabarni (matn, rasm yoki video) kiriting:")

@dp.message(BroadcastState.message)
async def broad_send(message: types.Message, state: FSMContext):
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT user_id FROM users") as cursor:
            users = await cursor.fetchall()

    success, count = 0, 0
    await message.answer("🚀 Xabar yuborish boshlandi...")

    for (uid,) in users:
        try:
            await message.copy_to(chat_id=uid)
            success += 1
        except Exception:
            pass
        count += 1
        if count % 20 == 0: await asyncio.sleep(1)

    await message.answer(f"✅ Xabar yuborildi!\n🟢 Muvaffaqiyatli: {success}\n🔴 Xato: {count - success}", reply_markup=admin_menu())
    await state.clear()

# --- STATISTICS ---
@dp.message(F.text == "📊 Mukammal Statistika")
async def stats_cmd(message: types.Message):
    if not await is_admin(message.from_user.id): return
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT COUNT(*) FROM users") as c1: u = (await c1.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM anime") as c2: a = (await c2.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM episodes") as c3: e = (await c3.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM channels") as c4: ch = (await c4.fetchone())[0]

    await message.answer(
        f"📊 **BOT STATISTIKASI**\n\n"
        f"👥 Barcha foydalanuvchilar: **{u} ta**\n"
        f"🎬 Animelar soni: **{a} ta**\n"
        f"📹 Qismlar soni: **{e} ta**\n"
        f"📢 Majburiy kanallar: **{ch} ta**",
        parse_mode="Markdown"
    )

# --- ADMIN MANAGEMENT ---
@dp.message(F.text == "👥 Adminlar ro'yxati")
async def show_admins(message: types.Message):
    if not await is_admin(message.from_user.id): return
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT user_id FROM admins") as cursor:
            admins = await cursor.fetchall()

    text = f"👑 **Asosiy Admin:** `{ADMIN_ID}`\n\n👥 **Yordamchi Adminlar:**\n"
    if admins:
        for idx, (uid,) in enumerate(admins, 1):
            text += f"{idx}. `{uid}`\n"
    else:
        text += "Hozircha qo'shimcha adminlar yo'q."

    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "👤 Admin qo'shish")
async def admin_add_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Admin qo'shish huquqi faqat asosiy adminga berilgan!")
        return
    await state.set_state(AdminState.user_id)
    await message.answer("Yangi adminning Telegram **ID**sini kiriting:")

@dp.message(AdminState.user_id)
async def admin_save(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ ID faqat raqamlardan iborat bo'lishi kerak!")
        return
    new_id = int(message.text.strip())
    
    if new_id == ADMIN_ID:
        await message.answer("⚠️ Bu ID asosiy admin IDsi bilan bir xil!")
        await state.clear()
        return

    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (new_id,))
        await conn.commit()
    await message.answer(f"✅ `{new_id}` muvaffaqiyatli admin qilindi!", reply_markup=admin_menu(), parse_mode="Markdown")
    await state.clear()

@dp.message(F.text == "🗑 Admin o'chirish")
async def admin_del_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Admin o'chirish huquqi faqat asosiy adminga berilgan!")
        return
    await state.set_state(AdminState.del_user_id)
    await message.answer("O'chirmoqchi bo'lgan adminning Telegram **ID**sini kiriting:")

@dp.message(AdminState.del_user_id)
async def admin_delete_save(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ ID faqat raqamlardan iborat bo'lishi kerak!")
        return
    
    target_id = int(message.text.strip())
    if target_id == ADMIN_ID:
        await message.answer("❌ Asosiy adminni o'chirib bo'lmaydi!")
        await state.clear()
        return

    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT user_id FROM admins WHERE user_id = ?", (target_id,)) as cursor:
            admin_exists = await cursor.fetchone()
        
        if admin_exists:
            await conn.execute("DELETE FROM admins WHERE user_id = ?", (target_id,))
            await conn.commit()
            await message.answer(f"🗑 `{target_id}` adminlikdan olib tashlandi!", reply_markup=admin_menu(), parse_mode="Markdown")
        else:
            await message.answer("❌ Bunday IDli admin ro'yxatda topilmadi.")

    await state.clear()

# --- SEARCH & DELIVERY ---
@dp.message(F.text & ~F.text.startswith("/"))
async def search_anime(message: types.Message):
    if not BOT_ACTIVE and not await is_admin(message.from_user.id): return

    unsubbed = await check_subscribes(message.from_user.id)
    if unsubbed and not await is_admin(message.from_user.id):
        await start_cmd(message, None)
        return

    code = message.text.strip()
    await send_anime_by_code(message, code)

@dp.callback_query(F.data.startswith("play_"))
async def play_ep(call: types.CallbackQuery):
    _, code, season, ep_num = call.data.split("_")
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT file_id FROM episodes WHERE anime_code = ? AND season = ? AND ep_num = ?", (code, int(season), int(ep_num))) as cursor:
            res = await cursor.fetchone()
    if res:
        await call.message.answer_video(video=res[0], caption=f"📹 {season}-Fasl | {ep_num}-Qism")
        await call.answer()

# --- MAIN RUNNER ---
async def main():
    logging.basicConfig(level=logging.INFO)
    await init_db()
    await start_web_server()
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
