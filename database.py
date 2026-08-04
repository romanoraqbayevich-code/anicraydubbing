import aiosqlite

DB_NAME = "anime_bot.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        # Foydalanuvchilar
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY
            )
        """)
        # Adminlar
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY
            )
        """)
        # Kanallar (Ommaviy, Shaxsiy, Zayavka)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT,
                invite_link TEXT,
                type TEXT  -- 'public', 'private', 'request'
            )
        """)
        # Qo'shimcha havolalar
        await db.execute("""
            CREATE TABLE IF NOT EXISTS links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                url TEXT
            )
        """)
        # Animelar
        await db.execute("""
            CREATE TABLE IF NOT EXISTS animes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                title TEXT,
                description TEXT,
                poster_id TEXT,
                seasons_count INTEGER DEFAULT 1
            )
        """)
        # Qismlar
        await db.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                anime_code TEXT,
                season INTEGER,
                episode_num INTEGER,
                file_id TEXT
            )
        """)
        # Bot sozlamalari (Bot statusi va Auto-post kanali)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        
        # Boshlang'ich sozlama: bot holati "active"
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('bot_status', 'active')")
        await db.commit()
