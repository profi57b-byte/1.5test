"""
Модуль для логирования действий пользователей бота
"""
import logging
from datetime import datetime
from aiogram import Bot
from aiogram.types import Message

logger = logging.getLogger(__name__)


class BotLogger:
    """Класс для отправки логов в Telegram чат"""

    def __init__(self, bot: Bot, chat_id: str):
        self.bot = bot
        self.chat_id = chat_id
        self.enabled = bool(chat_id and chat_id != 'YOUR_LOG_CHAT_ID')
        self._pending: dict = {}  # user_id -> dict с данными входящего сообщения

    def _parse_message_content(self, message: Message):
        """Разбирает тип сообщения, возвращает (текст_описания, media_type или None)."""
        if message.text:
            return f"📝 Текст: {message.text}", None
        elif message.sticker:
            return f"🖼 Стикер {message.sticker.emoji or ''}", "sticker"
        elif message.photo:
            cap = f" с подписью: {message.caption}" if message.caption else ""
            return f"📷 Фото{cap}", "photo"
        elif message.video:
            cap = f": {message.caption}" if message.caption else ""
            return f"🎥 Видео{cap}", "video"
        elif message.document:
            cap = f" ({message.caption})" if message.caption else ""
            return f"📄 Документ: {message.document.file_name}{cap}", "document"
        elif message.audio:
            cap = f" ({message.caption})" if message.caption else ""
            title = message.audio.title or message.audio.file_name
            return f"🎵 Аудио: {title}{cap}", "audio"
        elif message.voice:
            return "🎤 Голосовое сообщение", "voice"
        elif message.animation:
            cap = f": {message.caption}" if message.caption else ""
            return f"🖼 GIF{cap}", "animation"
        elif message.contact:
            return f"📞 Контакт: {message.contact.first_name} {message.contact.last_name or ''}", None
        elif message.location:
            return f"📍 Местоположение: {message.location.latitude}, {message.location.longitude}", None
        elif message.poll:
            return f"📊 Опрос: {message.poll.question}", None
        else:
            return f"📦 Другое сообщение (тип: {message.content_type})", None

    async def store_incoming(self, message: Message, role: str, employee_name: str = None):
        """
        Сохраняет входящее сообщение для отложенного объединённого логирования.
        employee_name — имя сотрудника из БД (вместо юзернейма).
        """
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        username = message.from_user.username or str(message.from_user.id)
        display_name = employee_name if employee_name else f"@{username}"
        user_info = f"{display_name} (ID: {message.from_user.id})"

        content, media_type = self._parse_message_content(message)

        self._pending[message.from_user.id] = {
            'timestamp': timestamp,
            'role': role,
            'user_info': user_info,
            'content': content,
            'media_type': media_type,
            'message': message,
        }

    async def flush_with_action(self, user_id: int, action: str):
        """
        Объединяет сохранённое входящее сообщение с действием обработчика
        и отправляет один объединённый лог.
        Если для user_id нет pending-записи — просто вызывает log_action.
        """
        pending = self._pending.pop(user_id, None)
        if not pending:
            await self.log_action(str(user_id), action)
            return

        log_line = (
            f"[{pending['timestamp']}] {pending['role']} {pending['user_info']}\n"
            f"{action}\n"
            f"{pending['content']}"
        )
        logger.info(log_line)
        if self.enabled:
            try:
                await self.bot.send_message(self.chat_id, log_line)
                if pending['media_type']:
                    await self.bot.forward_message(
                        chat_id=self.chat_id,
                        from_chat_id=pending['message'].chat.id,
                        message_id=pending['message'].message_id
                    )
            except Exception as e:
                logger.error(f"Ошибка при отправке объединённого лога: {e}")

    async def flush_pending(self, user_id: int):
        """
        Отправляет сохранённый лог без действия (если обработчик не вызвал flush_with_action).
        Вызывается в конце middleware.
        """
        pending = self._pending.pop(user_id, None)
        if not pending:
            return
        log_line = (
            f"[{pending['timestamp']}] {pending['role']} {pending['user_info']}\n"
            f"{pending['content']}"
        )
        logger.info(log_line)
        if self.enabled:
            try:
                await self.bot.send_message(self.chat_id, log_line)
                if pending['media_type']:
                    await self.bot.forward_message(
                        chat_id=self.chat_id,
                        from_chat_id=pending['message'].chat.id,
                        message_id=pending['message'].message_id
                    )
            except Exception as e:
                logger.error(f"Ошибка при отправке лога: {e}")

    async def log_action(self, username: str, action: str):
        """Отправить лог напрямую (для callback-обработчиков и системных сообщений)."""
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            log_message = f"[{timestamp}] Пользователь @{username} {action}"
            logger.info(log_message)
            if self.enabled:
                await self.bot.send_message(self.chat_id, f"📝 {log_message}")
        except Exception as e:
            logger.error(f"Ошибка при отправке лога: {e}")

    async def log_action_silent(self, username: str, action: str):
        """Логирует только локально, без отправки в Telegram (для частых обновлений типа рублемера)."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        logger.info(f"[{timestamp}] @{username} {action}")

    async def log_error(self, username: str, error_text: str):
        """Отправить лог ошибки в чат."""
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            log_message = f"[{timestamp}] ⚠️ ОШИБКА у @{username}: {error_text}"
            logger.error(log_message)
            if self.enabled:
                await self.bot.send_message(self.chat_id, f"🚨 {log_message}")
        except Exception as e:
            logger.error(f"Ошибка при отправке лога ошибки: {e}")

    async def log_incoming_message(self, message: Message, role: str):
        """Устаревший метод — оставлен для совместимости, вызывает store_incoming."""
        await self.store_incoming(message, role)