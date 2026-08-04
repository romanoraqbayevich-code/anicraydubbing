import asyncio
import logging
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, CommandObject
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

# --- RENDER TIMED OUT BO'LMASLIGI UCHUN WEB-SERVER ---
async def handle_health_check(request):
    return web.Response(text="OK", status=200)

async def start_background_web_server():
    app = web.Application()
    app.router.add_get("/", handle_health_check)
    app.router.add_get("/health", handle_health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

# --- FSM STATES ---
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

class DeleteFSM(StatesGroup):
    code = State()

class AutoChannelFSM(StatesGroup):
    channel_id = State()

# --- HELPER FUNKSIYALAR ---
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

def admin_menu():
    kb = [
        [KeyboardButton(text="➕ Anime qo‘shish"), KeyboardButton(text="➕ Qism qo‘shish")],
        [KeyboardButton(text="🗑 Anime o‘chirish"), KeyboardButton(text="📢 Kanallar boshqaruvi")],
        [KeyboardButton(text="🤖 Avto-kanal sozlash"), KeyboardButton(text="📊 Statistika")],
        [KeyboardButton(text="⚙️ Bot holatini boshqarish")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- ANIME CHIQARISH YORDAMCHI FUNKSIYASI ---
async def send_anime_info(chat_id: int, code: str):
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
        
        await bot.send_photo(chat_id=chat_id, photo=poster, caption=f"🎬 **{title}**\n\n📝 {desc}\n\n🔢 Kodi: `{code}`", reply_markup=ikb)
    else:
        await bot.send_message(chat_id=chat_id, text="❌ Bunday kodli anime topilmadi.")

# --- HANDLERS ---

@dp.message(CommandStart())
async def start_cmd(message: types.Message, command: CommandObject):
    user_id = message.from_user.id
    
    # Bazaga foydalanuvchini qo'shish
    async with aiosqlite.connect(db.DB_NAME) as conn:
        await conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        await conn.commit()

    # Deep-linking parametri (masalan: kanaldan /start 105 bo'lib kirsa)
    code_param = command.args if command.args else None

    # Obunani tekshirish
    if not await is_admin(user_id):
        subscribed = await check_subscription(user_id)
        if not subscribed:
            async with aiosqlite.connect(db.DB_NAME) as conn:
                async with conn.execute("SELECT invite_link FROM channels") as cursor:
                    links = await cursor.fetchall()
            
            ikb_list = [[InlineKeyboardButton(text=f"📢 {i+1}-Kanal", url=link[0])] for i, link in enumerate(links)]
            
            # Agar kanaldan kod orqali kelgan bo'lsa, tekshirish tugmasiga kodni biriktiramiz
            cb_data = f"check_sub_{code_param}" if code_param else "check_sub_none"
            ikb_list.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data=cb_data)])
            ikb = InlineKeyboardMarkup(inline_keyboard=ikb_list)
            
            await message.answer("⚠️ Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling:", reply_markup=ikb)
            return

    # Obunasi bo'lsa yoki admin bo'lsa:
    if code_param:
        await send_anime_info(message.chat.id, code_param)
    else:
        if await is_admin(user_id):
            await message.answer("🔧 **Boshqaruv paneli:**", reply_markup=admin_menu())
        else:
            await message.answer("👋 Xush kelibsiz! Ko'rmoqchi bo'lgan anime **KODI**ni yuboring:")

@dp.callback_query(F.data.startswith("check_sub_"))
async def check_sub_callback(call: types.CallbackQuery):
    user_id = call.from_user.id
    code_param = call.data.split("_")[2]
    
    if await check_subscription(user_id):
        await call.message.delete()
        await call.message.answer("✅ Obuna tasdiqlandi!")
        if code_param != "none":
            await send_anime_info(call.message.chat.id, code_param)
        else:
            await call.message.answer("Ko'rmoqchi bo'lgan anime **KODI**ni yuboring:")
    else:
        await call.answer("❌ Hali barcha kanallarga a'zo bo'lmadingiz!", show_alert=True)

# --- FASLLAR VA QISMLAR TUGMALARI ---

