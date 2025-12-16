"""
Модуль получения рыночных данных
Использует Binance Futures API через ccxt для получения топ монет по объёму
и OHLCV данных
"""

import ccxt
import pandas as pd
from typing import List, Dict, Optional
import time
import logging
from config import TIMEFRAME, LOOKBACK_PERIODS

logger = logging.getLogger(__name__)


class DataFetcher:
    """
    Класс для получения рыночных данных с Binance Futures.
    Определяет топ монет по объёму торгов и получает OHLCV.
    """

    def __init__(self):
        """Инициализация подключения к Binance Futures через ccxt"""
        self.exchange = ccxt.binance({
            'enableRateLimit': True,  # Автоматический rate limiting
            'options': {'defaultType': 'future'}  # Используем фьючерсы
        })
        self._markets_cache = None
        self._markets_cache_time = 0
        self._cache_ttl = 3600  # Время жизни кэша - 1 час

    def _load_markets(self) -> Dict:
        """Загружает и кэширует список доступных рынков"""
        current_time = time.time()
        if self._markets_cache is None or (current_time - self._markets_cache_time) > self._cache_ttl:
            self._markets_cache = self.exchange.load_markets()
            self._markets_cache_time = current_time
            logger.debug("Обновлен кэш рынков Binance Futures")
        return self._markets_cache

    def get_top_coins_by_volume(self, limit: int = 20) -> List[str]:
        """
        Получает топ монет по 24h объёму торгов на Binance Futures.
        
        Args:
            limit: Максимальное количество монет для возврата
            
        Returns:
            Список символов торговых пар (например, ['BTC/USDT:USDT', 'ETH/USDT:USDT', ...])
        """
        try:
            markets = self._load_markets()
            usdt_markets = {
                symbol: markets[symbol]['quoteVolume'] 
                for symbol in markets 
                if symbol.endswith('USDT:USDT') and markets[symbol]['active']
            }
            # Сортируем по объёму
            sorted_symbols = sorted(usdt_markets, key=lambda x: usdt_markets[x], reverse=True)
            top_symbols = sorted_symbols[:limit]
            
            if not top_symbols:
                logger.warning("Не удалось получить топ монет, используем fallback")
                return self._get_fallback_coins()
            
            logger.info(f"Найдено {len(top_symbols)} монет для анализа")
            return top_symbols

        except Exception as e:
            logger.error(f"Ошибка получения топ монет: {e}")
            return self._get_fallback_coins()

    def _get_fallback_coins(self) -> List[str]:
        """
        Резервный список популярных монет на случай ошибок
        Returns:
            Список из 20 наиболее ликвидных торговых пар
        """
        return [
            'BTC/USDT:USDT', 'ETH/USDT:USDT', 'BNB/USDT:USDT', 'XRP/USDT:USDT', 'ADA/USDT:USDT',
            'DOGE/USDT:USDT', 'SOL/USDT:USDT', 'DOT/USDT:USDT', 'MATIC/USDT:USDT', 'LTC/USDT:USDT',
            'AVAX/USDT:USDT', 'LINK/USDT:USDT', 'ATOM/USDT:USDT', 'UNI/USDT:USDT', 'ETC/USDT:USDT',
            'XLM/USDT:USDT', 'APT/USDT:USDT', 'NEAR/USDT:USDT', 'FIL/USDT:USDT', 'AAVE/USDT:USDT'
        ]

    def fetch_ohlcv(self, symbol: str, timeframe: str = TIMEFRAME,
                    limit: int = LOOKBACK_PERIODS) -> Optional[pd.DataFrame]:
        """
        Получает OHLCV (Open, High, Low, Close, Volume) данные для символа.
        """
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(
                ohlcv,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            df['symbol'] = symbol
            return df

        except ccxt.RateLimitExceeded:
            logger.warning(f"Rate limit для {symbol}, ожидание...")
            time.sleep(5)
            return self.fetch_ohlcv(symbol, timeframe, limit)
        except Exception as e:
            logger.warning(f"Ошибка получения данных для {symbol}: {e}")
            return None

    def fetch_all_coins_data(self) -> Dict[str, pd.DataFrame]:
        """
        Получает OHLCV данные для всех топ монет.
        """
        symbols = self.get_top_coins_by_volume()
        all_data = {}

        for i, symbol in enumerate(symbols):
            df = self.fetch_ohlcv(symbol)
            if df is not None and len(df) >= 50:
                all_data[symbol] = df
            if (i + 1) % 10 == 0:
                logger.info(f"Загружено {i + 1}/{len(symbols)} монет")
                time.sleep(1)

        logger.info(f"Успешно загружено данных для {len(all_data)} монет")
        return all_data

    def get_current_price(self, symbol: str) -> float:
        """
        Получает текущую цену для символа.
        """
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return float(ticker['last'])
        except Exception as e:
            logger.warning(f"Ошибка получения цены {symbol}: {e}")
            return 0.0
