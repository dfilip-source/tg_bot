"""
Модуль команд Telegram бота
Обрабатывает команды пользователей: /start, /force, /stats, /active, /help
"""

from telegram.ext import CommandHandler, Application
import logging

import database as db

logger = logging.getLogger(__name__)


def setup(engine, token: str) -> Application:
    """
    Настраивает Telegram Application с обработчиками команд.
    
    Args:
        engine: Экземпляр Engine для выполнения операций
        token: Токен Telegram бота
        
    Returns:
        Настроенный Application для запуска polling
    """
    app = Application.builder().token(token).build()
    
    async def start(update, context):
        """Обработчик команды /start - приветственное сообщение"""
        welcome_message = """
🤖 *Crypto Signal Bot*

Бот для генерации торговых сигналов на основе технического анализа и машинного обучения.

📌 *Доступные команды:*
├ /force - Принудительно запустить сканирование
├ /stats - Показать статистику
├ /active - Показать активные сигналы
└ /help - Показать справку

⏰ *Автоматическое сканирование:* каждые 4 часа

📊 *Анализируемые монеты:* Топ-250 по маркет капе
"""
        await update.message.reply_text(welcome_message, parse_mode='Markdown')
    
    async def force(update, context):
        """Обработчик команды /force - принудительный запуск сканирования"""
        await update.message.reply_text("🔍 Запускаю сканирование рынка...")
        
        try:
            await engine.run()
            await update.message.reply_text("✅ Сканирование завершено!")
        except Exception as e:
            logger.error(f"Ошибка при сканировании: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    
    async def stats(update, context):
        """Обработчик команды /stats - показать статистику"""
        try:
            message = await engine.stats_manager.format_stats_message()
            await update.message.reply_text(message, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            await update.message.reply_text("❌ Ошибка получения статистики")
    
    async def active(update, context):
        """Обработчик команды /active - показать активные сигналы"""
        try:
            open_trades = db.get_open_trades()
            
            if not open_trades:
                await update.message.reply_text("📭 Нет активных сигналов")
                return
            
            message = f"📋 *Активные сигналы ({len(open_trades)}):*\n\n"
            
            for trade in open_trades:
                side_emoji = "🐂" if trade['side'] == 'LONG' else "🐻"
                tp1_status = "✅" if trade['tp1_hit'] else "⏳"
                tp2_status = "✅" if trade['tp2_hit'] else "⏳"
                
                message += f"""
{side_emoji} *#{trade['symbol']}* ({trade['side']})
├ Вход A: {trade['entry_a']:.4f}
├ Вход B: {trade['entry_b']:.4f if trade['entry_b'] else 'N/A'}
├ SL: {trade['stop']:.4f}
├ TP1 {tp1_status}: {trade['tp1']:.4f}
├ TP2 {tp2_status}: {trade['tp2']:.4f}
└ TP3: {trade['tp3']:.4f}
"""
            
            await update.message.reply_text(message.strip(), parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Ошибка получения активных сигналов: {e}")
            await update.message.reply_text("❌ Ошибка получения активных сигналов")
    
    async def help_command(update, context):
        """Обработчик команды /help - справка"""
        help_message = """
📖 *Справка по боту*

🔹 *Как работает бот:*
Бот анализирует топ-250 криптовалют по маркет капе каждые 4 часа. Использует комбинацию технического анализа (20+ индикаторов) и машинного обучения для генерации сигналов.

🔹 *Типы входов:*
├ Entry A (70%) - основной вход
└ Entry B (30%) - усреднение

🔹 *Уровни:*
├ SL - стоп-лосс на основе ATR
├ TP1 - первая цель (+1 ATR)
├ TP2 - вторая цель (+2 ATR)
└ TP3 - третья цель (+3.5 ATR)

🔹 *Уведомления:*
Бот автоматически уведомляет о достижении каждого TP уровня и срабатывании SL.

🔹 *Disclaimer:*
Сигналы носят информационный характер. Торгуйте на свой риск.
"""
        await update.message.reply_text(help_message, parse_mode='Markdown')
    
    # Регистрируем обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("force", force))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("active", active))
    app.add_handler(CommandHandler("help", help_command))
    
    logger.info("Telegram команды настроены")
    
    return app
