"""
Главный модуль крипто-бота
Инициализирует все компоненты и запускает периодическое сканирование
с использованием APScheduler для планирования задач
"""

import os
import sys
import asyncio
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from data_fetcher import DataFetcher
from signal_generator import SignalGenerator
from telegram_bot import TelegramBot
from telegram_commands import setup
import database as db
from config import (
    MAX_SIGNALS_PER_RUN, SCAN_INTERVAL_HOURS, SIGNAL_CHECK_INTERVAL_MINUTES,
    LOG_FILE, LOG_MAX_SIZE, LOG_BACKUP_COUNT, POSITION_SIZE_A, POSITION_SIZE_B
)
from signal_tracker import SignalTracker
from statistics import StatisticsManager
from technical_analysis import TechnicalAnalyzer
from ml_predictor import MLPredictor


def setup_logging():
    """
    Настраивает систему логирования.
    Логи записываются в консоль и файл с ротацией.
    """
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(console_handler)
    
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=LOG_MAX_SIZE,
        backupCount=LOG_BACKUP_COUNT,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(file_handler)
    
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('telegram').setLevel(logging.WARNING)
    logging.getLogger('apscheduler').setLevel(logging.WARNING)


load_dotenv()
setup_logging()
logger = logging.getLogger(__name__)

db.init_db()

token = os.getenv("TELEGRAM_BOT_TOKEN")
chat_id = os.getenv("TELEGRAM_CHAT_ID")

if not token:
    logger.error("TELEGRAM_BOT_TOKEN не найден в переменных окружения!")
    print("ERROR: TELEGRAM_BOT_TOKEN не найден!")
    print("Создайте файл .env с переменными TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID")
    sys.exit(1)

if not chat_id:
    logger.error("TELEGRAM_CHAT_ID не найден в переменных окружения!")
    print("ERROR: TELEGRAM_CHAT_ID не найден!")
    sys.exit(1)

logger.info(f"Telegram Bot Token загружен (длина: {len(token)})")
logger.info(f"Telegram Chat ID: {chat_id}")

bot = TelegramBot(token, chat_id)


