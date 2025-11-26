import logging
import os
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ChatMemberHandler,
    ContextTypes,
    filters,
)

from database import (
    init_db,
    add_or_update_channel,
    update_channel_status,
    get_channels,
    increment_video_count,
    delete_channel,
    export_excel
)

# --- Загрузка ENV ---
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN", "")
AUTHORIZED_PASSWORD = "@12321231’m’@"
LEAVE_PASSWORD = "1234"

logging.basicConfig(level=logging.INFO)

# --- Состояния ---
authorized_users = set()
leave_confirmations = {}  # user_id -> "confirm" / "password"

# --- Главное меню ---
MAIN_MENU = ReplyKeyboardMarkup(
    [["🎥 Отправить видео/фото", "📊 Статистика"],
     ["📥 Экспорт Excel", "🚪 Покинуть чаты"]],
    resize_keyboard=True
)

# ================================
#        А В Т О Р И З А Ц И Я
# ================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in authorized_users:
        await update.message.reply_text("✅ Добро пожаловать снова!", reply_markup=MAIN_MENU)
        return

    context.user_data["awaiting_password"] = True
    await update.message.reply_text("🔐 Введите пароль для доступа:")


async def handle_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает ТОЛЬКО ввод пароля и ничего больше!
    """
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # --- Пароль для входа ---
    if context.user_data.get("awaiting_password"):
        if text == AUTHORIZED_PASSWORD:
            authorized_users.add(user_id)
            context.user_data["awaiting_password"] = False
            await update.message.reply_text("✅ Доступ разрешён!", reply_markup=MAIN_MENU)
        else:
            await update.message.reply_text("❌ Неверный пароль. Попробуйте снова:")
        return

    # --- Пароль для удаления чатов ---
    if leave_confirmations.get(user_id) == "password":
        await handle_leave_password(update, context)
        return


def check_access(user_id):
    return user_id in authorized_users


# ================================
#     Т Е К С Т / М Е Д И А
# ================================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Сначала проверяем, не вводит ли юзер пароль.
    """
    user_id = update.effective_user.id

    if context.user_data.get("awaiting_password") or leave_confirmations.get(user_id) == "password":
        await handle_password(update, context)
        return

    if not check_access(user_id):
        await update.message.reply_text("⛔️ У вас нет доступа. Введите /start.")
        return

    # если доступ есть → считаем текст рассылкой
    await handle_media(update, context)


async def prompt_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update.effective_user.id):
        await update.message.reply_text("⛔️ Нет доступа. Введите /start.")
        return
    await update.message.reply_text("📤 Отправьте видео, фото или текст.")


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        await update.message.reply_text("⛔️ Нет доступа.")
        return

    chats = get_channels()
    count = 0
    total_members = 0

    caption = update.message.caption or update.message.text or ""
    media_file_id = None
    media_type = None

    if update.message.video:
        media_file_id = update.message.video.file_id
        media_type = "video"
    elif update.message.photo:
        media_file_id = update.message.photo[-1].file_id
        media_type = "photo"
    else:
        media_type = "text"

    for chat_id, title, members, videos, *_ in chats:
        try:
            if media_type == "video":
                await context.bot.send_video(chat_id, media_file_id, caption=caption)
                increment_video_count(chat_id)
            elif media_type == "photo":
                await context.bot.send_photo(chat_id, media_file_id, caption=caption)
            else:
                await context.bot.send_message(chat_id, caption)
            count += 1
            total_members += members or 0
        except Exception as e:
            logging.warning(f"Не удалось отправить в {chat_id}: {e}")

    await update.message.reply_text(
        f"✅ Отправлено в {count} чатов.\n"
        f"👥 Всего участников: {total_members}"
    )


# ================================
#     С Т А Т И С Т И К А
# ================================
async def refresh_members(context: ContextTypes.DEFAULT_TYPE):
    chats = get_channels()

    for chat_id, title, _, _, _, _, link in chats:
        try:
            members = await context.bot.get_chat_member_count(chat_id)
            chat = await context.bot.get_chat(chat_id)

            update_channel_status(
                chat_id,
                title=chat.title,
                members=members,
                chat_type=chat.type,
                link=link
            )
        except Exception as e:
            logging.warning(f"Не удалось обновить {chat_id}: {e}")
            update_channel_status(chat_id, chat_type="left")


