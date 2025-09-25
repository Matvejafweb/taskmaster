import aiosqlite

DB_PATH = "database.db"

# ===== Инициализация базы =====
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            tasks_completed INTEGER DEFAULT 0
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT,
            xp INTEGER DEFAULT 10,
            is_done INTEGER DEFAULT 0,
            remind_at TEXT DEFAULT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """)
# ===== Пользователи =====
async def add_user(user_id: int, username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (id, username) VALUES (?, ?)",
            (user_id, username)
        )
        await db.commit()

async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()
    return user

# ===== Задачи =====
async def add_task(user_id: int, title: str, xp: int = 10, remind_at: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO tasks (user_id, title, xp, remind_at) VALUES (?, ?, ?, ?)",
            (user_id, title, xp, remind_at)
        )
        await db.commit()

async def get_tasks(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, title, xp, is_done FROM tasks WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            tasks = await cursor.fetchall()
    return tasks

async def complete_task(user_id: int, task_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        # Проверяем, что задача есть и не выполнена
        async with db.execute(
            "SELECT xp, is_done FROM tasks WHERE id=? AND user_id=?", (task_id, user_id)
        ) as cursor:
            task = await cursor.fetchone()

        if not task or task[1] == 1:
            return False

        xp_gain = task[0]

        # Обновляем задачу как выполненную
        await db.execute("UPDATE tasks SET is_done=1 WHERE id=?", (task_id,))

        # Получаем текущий xp, уровень и количество выполненных задач
        async with db.execute(
            "SELECT xp, level, tasks_completed FROM users WHERE id=?", (user_id,)
        ) as cursor:
            user = await cursor.fetchone()
        xp, level, tasks_completed = user

        new_xp = xp + xp_gain
        new_level = level
        level_up = False

        # Правило: каждые 100 XP = +1 уровень
        if new_xp >= level * 100:
            new_level += 1
            level_up = True

        # Увеличиваем счетчик выполненных задач
        tasks_completed += 1

        # Обновляем пользователя
        await db.execute(
            "UPDATE users SET xp=?, level=?, tasks_completed=? WHERE id=?",
            (new_xp, new_level, tasks_completed, user_id)
        )
        await db.commit()

        return {"xp_gain": xp_gain, "level_up": level_up, "new_level": new_level}


async def delete_task(user_id: int, task_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM tasks WHERE id = ? AND user_id = ?",
            (task_id, user_id)
        )
        await db.commit()
        return cursor.rowcount > 0

# ===== Новый метод для рейтинга =====
async def get_leaderboard(limit: int = 100):
    """Возвращает топ пользователей по уровню и XP"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT username, level, xp, tasks_completed "
            "FROM users "
            "ORDER BY level DESC, xp DESC "
            "LIMIT ?", (limit,)
        ) as cursor:
            leaderboard = await cursor.fetchall()
    return leaderboard