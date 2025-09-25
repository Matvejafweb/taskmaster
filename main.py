from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from dotenv import load_dotenv
import os
import asyncio
from db import init_db, add_user, get_user, get_tasks, complete_task, delete_task, add_task as db_add_task

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher()

# ===== Клавиатура задач =====
def tasks_keyboard(tasks):
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for i, (task_id, title, xp, is_done) in enumerate(tasks, start=1):
        if not is_done:
            kb.inline_keyboard.append([
                InlineKeyboardButton(
                    text=f"✅ {title} (XP: {xp})",
                    callback_data=f"complete_{task_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Удалить",
                    callback_data=f"delete_{task_id}"
                )
            ])
    return kb

# ===== Главное меню =====
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Профиль")],
        [KeyboardButton(text="➕ Добавить задачу")],
        [KeyboardButton(text="📋 Мои задачи")],
        [KeyboardButton(text="🏆 Рейтинг")]
    ],
    resize_keyboard=True
)

# ===== FSM для добавления задачи =====
class AddTask(StatesGroup):
    waiting_for_title = State()


# ===== Настройки канала =====
CHANNEL_ID = -1002389424026       # ID канала
CHANNEL = '@taskmasterr'          # @username канала (если публичный)

# ===== Проверка подписки =====
CHANNEL_ID = -1002389424026
CHANNEL_LINK = "https://t.me/taskmasterr"

# Асинхронная функция проверки подписки
async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ["member", "creator", "administrator"]
    except Exception:
        return False

# Декоратор для команд
def subscription_required(func):
    async def wrapper(message: types.Message, *args, **kwargs):
        subscribed = await check_subscription(message.from_user.id)
        if not subscribed:
            kb = InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(text="Перейти к каналу", url=CHANNEL_LINK)
                ]]
            )
            await message.answer("🚫 Для использования бота необходимо подписаться на канал.", reply_markup=kb)
            return
        return await func(message)
    return wrapper

# ===== /start =====
@dp.message(Command("start"))
@subscription_required
async def start(message: types.Message):
    await add_user(message.from_user.id, message.from_user.username or "NoName")
    await message.answer(
        f"Привет, {message.from_user.first_name}! Выберите действие в меню ниже.",
        reply_markup=main_menu
    )

# ===== /profile =====
@dp.message(Command("profile"))
@dp.message(lambda msg: msg.text == "📊 Профиль")
async def profile(message: types.Message):
    user = await get_user(message.from_user.id)
    if not user:
        await message.answer("Профиль не найден. Введите /start, чтобы создать профиль.")
        return
    user_id, username, xp, level, tasks_completed = user
    profile_text = (
        f"👤 <b>{username}</b>\n"
        f"⭐ Уровень: <b>{level}</b>\n"
        f"💎 Опыт: <b>{xp}</b>\n"
        f"✅ Выполнено задач: <b>{tasks_completed}</b>"
    )
    await message.answer(profile_text, parse_mode="HTML")

# ===== Добавление задачи =====
@dp.message(Command("add_task"))
@dp.message(lambda msg: msg.text == "➕ Добавить задачу")
async def add_task_start(message: types.Message, state: FSMContext):
    await message.answer("Введите название новой задачи:")
    await state.set_state(AddTask.waiting_for_title)

@dp.message(AddTask.waiting_for_title)
async def add_task_finish(message: types.Message, state: FSMContext):
    title = message.text.strip()
    if not title:
        await message.answer("Название не может быть пустым, попробуйте ещё раз:")
        return
    await db_add_task(message.from_user.id, title)
    await message.answer("Задача добавлена ✅")
    tasks = await get_tasks(message.from_user.id)
    if tasks and any(t[3] == 0 for t in tasks):
        await message.answer("Ваши задачи:", reply_markup=tasks_keyboard(tasks))
    else:
        await message.answer("У вас пока нет активных задач.")
    await state.clear()