@dp.callback_query(F.data.startswith("season_"))
async def show_episodes_list(call: types.CallbackQuery):
    _, code, season = call.data.split("_")
    async with aiosqlite.connect(db.DB_NAME) as conn:
        async with conn.execute(
            "SELECT episode_num FROM episodes WHERE anime_code = ? AND season = ? ORDER BY episode_num ASC", 
            (code, int(season))
        ) as cursor:
            episodes = await cursor.fetchall()

    if episodes:
        ikb_list = []
        row = []
        for ep in episodes:
            ep_num = ep[0]
            row.append(InlineKeyboardButton(text=f"▶️ {ep_num}-qism", callback_data=f"getep_{code}_{season}_{ep_num}"))
            if len(row) == 2:  # Har bir qatorda 2 tadan tugma
                ikb_list.append(row)
                row = []
        if row:
            ikb_list.append(row)
            
        ikb = InlineKeyboardMarkup(inline_keyboard=ikb_list)
        await call.message.answer(f"🎞 **{season}-Fasl qismlarini tanlang:**", reply_markup=ikb)
    else:
        await call.answer("Ushbu faslda hali qismlar yo'q.", show_alert=True)

# AYNAN TANLANGAN QISMNI YUBORISH
@dp.callback_query(F.data.startswith("getep_"))
async def send_single_episode(call: types.CallbackQuery):
    _, code, season, ep_num = call.data.split("_")
    
    async with aiosqlite.connect(db.DB_NAME) as conn:
        async with conn.execute(
            "SELECT file_id FROM episodes WHERE anime_code = ? AND season = ? AND episode_num = ?", 
            (code, int(season), int(ep_num))
        ) as cursor:
            ep = await cursor.fetchone()

    if ep:
        file_id = ep[0]
        await call.answer(f"{ep_num}-qism yuklanmoqda...")
        try:
            await bot.send_video(chat_id=call.from_user.id, video=file_id, caption=f"▶️ **{season}-Fasl {ep_num}-Qism**")
        except Exception:
            await bot.send_document(chat_id=call.from_user.id, document=file_id, caption=f"▶️ **{season}-Fasl {ep_num}-Qism**")
    else:
        await call.answer("❌ Qism topilmadi.", show_alert=True)

# --- MAJBURIY KANALLARNI BOSHQARISH (QO'SHISH / O'CHIRISH) ---

@dp.message(F.text == "📢 Kanallar boshqaruvi")
async def channels_menu(message: types.Message):
    if not await is_admin(message.from_user.id): return
    
    async with aiosqlite.connect(db.DB_NAME) as conn:
        async with conn.execute("SELECT id, channel_id FROM channels") as cursor:
            channels = await cursor.fetchall()
            
    text = "📢 **Majburiy obuna kanallari ro'yxati:**\n\n"
    ikb_list = []
    
    if channels:
        for ch_id_db, ch_tg_id in channels:
            text += f"🔹 {ch_tg_id}\n"
            ikb_list.append([InlineKeyboardButton(text=f"❌ O'chirish: {ch_tg_id}", callback_data=f"delchan_{ch_id_db}")])
    else:
        text += "Hali hech qanday kanal qo'shilmagan."
        
    ikb_list.append([InlineKeyboardButton(text="➕ Yangi kanal qo'shish", callback_data="add_new_channel")])
    ikb = InlineKeyboardMarkup(inline_keyboard=ikb_list)
    
    await message.answer(text, reply_markup=ikb)

