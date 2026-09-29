"""
database.py - Supabase (PostgreSQL) versiyasi.

Kerak: requirements.txt ga `asyncpg` qo'shing, `aiosqlite` ni olib tashlang.
Environment variable: DATABASE_URL  (Supabase Session pooler URI)

main.py da `import aiosqlite` o'rniga `import database as aiosqlite` yozilsa,
`aiosqlite.connect(DB_NAME)`, `await conn.execute(...)`,
`async with conn.execute(...) as cursor`, `fetchone()`, `fetchall()`, `commit()`
va `?` belgili so'rovlar o'zgarishsiz ishlayveradi.
"""
import os
import re

import asyncpg

DATABASE_URL = os.getenv("DATABASE_URL")

_pool = None

# INSERT OR REPLACE ni Postgres'ga o'girish uchun har bir jadvalning kaliti
_PK = {
    "users": "user_id",
    "admins": "user_id",
    "anime": "code",
    "auto_channels": "ch_id",
}

_OR_IGNORE = re.compile(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO", re.I)
_OR_REPLACE = re.compile(r"^\s*INSERT\s+OR\s+REPLACE\s+INTO\s+(\w+)\s*\(([^)]*)\)", re.I)


def _convert(sql: str) -> str:
    """SQLite so'rovini PostgreSQL so'roviga o'giradi."""
    sql = sql.strip().rstrip(";")

    if _OR_IGNORE.match(sql):
        sql = _OR_IGNORE.sub("INSERT INTO", sql, count=1) + " ON CONFLICT DO NOTHING"
    else:
        m = _OR_REPLACE.match(sql)
        if m:
            table = m.group(1).lower()
            cols = [c.strip() for c in m.group(2).split(",")]
            pk = _PK.get(table)
            if pk is None:
                raise ValueError(f"INSERT OR REPLACE: '{table}' jadvali uchun kalit _PK da yo'q")
            sets = [f"{c}=EXCLUDED.{c}" for c in cols if c != pk]
            sql = re.sub(r"INSERT\s+OR\s+REPLACE\s+INTO", "INSERT INTO", sql, count=1, flags=re.I)
            sql += f" ON CONFLICT ({pk}) " + (
                f"DO UPDATE SET {', '.join(sets)}" if sets else "DO NOTHING"
            )

    # ? -> $1, $2, ...
    out, n = [], 0
    for ch in sql:
        if ch == "?":
            n += 1
            out.append(f"${n}")
        else:
            out.append(ch)
    return "".join(out)


class _Cursor:
    def __init__(self, rows=None, rowcount=-1):
        self._rows = [tuple(r) for r in (rows or [])]
        self._i = 0
        self.rowcount = rowcount

    async def fetchone(self):
        if self._i >= len(self._rows):
            return None
        row = self._rows[self._i]
        self._i += 1
        return row

    async def fetchall(self):
        rows = self._rows[self._i:]
        self._i = len(self._rows)
        return rows


class _Execute:
    """`await db.execute(...)` ham, `async with db.execute(...) as cur` ham ishlashi uchun."""

    def __init__(self, coro):
        self._coro = coro

    def __await__(self):
        return self._coro.__await__()

    async def __aenter__(self):
        return await self._coro

    async def __aexit__(self, *exc):
        return False


class _Connection:
    def __init__(self):
        self._c = None

    async def __aenter__(self):
        if _pool is None:
            raise RuntimeError("Avval `await init_db()` ni chaqiring")
        self._c = await _pool.acquire()
        return self

    async def __aexit__(self, *exc):
        await _pool.release(self._c)
        self._c = None
        return False

    async def _run(self, sql, params):
        q = _convert(sql)
        params = tuple(params or ())
        up = q.lstrip().upper()
        if up.startswith(("SELECT", "WITH")) or " RETURNING " in up:
            rows = await self._c.fetch(q, *params)
            return _Cursor(rows, len(rows))
        status = await self._c.execute(q, *params)
        try:
            rc = int(status.split()[-1])
        except (ValueError, IndexError):
            rc = -1
        return _Cursor([], rc)

    def execute(self, sql, params=()):
        return _Execute(self._run(sql, params))

    async def executemany(self, sql, seq):
        await self._c.executemany(_convert(sql), [tuple(p) for p in seq])

    async def commit(self):
        pass  # asyncpg har so'rovni avtomatik commit qiladi


def connect(*_args, **_kwargs):
    """aiosqlite.connect(DB_NAME) o'rnida ishlashi uchun argumentlar e'tiborsiz qoldiriladi."""
    return _Connection()


async def init_db():
    global _pool
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable o'rnatilmagan")

    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=DATABASE_URL,
            min_size=1,
            max_size=5,
            ssl="require",
            statement_cache_size=0,  # Supabase pooler (pgbouncer) uchun shart
        )

    async with _pool.acquire() as conn:
        # Telegram ID lari 32-bitdan katta bo'lishi mumkin -> BIGINT
        await conn.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY)")
        await conn.execute("CREATE TABLE IF NOT EXISTS admins (user_id BIGINT PRIMARY KEY)")
        await conn.execute("CREATE TABLE IF NOT EXISTS anime (code TEXT PRIMARY KEY, title TEXT)")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                id BIGSERIAL PRIMARY KEY,
                anime_code TEXT,
                season INTEGER,
                ep_num INTEGER,
                file_id TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                id BIGSERIAL PRIMARY KEY,
                ch_id BIGINT,
                ch_type TEXT,
                title TEXT,
                link TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS extra_links (
                id BIGSERIAL PRIMARY KEY,
                title TEXT,
                url TEXT
            )
        """)
        await conn.execute("CREATE TABLE IF NOT EXISTS auto_channels (ch_id BIGINT PRIMARY KEY)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_episodes_lookup ON episodes (anime_code, season, ep_num)")


async def close_db():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
