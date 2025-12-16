"""
Модуль технического анализа
Рассчитывает множество индикаторов и определяет силу сигналов
на основе комбинации тренда, моментума, волатильности и объема
"""

import pandas as pd
import numpy as np
import ta
from typing import Dict
import logging

logger = logging.getLogger(__name__)


class TechnicalAnalyzer:
    """
    Класс для комплексного технического анализа.
    Добавляет более 30 технических индикаторов и оценивает силу сигналов.
    """
    
    def add_all_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Добавляет все технические индикаторы к DataFrame.
        
        Категории индикаторов:
        - Тренд: SMA, EMA, MACD, ADX, Ichimoku
        - Моментум: RSI, Stochastic, Williams %R, ROC
        - Волатильность: Bollinger Bands, ATR, Keltner, Donchian
        - Объем: OBV, CMF, Volume Ratio
        
        Args:
            df: DataFrame с колонками open, high, low, close, volume
            
        Returns:
            DataFrame с добавленными индикаторами
        """
        df = df.copy()
        
        # === ИНДИКАТОРЫ ТРЕНДА ===
        
        # Скользящие средние
        df['sma_10'] = ta.trend.sma_indicator(df['close'], window=10)
        df['sma_20'] = ta.trend.sma_indicator(df['close'], window=20)
        df['sma_50'] = ta.trend.sma_indicator(df['close'], window=50)
        df['sma_100'] = ta.trend.sma_indicator(df['close'], window=100)
        df['ema_12'] = ta.trend.ema_indicator(df['close'], window=12)
        df['ema_26'] = ta.trend.ema_indicator(df['close'], window=26)
        
        # MACD (Moving Average Convergence Divergence)
        macd = ta.trend.MACD(df['close'])
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        df['macd_histogram'] = macd.macd_diff()
        
        # ADX (Average Directional Index) - сила тренда
        adx = ta.trend.ADXIndicator(df['high'], df['low'], df['close'])
        df['adx'] = adx.adx()
        df['adx_pos'] = adx.adx_pos()  # +DI
        df['adx_neg'] = adx.adx_neg()  # -DI
        
        # Ichimoku Cloud
        ichimoku = ta.trend.IchimokuIndicator(df['high'], df['low'])
        df['ichimoku_a'] = ichimoku.ichimoku_a()
        df['ichimoku_b'] = ichimoku.ichimoku_b()
        df['ichimoku_base'] = ichimoku.ichimoku_base_line()
        df['ichimoku_conv'] = ichimoku.ichimoku_conversion_line()
        
        # === ИНДИКАТОРЫ МОМЕНТУМА ===
        
        # RSI (Relative Strength Index)
        df['rsi'] = ta.momentum.rsi(df['close'], window=14)
        df['rsi_6'] = ta.momentum.rsi(df['close'], window=6)  # Быстрый RSI
        
        # Stochastic Oscillator
        stoch = ta.momentum.StochasticOscillator(df['high'], df['low'], df['close'])
        df['stoch_k'] = stoch.stoch()
        df['stoch_d'] = stoch.stoch_signal()
        
        # Williams %R
        df['williams_r'] = ta.momentum.williams_r(df['high'], df['low'], df['close'])
        
        # ROC (Rate of Change)
        df['roc'] = ta.momentum.roc(df['close'], window=10)
        
        # === ИНДИКАТОРЫ ВОЛАТИЛЬНОСТИ ===
        
        # Bollinger Bands
        bb = ta.volatility.BollingerBands(df['close'])
        df['bb_upper'] = bb.bollinger_hband()
        df['bb_middle'] = bb.bollinger_mavg()
        df['bb_lower'] = bb.bollinger_lband()
        df['bb_width'] = bb.bollinger_wband()  # Ширина канала
        df['bb_pband'] = bb.bollinger_pband()  # Позиция цены в канале (0-1)
        
        # ATR (Average True Range)
        df['atr'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'])
        df['atr_percent'] = (df['atr'] / df['close']) * 100  # ATR в процентах от цены
        
        # Keltner Channel
        kc = ta.volatility.KeltnerChannel(df['high'], df['low'], df['close'])
        df['kc_upper'] = kc.keltner_channel_hband()
        df['kc_middle'] = kc.keltner_channel_mband()
        df['kc_lower'] = kc.keltner_channel_lband()
        
        # Donchian Channel
        dc = ta.volatility.DonchianChannel(df['high'], df['low'], df['close'])
        df['dc_upper'] = dc.donchian_channel_hband()
        df['dc_lower'] = dc.donchian_channel_lband()
        
        # === ИНДИКАТОРЫ ОБЪЕМА ===
        
        # OBV (On-Balance Volume)
        df['obv'] = ta.volume.on_balance_volume(df['close'], df['volume'])
        
        # Volume SMA и соотношение
        df['volume_sma_20'] = ta.trend.sma_indicator(df['volume'], window=20)
        df['volume_ratio'] = df['volume'] / df['volume_sma_20']
        
        # Chaikin Money Flow
        df['cmf'] = ta.volume.chaikin_money_flow(
            df['high'], df['low'], df['close'], df['volume']
        )
        
        # === ДОПОЛНИТЕЛЬНЫЕ ИНДИКАТОРЫ ===
        
        # Parabolic SAR
        psar = ta.trend.PSARIndicator(df['high'], df['low'], df['close'])
        df['psar'] = psar.psar()
        
        # Vortex Indicator
        vortex = ta.trend.VortexIndicator(df['high'], df['low'], df['close'])
        df['vortex_pos'] = vortex.vortex_indicator_pos()
        df['vortex_neg'] = vortex.vortex_indicator_neg()
        
        # Удаляем строки с NaN (начальные периоды без достаточных данных)
        df.dropna(inplace=True)
        
        return df
    
    def get_support_resistance(self, df: pd.DataFrame) -> Dict:
        """
        Рассчитывает динамические уровни поддержки и сопротивления на основе ATR.
        
        Args:
            df: DataFrame с рассчитанными индикаторами
            
        Returns:
            Словарь с уровнями поддержки/сопротивления и ATR
        """
        current_price = df['close'].iloc[-1]
        atr = df['atr'].iloc[-1]
        
        return {
            'resistance_1': current_price + atr * 1.5,
            'resistance_2': current_price + atr * 2.5,
            'resistance_3': current_price + atr * 4,
            'support_1': current_price - atr * 1.5,
            'support_2': current_price - atr * 2.5,
            'support_3': current_price - atr * 4,
            'atr': atr,
            'atr_percent': (atr / current_price) * 100
        }
    
    def get_signal_strength(self, df: pd.DataFrame) -> Dict:
        """
        Анализирует силу бычьих и медвежьих сигналов на основе множества индикаторов.
        
        Система подсчета очков:
        - RSI зоны перекупленности/перепроданности: +2 очка
        - MACD пересечение: +2 очка, направление: +1 очко
        - Расположение MA: +2 очка
        - Bollinger Bands пробой: +2 очка
        - Stochastic в экстремальных зонах: +1 очко
        - Подтверждение объемом: +1 очко
        
        Args:
            df: DataFrame с рассчитанными индикаторами
            
        Returns:
            Словарь с очками бычьих/медвежьих сигналов и уверенностью
        """
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        bullish_signals = 0
        bearish_signals = 0
        
        # === RSI АНАЛИЗ ===
        if last['rsi'] < 30:
            # Перепроданность - сильный бычий сигнал
            bullish_signals += 2
        elif last['rsi'] > 70:
            # Перекупленность - сильный медвежий сигнал
            bearish_signals += 2
        elif last['rsi'] < 45:
            bullish_signals += 1
        elif last['rsi'] > 55:
            bearish_signals += 1
        
        # === MACD АНАЛИЗ ===
        # Пересечение MACD с сигнальной линией
        if last['macd'] > last['macd_signal'] and prev['macd'] <= prev['macd_signal']:
            bullish_signals += 2  # Бычье пересечение
        elif last['macd'] < last['macd_signal'] and prev['macd'] >= prev['macd_signal']:
            bearish_signals += 2  # Медвежье пересечение
        elif last['macd'] > last['macd_signal']:
            bullish_signals += 1
        else:
            bearish_signals += 1
        
        # === СКОЛЬЗЯЩИЕ СРЕДНИЕ ===
        if last['close'] > last['sma_20'] > last['sma_50']:
            bullish_signals += 2  # Бычий тренд
        elif last['close'] < last['sma_20'] < last['sma_50']:
            bearish_signals += 2  # Медвежий тренд
        
        # === BOLLINGER BANDS ===
        if last['close'] < last['bb_lower']:
            bullish_signals += 2  # Цена ниже нижней границы - перепроданность
        elif last['close'] > last['bb_upper']:
            bearish_signals += 2  # Цена выше верхней границы - перекупленность
        
        # === STOCHASTIC ===
        if last['stoch_k'] < 20 and last['stoch_k'] > last['stoch_d']:
            bullish_signals += 1  # Разворот из зоны перепроданности
        elif last['stoch_k'] > 80 and last['stoch_k'] < last['stoch_d']:
            bearish_signals += 1  # Разворот из зоны перекупленности
        
        # === ADX (СИЛА ТРЕНДА) ===
        trend_strength = last['adx'] if not np.isnan(last['adx']) else 20
        
        # === ПОДТВЕРЖДЕНИЕ ОБЪЕМОМ ===
        if last['volume_ratio'] > 1.5:
            # Повышенный объем подтверждает движение
            if last['close'] > last['open']:
                bullish_signals += 1
            else:
                bearish_signals += 1
        
        total_signals = bullish_signals + bearish_signals
        
        return {
            'bullish_score': bullish_signals,
            'bearish_score': bearish_signals,
            'trend_strength': trend_strength,
            'net_score': bullish_signals - bearish_signals,
            'confidence': abs(bullish_signals - bearish_signals) / max(total_signals, 1)
        }