async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update.effective_user.id):
        await update.message.reply_text("⛔️ Нет доступа.")
        return

    await update.message.reply_text("♻️ Обновляю данные...")
    await refresh_members(context)

    chats = get_channels()
    if not chats:
        await update.message.reply_text("⚠️ Нет подключённых чатов.")
        return

    total_members = sum(c[2] or 0 for c in chats)

    await update.message.reply_text(
        f"📊 Статистика:\n"
        f"• Чатов: {len(chats)}\n"
        f"• Участников: {total_members}"
    )


# ================================
#     Э К С П О Р Т  E X C E L
# ================================
async def export_excel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_access(update.effective_user.id):
        await update.message.reply_text("⛔️ Нет доступа.")
        return

    await update.message.reply_text("📦 Генерирую Excel...")
    await refresh_members(context)

    file_path = export_excel()
    if not file_path:
        await update.message.reply_text("⚠️ Нет данных.")
        return

    with open(file_path, "rb") as f:
        await update.message.reply_document(InputFile(f, filename="channels.xlsx"))

    os.remove(file_path)


# ================================
#     В Ы Х О Д  И З  Ч А Т О В
# ================================
async def initiate_leave(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_access(user_id):
        await update.message.reply_text("⛔️ Нет доступа.")
        return

    leave_confirmations[user_id] = "confirm"
    markup = ReplyKeyboardMarkup([["✅ Да", "❌ Нет"]], resize_keyboard=True)
    await update.message.reply_text("Выйти из всех чатов?", reply_markup=markup)


async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if leave_confirmations.get(user_id) != "confirm":
        return

    if text == "✅ Да":
        leave_confirmations[user_id] = "password"
        await update.message.reply_text("Введите пароль:")
    else:
        leave_confirmations.pop(user_id, None)
        await update.message.reply_text("❎ Отменено.", reply_markup=MAIN_MENU)


async def handle_leave_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if text != LEAVE_PASSWORD:
        leave_confirmations.pop(user_id, None)
        await update.message.reply_text("❌ Неверный пароль.", reply_markup=MAIN_MENU)
        return

    chats = get_channels()
    left = 0

    for chat_id, *_ in chats:
        try:
            await context.bot.leave_chat(chat_id)
            delete_channel(chat_id)
            left += 1
        except Exception as e:
            logging.warning(f"Не смог выйти из {chat_id}: {e}")

    leave_confirmations.pop(user_id, None)
    await update.message.reply_text(f"🚪 Вышел из {left} чатов.", reply_markup=MAIN_MENU)


# ================================
#   О Б Н О В Л Е Н И Я  Ч А Т О В
# ================================
async def chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.my_chat_member.chat
    new_status = update.my_chat_member.new_chat_member.status

    try:
        members = await context.bot.get_chat_member_count(chat.id)
    except:
        members = -1

    if members != -1 and members < 50:
        try:
            await context.bot.leave_chat(chat.id)
            update_channel_status(chat.id, chat_type="left")
        except:
            pass
        return

    link = f"https://t.me/{chat.username}" if chat.username else ""
    title = chat.title or "Без названия"

    add_or_update_channel(chat.id, title, members, new_status, link)


# ================================
#           Z A P U S K
# ================================
def main():
    init_db()

    app = ApplicationBuilder().token(TOKEN).build()

    # --- Команды ---
    app.add_handler(CommandHandler("start", start))

    # --- Членство в чатах ---
    app.add_handler(ChatMemberHandler(chat_member_update, ChatMemberHandler.MY_CHAT_MEMBER))

    # --- Кнопки меню ---
    app.add_handler(MessageHandler(filters.Regex("^🎥 Отправить видео/фото$"), prompt_media))
    app.add_handler(MessageHandler(filters.Regex("^📊 Статистика$"), show_stats))
    app.add_handler(MessageHandler(filters.Regex("^📥 Экспорт Excel$"), export_excel_handler))
    app.add_handler(MessageHandler(filters.Regex("^🚪 Покинуть чаты$"), initiate_leave))
    app.add_handler(MessageHandler(filters.Regex("^(✅ Да|❌ Нет)$"), handle_confirmation))

    # --- Медиа ---
    app.add_handler(MessageHandler(filters.VIDEO | filters.PHOTO, handle_media))

    # --- Текст (в конце!) ---
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, handle_text))

    logging.info("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