@dp.callback_query(F.data == "add_new_channel")
async def add_ch_start(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(ChannelFSM.channel_id)
    await call.message.answer("Kanal ID yoki username'sini kiriting (masalan: `@mychannel` yoki `-100123456789`):")

@dp.message(ChannelFSM.channel_id)
async def ch_id_save(message: types.Message, state: FSMContext):
    await state.update_data(channel_id=message.text.strip())
    await state.set_state(ChannelFSM.invite_link)
    await message.answer("Kanal taklif havolasini (Invite Link) kiriting:")

@dp.message(ChannelFSM.invite_link)
async def ch_link_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(db.DB_NAME) as conn:
        await conn.execute("INSERT INTO channels (channel_id, invite_link) VALUES (?, ?)", (data['channel_id'], message.text.strip()))
        await conn.commit()
    await message.answer("✅ Kanal majburiy obuna ro'yxatiga saqlandi!")
    await state.clear()

@dp.callback_query(F.data.startswith("delchan_"))
async def delete_channel(call: types.CallbackQuery):
    ch_db_id = call.data.split("_")[1]
    async with aiosqlite.connect(db.DB_NAME) as conn:
        await conn.execute("DELETE FROM channels WHERE id = ?", (int(ch_db_id),))
        await conn.commit()
    await call.answer("🗑 Kanal muvaffaqiyatli o'chirildi!", show_alert=True)
    await call.message.delete()

# --- QISM QO'SHISH VA KANALGA AVTO-POSTING (DEEP LINK BILAN) ---

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
    await message.answer("Qism raqamini kiriting (masalan: 12):")

@dp.message(EpisodeFSM.episode)
async def add_ep_num(message: types.Message, state: FSMContext):
    await state.update_data(episode=int(message.text))
    await state.set_state(EpisodeFSM.file_id)
    await message.answer("Qism **VIDEO**sini yuboring:")

@dp.message(EpisodeFSM.file_id)
async def add_ep_file(message: types.Message, state: FSMContext):
    video_id = message.video.file_id if message.video else (message.document.file_id if message.document else None)
    if not video_id:
        await message.answer("❌ Iltimos, **VIDEO** yuboring!")
        return
    
    data = await state.get_data()
    bot_info = await bot.get_me()
    
    async with aiosqlite.connect(db.DB_NAME) as conn:
        await conn.execute(
            "INSERT INTO episodes (anime_code, season, episode_num, file_id) VALUES (?, ?, ?, ?)",
            (data['anime_code'], data['season'], data['episode'], video_id)
        )
        await conn.commit()
        
        async with conn.execute("SELECT title, poster_id FROM animes WHERE code = ?", (data['anime_code'],)) as c1:
            anime_info = await c1.fetchone()
        async with conn.execute("SELECT value FROM settings WHERE key='auto_channel'") as c2:
            auto_ch = await c2.fetchone()

    await message.answer(f"✅ `{data['anime_code']}` kodli animega {data['season']}-Fasl {data['episode']}-Qism qo'shildi!")

    # AVTO-POSTING (KANALGA TUGMA BILAN CHIQARISH)
    if auto_ch and anime_info:
        ch_id = auto_ch[0]
        title, poster_id = anime_info
        
        # Botga to'g'ridan-to me o'tuvchi havola (Start deep-link)
        bot_link = f"https://t.me/{bot_info.username}?start={data['anime_code']}"
        ikb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎬 Animeni tomosha qilish", url=bot_link)]
        ])

        caption = f"🎬 **YANGI QISM CHIQDI!**\n\n📌 **Anime:** {title}\n🎞 **{data['season']}-Fasl {data['episode']}-Qism**\n\n👇 Pastdagi tugma orqali tomosha qiling:"
        
        try:
            await bot.send_photo(chat_id=ch_id, photo=poster_id, caption=caption, reply_markup=ikb)
        except Exception:
            try:
                await bot.send_message(chat_id=ch_id, text=caption, reply_markup=ikb)
            except Exception:
                pass

    await state.clear()

# --- QOLGAN STANDART MENYULAR ---

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
    except Exception:
        await message.answer("❌ Bu kod bazada mavjud! Boshqa kod bilan qaytadan urining.")
    await state.clear()

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
    await message.answer(f"🗑 **{code}** kodli anime o'chirildi!")
    await state.clear()

@dp.message(F.text == "🤖 Avto-kanal sozlash")
async def auto_ch_start(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id): return
    await state.set_state(AutoChannelFSM.channel_id)
    await message.answer("Postlar tushadigan kanal ID yoki username'ini kiriting (masalan: `@mychannel`):")

@dp.message(AutoChannelFSM.channel_id)
async def auto_ch_save(message: types.Message, state: FSMContext):
    ch_id = message.text.strip()
    async with aiosqlite.connect(db.DB_NAME) as conn:
        await conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('auto_channel', ?)", (ch_id,))
        await conn.commit()
    await message.answer(f"✅ **{ch_id}** avto-post kanali sifatida biriktirildi!")
    await state.clear()

@dp.message(F.text == "📊 Statistika")
async def show_stats(message: types.Message):
    if not await is_admin(message.from_user.id): return
    async with aiosqlite.connect(db.DB_NAME) as conn:
        async with conn.execute("SELECT COUNT(*) FROM users") as c1: u_cnt = (await c1.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM animes") as c2: a_cnt = (await c2.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM episodes") as c3: e_cnt = (await c3.fetchone())[0]
        
    await message.answer(f"📊 **Statistika:**\n\n👤 A'zolar: **{u_cnt}**\n🎬 Animelar: **{a_cnt}**\n🎞 Qismlar: **{e_cnt}**")

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

@dp.message(F.text)
async def search_anime_by_code(message: types.Message):
    code = message.text.strip()
    if not await is_admin(message.from_user.id):
        if not await check_subscription(message.from_user.id):
            await start_cmd(message, CommandObject())
            return
            
    await send_anime_info(message.chat.id, code)

async def main():
    logging.basicConfig(level=logging.INFO)
    await db.init_db()
    await start_background_web_server()
    print("Bot muvaffaqiyatli ishga tushdi...")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
