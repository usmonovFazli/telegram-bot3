import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    FSInputFile
)
from dotenv import load_dotenv

import database as db

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher()

logging.basicConfig(level=logging.INFO)


# ------------------------------------------------------
# Главное меню
# ------------------------------------------------------
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🎥 Отправить")],
        [KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="📥 Экспорт Excel")],
        [KeyboardButton(text="🚪 Покинуть все чаты")]
    ],
    resize_keyboard=True
)


# ------------------------------------------------------
# START
# ------------------------------------------------------
@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer("Выберите действие:", reply_markup=main_kb)


# ------------------------------------------------------
# ОТПРАВКА СООБЩЕНИЙ
# ------------------------------------------------------
user_states = {}  # user_id → {"file": ..., "text": ...}


@dp.message(lambda m: m.text == "🎥 Отправить")
async def ask_media(message: types.Message):
    user_states[message.from_user.id] = {"file": None, "text": None}
    await message.answer("Отправьте видео, фото или текст.")


@dp.message(lambda m: m.from_user.id in user_states)
async def handle_send(message: types.Message):
    state = user_states.get(message.from_user.id)
    if not state:
        return

    # -------- медиа --------
    if message.video or message.photo:
        state["file"] = message.video or message.photo[-1]
        state["text"] = message.caption if message.caption else None

    # -------- текст --------
    elif message.text and state["file"] is None:
        state["text"] = message.text

    # Все чаты
    channels = db.get_channels()
    sent_count = 0

    for ch in channels:
        chat_id = ch[0]

        try:
            # видео
            if state["file"] and message.video:
                await bot.send_video(
                    chat_id=chat_id,
                    video=state["file"].file_id,
                    caption=state["text"] or ""
                )

            # фото
            elif state["file"] and message.photo:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=state["file"].file_id,
                    caption=state["text"] or ""
                )

            # текст
            else:
                await bot.send_message(chat_id, state["text"])

            db.increment_video_count(chat_id)
            sent_count += 1

        except Exception as e:
            print(f"Ошибка отправки в {chat_id}: {e}")

    # Общий охват
    total_members = sum([c[2] for c in channels])

    await message.answer(
        f"✅ Сообщение отправлено в {sent_count} чатов.\n"
        f"👥 Общий охват: {total_members} участников."
    )

    user_states.pop(message.from_user.id, None)


# ------------------------------------------------------
# СТАТИСТИКА
# ------------------------------------------------------
@dp.message(lambda m: m.text == "📊 Статистика")
async def stats(message: types.Message):
    channels = db.get_channels()

    total = len(channels)
    supergroups = len([c for c in channels if c[5] == "supergroup"])
    groups = len([c for c in channels if c[5] == "group"])
    max_videos = max([c[3] for c in channels], default=0)

    text = (
        f"📊 *Общая статистика*\n\n"
        f"📌 Всего чатов: {total}\n"
        f"💬 Супергрупп: {supergroups}\n"
        f"👥 Групп: {groups}\n"
        f"🔥 Максимальное количество отправок в один чат: {max_videos}"
    )

    await message.answer(text, parse_mode="Markdown")


# ------------------------------------------------------
# ЭКСПОРТ EXCEL
# ------------------------------------------------------
@dp.message(lambda m: m.text == "📥 Экспорт Excel")
async def export_excel(message: types.Message):
    path = db.export_excel()

    if not os.path.exists(path):
        await message.answer("Ошибка: файл не найден.")
        return

    await message.answer_document(FSInputFile(path))


# ------------------------------------------------------
# ПОКИНУТЬ ВСЕ ЧАТЫ
# ------------------------------------------------------
@dp.message(lambda m: m.text == "🚪 Покинуть все чаты")
async def leave_all_chats(message: types.Message):
    channels = db.get_channels()
    left = 0

    for ch in channels:
        chat_id = ch[0]

        try:
            await bot.leave_chat(chat_id)
            db.delete_channel(chat_id)
            left += 1
        except Exception as e:
            print(f"Ошибка выхода из {chat_id}: {e}")

    await message.answer(
        f"🚪 Бот покинул {left} чатов.\n"
        f"🧹 База очищена."
    )


# ------------------------------------------------------
# ЗАПУСК БОТА
# ------------------------------------------------------
if __name__ == "__main__":
    import asyncio

    async def main():
        db.init_db()
        await dp.start_polling(bot)

    asyncio.run(main())
