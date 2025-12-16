"""
Модуль Telegram бота
Управляет отправкой сообщений и уведомлений
"""

from telegram import Bot
import logging

logger = logging.getLogger(__name__)


class TelegramBot:
    """
    Класс для отправки сообщений в Telegram.
    Использует python-telegram-bot для взаимодействия с Telegram API.
    """
    
    def __init__(self, token: str, chat_id: str):
        """
        Инициализация бота.
        
        Args:
            token: Токен Telegram бота от @BotFather
            chat_id: ID чата/канала для отправки сообщений
        """
        self.bot = Bot(token)
        self.chat_id = chat_id
    
    async def send(self, text: str, parse_mode: str = 'Markdown'):
        """
        Отправляет текстовое сообщение в чат.
        
        Args:
            text: Текст сообщения
            parse_mode: Режим парсинга (Markdown или HTML)
        """
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=parse_mode
            )
            logger.debug(f"Сообщение отправлено в чат {self.chat_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения в Telegram: {e}")
    
    async def send_signal_result(self, result: dict):
        """
        Отправляет уведомление о результате сигнала (достижение TP или SL).
        
        Args:
            result: Словарь с данными результата
                - type: тип события (TP1, TP2, TP3_FULL, STOP_LOSS)
                - signal: данные сигнала
                - pnl: процент прибыли/убытка
        """
        symbol = result['signal']['symbol']
        pnl = result['pnl']
        result_type = result['type']
        
        # Формируем сообщение в зависимости от типа события
        if result_type == 'STOP_LOSS':
            emoji = "❌"
            text = f"Стоп-лосс"
        elif result_type == 'TP3_FULL':
            emoji = "🏆"
            text = f"TP3 (закрыто)"
        else:
            emoji = "🎯"
            text = result_type
        
        # Форматируем PnL
        pnl_str = f"+{pnl:.2f}%" if pnl > 0 else f"{pnl:.2f}%"
        
        message = f"{emoji} #{symbol} - {text}: {pnl_str}"
        
        await self.send(message)