class Engine:
    """
    Основной движок бота.
    Координирует работу всех компонентов.
    """
    
    def __init__(self):
        """Инициализация всех компонентов"""
        self.data_fetcher = DataFetcher()
        self.ta = TechnicalAnalyzer()
        self.ml = MLPredictor()
        self.signal_gen = SignalGenerator(self.ta, self.ml)
        self.tracker = SignalTracker(self.data_fetcher, bot)
        self.stats_manager = StatisticsManager()
        
        logger.info("Engine инициализирован")
    
    async def run(self):
        """
        Основной цикл сканирования рынка.
        """
        logger.info("Запуск сканирования рынка...")
        
        sent = 0
        
        try:
            all_data = await asyncio.get_event_loop().run_in_executor(
                None, self.data_fetcher.fetch_all_coins_data
            )
            
            for symbol, df in all_data.items():
                sig = self.signal_gen.generate(df, symbol)
                
                if sig:
                    db.open_trade(
                        sig.symbol, sig.side, sig.entry_a, sig.entry_b,
                        sig.stop, sig.tp1, sig.tp2, sig.tp3
                    )
                    
                    message = self._format_signal_message(sig)
                    await bot.send(message)
                    sent += 1
                    
                    logger.info(f"Отправлен сигнал #{sent}: {sig.symbol} {sig.side}")
                
                if sent >= MAX_SIGNALS_PER_RUN:
                    logger.info(f"Достигнут лимит сигналов: {MAX_SIGNALS_PER_RUN}")
                    break
            
            logger.info(f"Сканирование завершено. Отправлено сигналов: {sent}")
            
        except Exception as e:
            logger.error(f"Ошибка при сканировании: {e}", exc_info=True)
    
    async def check_signals(self):
        """Проверяет активные сигналы на достижение уровней"""
        logger.debug("Проверка активных сигналов...")
        
        try:
            results = await self.tracker.check_all_signals()
            if results:
                logger.info(f"Обнаружено событий: {len(results)}")
        except Exception as e:
            logger.error(f"Ошибка проверки сигналов: {e}")
    
    def _format_signal_message(self, sig) -> str:
        """Форматирует сигнал для отправки в Telegram."""
        entry_a = sig.entry_a
        entry_b = sig.entry_b
        stop = sig.stop
        tp1 = sig.tp1
        tp2 = sig.tp2
        tp3 = sig.tp3
        side = sig.side
        symbol = sig.symbol
        
        is_long = side == "LONG"
        emoji = "🐂 Лонг" if is_long else "🐻 Шорт"
        entry_text = "(вход с текущих)" if not entry_b else "(2-фазный)"
        
        message = f"*#{symbol}* {emoji} {entry_text}\n"
        message += f"📊 Уверенность: {sig.confidence:.1%}\n\n"
        
        if entry_b:
            message += "*Вход (2-фазный):*\n"
            message += f"├ Вход A: `{entry_a:.4f}` ({POSITION_SIZE_A*100:.0f}%)\n"
            message += f"└ Вход B: `{entry_b:.4f}` ({POSITION_SIZE_B*100:.0f}%)\n\n"
        else:
            message += f"*Вход:* `{entry_a:.4f}`\n\n"
        
        sl_perc_a = abs((entry_a - stop) / entry_a * 100)
        
        if entry_b:
            sl_perc_b = abs((entry_b - stop) / entry_b * 100)
            message += f"*Стоп-лосс:* `{stop:.4f}` 🛡️\n"
            message += f"├ От A: -{sl_perc_a:.1f}%\n"
            message += f"└ От B: -{sl_perc_b:.1f}%\n\n"
        else:
            message += f"*Стоп-лосс:* `{stop:.4f}` 🛡️ (-{sl_perc_a:.1f}%)\n\n"
        
        message += "*Тейк-профиты:*\n"
        
        for tp_num, tp in enumerate([tp1, tp2, tp3], 1):
            perc_a = abs((tp - entry_a) / entry_a * 100)
            rr_a = perc_a / sl_perc_a if sl_perc_a > 0 else 0
            
            if entry_b:
                perc_b = abs((tp - entry_b) / entry_b * 100)
                sl_perc_b = abs((entry_b - stop) / entry_b * 100)
                rr_b = perc_b / sl_perc_b if sl_perc_b > 0 else 0
                
                connector = "├" if tp_num < 3 else "└"
                message += f"{connector} TP{tp_num}: `{tp:.4f}` 🎯\n"
                message += f"  (A: +{perc_a:.1f}% R:{rr_a:.1f} | B: +{perc_b:.1f}% R:{rr_b:.1f})\n"
            else:
                connector = "├" if tp_num < 3 else "└"
                message += f"{connector} TP{tp_num}: `{tp:.4f}` 🎯 (+{perc_a:.1f}%, R:{rr_a:.1f})\n"
        
        return message


engine = Engine()
app = setup(engine, token)

if app is None:
    logger.error("Ошибка создания Telegram Application!")
    sys.exit(1)

scheduler = AsyncIOScheduler()


async def scheduled_scan():
    """Задача планировщика: сканирование рынка"""
    logger.info("Запуск запланированного сканирования...")
    await engine.run()


async def scheduled_check():
    """Задача планировщика: проверка активных сигналов"""
    await engine.check_signals()


async def post_init(application):
    """Callback после инициализации бота - запускаем планировщик"""
    scheduler.add_job(
        scheduled_scan,
        trigger=IntervalTrigger(hours=SCAN_INTERVAL_HOURS),
        id='market_scan',
        name='Сканирование рынка',
        replace_existing=True
    )
    
    scheduler.add_job(
        scheduled_check,
        trigger=IntervalTrigger(minutes=SIGNAL_CHECK_INTERVAL_MINUTES),
        id='signal_check',
        name='Проверка сигналов',
        replace_existing=True
    )
    
    scheduler.start()
    logger.info(f"Планировщик запущен: сканирование каждые {SCAN_INTERVAL_HOURS}ч, проверка каждые {SIGNAL_CHECK_INTERVAL_MINUTES}мин")


def main():
    """Главная функция запуска бота"""
    logger.info("=" * 50)
    logger.info("Запуск Crypto Signal Bot")
    logger.info("=" * 50)
    
    app.post_init = post_init
    
    logger.info("Запуск Telegram бота...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
