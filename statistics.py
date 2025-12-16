"""
Модуль статистики и аналитики
Собирает и форматирует статистику по сигналам и торговле
"""

from typing import Dict, List
import logging

import database as db

logger = logging.getLogger(__name__)


class StatisticsManager:
    """Управление статистикой сигналов и торговли"""
    
    def __init__(self):
        """Инициализация менеджера статистики"""
        pass
    
    async def get_full_stats(self, days: int = 30) -> Dict:
        """
        Получает полную статистику за указанный период.
        
        Args:
            days: Количество дней для анализа (по умолчанию 30)
            
        Returns:
            Словарь со статистикой: total, wins, losses, winrate, pnl и т.д.
        """
        # Базовая статистика из БД
        total, wins, total_pnl = db.stats()
        losses = total - wins if total > 0 else 0
        
        # Статистика по TP уровням
        tp_stats = db.get_tp_stats()
        
        stats = {
            'total': total,
            'wins': wins,
            'losses': losses,
            'winrate': (wins / total * 100) if total > 0 else 0.0,
            'total_pnl': total_pnl,
            'avg_pnl': (total_pnl / total) if total > 0 else 0.0,
            'tp1_hits': tp_stats['tp1_hits'],
            'tp2_hits': tp_stats['tp2_hits'],
            'tp3_hits': tp_stats['tp3_hits']
        }
        
        # Дополнительные метрики
        if stats['total'] > 0:
            stats['loss_rate'] = 100 - stats['winrate']
            
            # Средний выигрыш (только для прибыльных сделок)
            if wins > 0 and total_pnl > 0:
                stats['avg_win'] = total_pnl / wins
            else:
                stats['avg_win'] = 0.0
            
            # Profit Factor (упрощенный)
            stats['profit_factor'] = abs(stats['avg_pnl']) if stats['avg_pnl'] != 0 else 0.0
        else:
            stats['loss_rate'] = 0.0
            stats['avg_win'] = 0.0
            stats['profit_factor'] = 0.0
        
        return stats
    
    async def get_best_performers(self, limit: int = 5) -> List[Dict]:
        """
        Получает список лучших монет по прибыльности.
        
        Args:
            limit: Максимальное количество монет в списке
            
        Returns:
            Список словарей с данными по каждой монете
        """
        from database import get_connection
        
        with get_connection() as conn:
            cursor = conn.execute("""
                SELECT symbol, 
                       COUNT(*) as total,
                       SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                       SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
                       SUM(pnl) as total_pnl
                FROM trades
                WHERE status = 'CLOSED'
                GROUP BY symbol
                ORDER BY total_pnl DESC
                LIMIT ?
            """, (limit,))
            
            results = []
            for row in cursor.fetchall():
                symbol, total, wins, losses, pnl = row
                results.append({
                    'symbol': symbol,
                    'total': total,
                    'wins': wins or 0,
                    'losses': losses or 0,
                    'pnl': pnl or 0.0
                })
            
            return results
    
    async def format_stats_message(self, days: int = 30) -> str:
        """
        Форматирует статистику для отправки в Telegram.
        
        Args:
            days: Количество дней для анализа
            
        Returns:
            Отформатированное сообщение в Markdown
        """
        stats = await self.get_full_stats(days)
        best = await self.get_best_performers(5)
        
        # Формируем сообщение
        message = f"""
📊 *Статистика за {days} дней*

📈 *Общие показатели:*
├ Всего сигналов: {stats['total']}
├ Выигрышных: {stats['wins']} ✅
├ Проигрышных: {stats['losses']} ❌
├ Winrate: {stats['winrate']:.1f}%
└ Общий PnL: {stats['total_pnl']:+.2f}%

🎯 *Тейк-профиты:*
├ TP1 достигнут: {stats['tp1_hits']} раз
├ TP2 достигнут: {stats['tp2_hits']} раз
└ TP3 достигнут: {stats['tp3_hits']} раз
"""
        
        # Добавляем лучшие монеты
        if best:
            message += "\n🏆 *Лучшие монеты:*\n"
            for i, b in enumerate(best, 1):
                total = b['wins'] + b['losses']
                wr = (b['wins'] / total * 100) if total > 0 else 0
                message += f"├ {i}. {b['symbol']}: {b['pnl']:+.2f}% (WR: {wr:.0f}%)\n"
        
        return message.strip()
