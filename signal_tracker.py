"""
Модуль отслеживания активных сигналов
Проверяет достижение уровней TP и SL,
отправляет уведомления и обновляет статистику
"""

from typing import Dict, List, Optional
import logging

from config import DB_NAME, POSITION_SIZE_A, POSITION_SIZE_B
from data_fetcher import DataFetcher
import database as db

logger = logging.getLogger(__name__)


class SignalTracker:
    """
    Отслеживание активных сигналов и их результатов.
    
    Функции:
    - Проверка достижения SL и TP уровней
    - Предотвращение дублирования уведомлений
    - Корректный расчет PnL с учетом пропорций позиций
    """
    
    def __init__(self, data_fetcher: DataFetcher, notifier):
        """
        Args:
            data_fetcher: Экземпляр для получения текущих цен
            notifier: Объект для отправки уведомлений (TelegramBot)
        """
        self.fetcher = data_fetcher
        self.notifier = notifier
        self.price_cache: Dict[str, float] = {}
    
    async def check_all_signals(self) -> List[Dict]:
        """
        Проверяет все активные сигналы на достижение уровней.
        
        Returns:
            Список словарей с результатами проверки
        """
        # Получаем открытые сделки из БД
        active_signals = db.get_open_trades()
        results = []
        
        if not active_signals:
            logger.debug("Нет активных сигналов для проверки")
            return results
        
        # Обновляем кэш цен для всех символов
        symbols = list(set(s['symbol'] for s in active_signals))
        await self._update_prices(symbols)
        
        # Проверяем каждый сигнал
        for signal in active_signals:
            result = await self._check_signal(signal)
            if result:
                results.append(result)
        
        return results
    
    async def _update_prices(self, symbols: List[str]) -> None:
        """
        Обновляет кэш текущих цен для списка символов.
        
        Args:
            symbols: Список торговых пар
        """
        for symbol in symbols:
            try:
                price = self.fetcher.get_current_price(symbol)
                if price > 0:
                    self.price_cache[symbol] = price
            except Exception as e:
                logger.warning(f"Ошибка получения цены {symbol}: {e}")
    
    def _calculate_weighted_entry(self, entry_a: float, entry_b: Optional[float]) -> float:
        """
        Рассчитывает средневзвешенную цену входа с учетом пропорций позиций.
        
        Формула: (entry_a * 70% + entry_b * 30%) / 100%
        
        Args:
            entry_a: Основная точка входа
            entry_b: Точка усреднения (может быть None)
            
        Returns:
            Средневзвешенная цена входа
        """
        if entry_b is None:
            return entry_a
        
        # Используем веса из конфига
        return (entry_a * POSITION_SIZE_A + entry_b * POSITION_SIZE_B)
    
    def _calculate_pnl(self, entry_avg: float, exit_price: float, is_long: bool) -> float:
        """
        Рассчитывает PnL в процентах.
        
        Args:
            entry_avg: Средневзвешенная цена входа
            exit_price: Цена выхода
            is_long: True для LONG, False для SHORT
            
        Returns:
            PnL в процентах
        """
        if is_long:
            pnl = ((exit_price - entry_avg) / entry_avg) * 100
        else:
            pnl = ((entry_avg - exit_price) / entry_avg) * 100
        return pnl
    
    async def _check_signal(self, signal: Dict) -> Optional[Dict]:
        """
        Проверяет один сигнал на достижение уровней.
        
        Логика:
        1. Проверяем стоп-лосс (закрытие позиции)
        2. Проверяем TP1, TP2 (уведомление, без закрытия)
        3. Проверяем TP3 (закрытие позиции)
        
        Args:
            signal: Словарь с данными сигнала из БД
            
        Returns:
            Словарь с результатом или None
        """
        symbol = signal['symbol']
        current_price = self.price_cache.get(symbol)
        
        if not current_price:
            return None
        
        signal_id = signal['id']
        direction = signal['side']
        entry_a = signal['entry_a']
        entry_b = signal['entry_b']
        stop = signal['stop']
        tp1 = signal['tp1']
        tp2 = signal['tp2']
        tp3 = signal['tp3']
        
        is_long = direction == 'LONG'
        
        # Рассчитываем средневзвешенную цену входа
        entry_avg = self._calculate_weighted_entry(entry_a, entry_b)
        
        # === ПРОВЕРКА СТОП-ЛОССА ===
        stop_hit = (is_long and current_price <= stop) or (not is_long and current_price >= stop)
        
        if stop_hit:
            pnl = self._calculate_pnl(entry_avg, stop, is_long)
            
            # Закрываем сделку в БД
            db.close_trade(signal_id, pnl)
            
            result = {
                'type': 'STOP_LOSS',
                'signal': signal,
                'hit_price': current_price,
                'pnl': pnl
            }
            
            await self.notifier.send_signal_result(result)
            logger.info(f"❌ {symbol} - Стоп-лосс: {pnl:.2f}%")
            return result
        
        # === ПРОВЕРКА ТЕЙК-ПРОФИТОВ ===
        tp_results = []
        
        # TP1 - частичная фиксация, только уведомление
        tp1_hit = (is_long and current_price >= tp1) or (not is_long and current_price <= tp1)
        if tp1_hit and not db.is_tp_hit(signal_id, 1):
            pnl = self._calculate_pnl(entry_avg, tp1, is_long)
            db.mark_tp_hit(signal_id, 1)
            
            result = {
                'type': 'TP1',
                'signal': signal,
                'hit_price': current_price,
                'pnl': pnl
            }
            tp_results.append(result)
            await self.notifier.send_signal_result(result)
            logger.info(f"🎯 {symbol} - TP1 достигнут: +{pnl:.2f}%")
        
        # TP2 - частичная фиксация, только уведомление
        tp2_hit = (is_long and current_price >= tp2) or (not is_long and current_price <= tp2)
        if tp2_hit and not db.is_tp_hit(signal_id, 2):
            pnl = self._calculate_pnl(entry_avg, tp2, is_long)
            db.mark_tp_hit(signal_id, 2)
            
            result = {
                'type': 'TP2',
                'signal': signal,
                'hit_price': current_price,
                'pnl': pnl
            }
            tp_results.append(result)
            await self.notifier.send_signal_result(result)
            logger.info(f"🎯 {symbol} - TP2 достигнут: +{pnl:.2f}%")
        
        # TP3 - полное закрытие позиции
        tp3_hit = (is_long and current_price >= tp3) or (not is_long and current_price <= tp3)
        if tp3_hit and not db.is_tp_hit(signal_id, 3):
            pnl = self._calculate_pnl(entry_avg, tp3, is_long)
            
            db.mark_tp_hit(signal_id, 3)
            db.close_trade(signal_id, pnl)
            
            result = {
                'type': 'TP3_FULL',
                'signal': signal,
                'hit_price': current_price,
                'pnl': pnl
            }
            tp_results.append(result)
            await self.notifier.send_signal_result(result)
            logger.info(f"🏆 {symbol} - TP3 достигнут (закрыто): +{pnl:.2f}%")
        
        return tp_results[0] if tp_results else None