# ===== Вывод списка задач =====
@dp.message(Command("tasks"))
@dp.message(lambda msg: msg.text == "📋 Мои задачи")
async def cmd_tasks(message: types.Message):
    tasks = await get_tasks(message.from_user.id)
    if not tasks or all(t[3] == 1 for t in tasks):
        await message.answer("У вас нет активных задач!")
        return
    await message.answer("Ваши задачи:", reply_markup=tasks_keyboard(tasks))

# ===== Выполнение задачи =====
@dp.callback_query(lambda c: c.data and c.data.startswith("complete_"))
async def complete_task_callback(callback: CallbackQuery):
    task_id = int(callback.data.split("_")[1])
    result = await complete_task(callback.from_user.id, task_id)
    if not result:
        await callback.answer("Задача не найдена или уже выполнена.", show_alert=True)
        return
    msg = f"Задача выполнена! 🎉 Вы получили {result['xp_gain']} XP."
    if result["level_up"]:
        msg += f"\n\n🔥 Поздравляем! Новый уровень: {result['new_level']}!"
    await callback.answer(msg, show_alert=True)
    tasks = await get_tasks(callback.from_user.id)
    if tasks and any(t[3] == 0 for t in tasks):
        await callback.message.edit_text("Ваши задачи:", reply_markup=tasks_keyboard(tasks))
    else:
        await callback.message.edit_text("У вас нет активных задач!")

# ===== Удаление задачи =====
@dp.callback_query(lambda c: c.data and c.data.startswith("delete_") and not c.data.startswith("delete_confirm_") and c.data != "delete_cancel")
async def delete_task_confirm(callback: CallbackQuery):
    task_id = int(callback.data.split("_")[1])
    tasks = await get_tasks(callback.from_user.id)
    task_titles = {t[0]: (i+1, t[1]) for i, t in enumerate(tasks) if t[3] == 0}
    if task_id not in task_titles:
        await callback.answer("Задача не найдена ❌", show_alert=True)
        return
    num, title = task_titles[task_id]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data=f"delete_confirm_{task_id}"),
            InlineKeyboardButton(text="❌ Нет", callback_data="delete_cancel")
        ]
    ])
    await callback.message.edit_text(f"Вы уверены, что хотите удалить задачу: <b>{title}</b>? 🗑",
                                     reply_markup=kb, parse_mode="HTML")

@dp.callback_query(lambda c: c.data and c.data.startswith("delete_confirm_"))
async def delete_task_callback(callback: CallbackQuery):
    task_id = int(callback.data.split("_")[2])
    success = await delete_task(callback.from_user.id, task_id)
    if success:
        await callback.answer("Задача удалена 🗑️", show_alert=True)
    else:
        await callback.answer("Задача не найдена ❌", show_alert=True)
    tasks = await get_tasks(callback.from_user.id)
    if tasks and any(t[3] == 0 for t in tasks):
        await callback.message.edit_text("Ваши задачи:", reply_markup=tasks_keyboard(tasks))
    else:
        await callback.message.edit_text("У вас нет активных задач!")

@dp.callback_query(lambda c: c.data == "delete_cancel")
async def delete_cancel(callback: CallbackQuery):
    await callback.answer("Удаление отменено ✅", show_alert=True)
    tasks = await get_tasks(callback.from_user.id)
    if tasks and any(t[3] == 0 for t in tasks):
        await callback.message.edit_text("Ваши задачи:", reply_markup=tasks_keyboard(tasks))
    else:
        await callback.message.edit_text("У вас нет активных задач!")

@dp.message(Command("leaderboard"))
async def leaderboard_cmd(message: types.Message):
    from db import get_leaderboard
    top_users = await get_leaderboard()
    if not top_users:
        await message.answer("Пока нет пользователей в рейтинге.")
        return

    text = "🏆 Топ пользователей:\n\n"
    for i, (username, level, xp, tasks_completed) in enumerate(top_users, start=1):
        text += f"{i}. {username} — ⭐ {level}, 💎 {xp} XP, ✅ {tasks_completed} задач\n"

    await message.answer(text)

@dp.message(lambda msg: msg.text == "🏆 Рейтинг")
async def leaderboard_button(message: types.Message):
    await leaderboard_cmd(message)

# ===== main =====
async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
