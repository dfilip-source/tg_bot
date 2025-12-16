"""
Модуль генерации торговых сигналов
Комбинирует технический анализ и ML предсказания
для формирования высококачественных сигналов
"""

from dataclasses import dataclass
from typing import Optional
import pandas as pd
import logging

from technical_analysis import TechnicalAnalyzer
from ml_predictor import MLPredictor
from config import (
    ENABLE_AVERAGING, AVERAGING_DISTANCE,
    ATR_MULTIPLIER_SL, ATR_MULTIPLIER_TP1, ATR_MULTIPLIER_TP2, ATR_MULTIPLIER_TP3,
    MIN_CONFIDENCE, MIN_ADX, POSITION_SIZE_A, POSITION_SIZE_B
)

logger = logging.getLogger(__name__)


@dataclass
class Signal:
    """
    Структура торгового сигнала.
    
    Attributes:
        symbol: Торговая пара (например, BTCUSDT)
        side: Направление сделки (LONG или SHORT)
        entry_a: Основная точка входа (70% позиции)
        entry_b: Точка усреднения (30% позиции), опционально
        stop: Уровень стоп-лосса
        tp1, tp2, tp3: Три уровня тейк-профита
        confidence: Уверенность в сигнале (0-1)
    """
    symbol: str
    side: str
    entry_a: float
    entry_b: Optional[float] = None
    stop: float = 0.0
    tp1: float = 0.0
    tp2: float = 0.0
    tp3: float = 0.0
    confidence: float = 0.0


class SignalGenerator:
    """
    Генератор торговых сигналов.
    
    Логика генерации:
    1. Расчет технических индикаторов
    2. Оценка силы сигнала через TA
    3. Получение ML предсказания
    4. Проверка согласованности TA и ML
    5. Расчет уровней входа, SL и TP на основе ATR
    """
    
    def __init__(self, ta: TechnicalAnalyzer, ml: MLPredictor):
        """
        Args:
            ta: Экземпляр технического анализатора
            ml: Экземпляр ML предсказателя
        """
        self.ta = ta
        self.ml = ml
    
    def generate(self, df: pd.DataFrame, symbol: str) -> Optional[Signal]:
        """
        Генерирует торговый сигнал для указанного символа.
        
        Условия генерации сигнала:
        1. Комбинированная уверенность (TA + ML) >= MIN_CONFIDENCE
        2. ADX >= MIN_ADX (подтверждение наличия тренда)
        3. Согласованность направления TA и ML
        
        Args:
            df: DataFrame с OHLCV данными
            symbol: Торговая пара
            
        Returns:
            Signal если условия выполнены, иначе None
        """
        try:
            # Шаг 1: Добавляем все технические индикаторы
            df = self.ta.add_all_indicators(df)
            
            if len(df) < 10:
                logger.debug(f"{symbol}: недостаточно данных после расчета индикаторов")
                return None
            
            # Шаг 2: Получаем силу сигнала из технического анализа
            strength = self.ta.get_signal_strength(df)
            
            # Шаг 3: Получаем ML предсказание
            ml_pred = self.ml.predict(df)
            
            # Шаг 4: Проверяем комбинированную уверенность
            # Среднее значение уверенности от TA и ML
            combined_conf = (strength['confidence'] + ml_pred['confidence']) / 2
            
            if combined_conf < MIN_CONFIDENCE:
                logger.debug(f"{symbol}: низкая уверенность {combined_conf:.2f} < {MIN_CONFIDENCE}")
                return None
            
            # Шаг 5: Проверяем силу тренда через ADX
            current_adx = df['adx'].iloc[-1]
            if current_adx < MIN_ADX:
                logger.debug(f"{symbol}: слабый тренд ADX={current_adx:.1f} < {MIN_ADX}")
                return None
            
            # Шаг 6: Проверяем согласованность TA и ML
            direction = ml_pred['direction']
            net_score = strength['net_score']
            
            # ML говорит LONG, но TA медвежий (или наоборот) - пропускаем
            if (direction == 1 and net_score <= 0) or (direction == -1 and net_score >= 0):
                logger.debug(f"{symbol}: несогласованность TA ({net_score}) и ML ({direction})")
                return None
            
            # Шаг 7: Определяем направление и рассчитываем уровни
            side = "LONG" if direction == 1 else "SHORT"
            price = df['close'].iloc[-1]
            atr = df['atr'].iloc[-1]
            
            # Расчет дистанций на основе ATR
            sl_dist = atr * ATR_MULTIPLIER_SL
            tp1_dist = atr * ATR_MULTIPLIER_TP1
            tp2_dist = atr * ATR_MULTIPLIER_TP2
            tp3_dist = atr * ATR_MULTIPLIER_TP3
            
            if side == "LONG":
                entry_a = price
                # Усреднение ниже текущей цены для LONG
                entry_b = price * (1 - AVERAGING_DISTANCE) if ENABLE_AVERAGING else None
                stop = price - sl_dist
                tp1 = price + tp1_dist
                tp2 = price + tp2_dist
                tp3 = price + tp3_dist
            else:  # SHORT
                entry_a = price
                # Усреднение выше текущей цены для SHORT
                entry_b = price * (1 + AVERAGING_DISTANCE) if ENABLE_AVERAGING else None
                stop = price + sl_dist
                tp1 = price - tp1_dist
                tp2 = price - tp2_dist
                tp3 = price - tp3_dist
            
            signal = Signal(
                symbol=symbol,
                side=side,
                entry_a=entry_a,
                entry_b=entry_b,
                stop=stop,
                tp1=tp1,
                tp2=tp2,
                tp3=tp3,
                confidence=combined_conf
            )
            
            logger.info(
                f"Сигнал: {symbol} {side} | Уверенность: {combined_conf:.2%} | "
                f"Entry: {entry_a:.4f} | SL: {stop:.4f} | TP1: {tp1:.4f}"
            )
            
            return signal
            
        except Exception as e:
            logger.error(f"Ошибка генерации сигнала для {symbol}: {e}")
            return None
