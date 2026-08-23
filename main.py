# --- FSM STATES ---
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

# --- MENUS ---
def admin_menu():
    kb = [
        [KeyboardButton(text="➕ Anime qo‘shish"), KeyboardButton(text="➕ Qism qo‘shish")],
        [KeyboardButton(text="📦 Ommaviy qism qo'shish")],
        [KeyboardButton(text="✏️ Anime tahrirlash"), KeyboardButton(text="🗑 Anime o‘chirish")],
        [KeyboardButton(text="📢 Majburiy kanallar"), KeyboardButton(text="🔗 Qo'shimcha linklar")],
        [KeyboardButton(text="📢 Avto-kanal biriktirish"), KeyboardButton(text="📨 Xabar yuborish")],
        [KeyboardButton(text="📊 Mukammal Statistika"), KeyboardButton(text="👥 Adminlar ro'yxati")],
        [KeyboardButton(text="👤 Admin qo'shish"), KeyboardButton(text="🗑 Admin o'chirish")],
        [KeyboardButton(text="⚙️ Bot holati")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
