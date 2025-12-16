import ccxt
import pandas as pd
import numpy as np
import requests
from typing import List, Dict, Optional
import time
from config import TOP_COINS_COUNT, TIMEFRAME, LOOKBACK_PERIODS
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataFetcher:
    def __init__(self):
        self.exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })
        self.coingecko_url = "https://api.coingecko.com/api/v3"

    def get_top_coins_by_marketcap(self, limit: int = TOP_COINS_COUNT) -> List[str]:
        """Получает топ монет по маркет капе"""
        try:
            url = f"{self.coingecko_url}/coins/markets"
            params = {
                'vs_currency': 'usd',
                'order': 'market_cap_desc',
                'per_page': limit * 2,  # Берем больше, т.к. не все есть на Binance
                'page': 1,
                'sparkline': False
            }
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            # Получаем символы
            symbols = [coin['symbol'].upper() + 'USDT' for coin in data]

            # Фильтруем только те, что есть на Binance Futures
            available_markets = self.exchange.load_markets()
            valid_symbols = [s for s in symbols if s in available_markets][:limit]

            # Исключаем стейблкоины
            stablecoins = ['USDTUSDT', 'USDCUSDT', 'BUSDUSDT', 'DAIUSDT', 'TUSDUSDT']
            valid_symbols = [s for s in valid_symbols if s not in stablecoins]

            if not valid_symbols:
                logger.warning("CoinGecko вернул пустой список, используем fallback")
                return self._get_fallback_coins()

            logger.info(f"Найдено {len(valid_symbols)} монет для анализа")
            return valid_symbols

        except Exception as e:
            logger.error(f"Ошибка получения топ монет: {e}")
            return self._get_fallback_coins()

    def _get_fallback_coins(self) -> List[str]:
        """Резервный список монет"""
        return [
            'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT',
            'DOGEUSDT', 'SOLUSDT', 'DOTUSDT', 'MATICUSDT', 'LTCUSDT',
            'AVAXUSDT', 'LINKUSDT', 'ATOMUSDT', 'UNIUSDT', 'ETCUSDT',
            'XLMUSDT', 'APTUSDT', 'NEARUSDT', 'FILUSDT', 'AAVEUSDT'
        ]

    def fetch_ohlcv(self, symbol: str, timeframe: str = TIMEFRAME,
                    limit: int = LOOKBACK_PERIODS) -> Optional[pd.DataFrame]:
        """Получает OHLCV данные для символа"""
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            df['symbol'] = symbol
            return df
        except Exception as e:
            logger.warning(f"Ошибка получения данных для {symbol}: {e}")
            return None

    def fetch_all_coins_data(self) -> Dict[str, pd.DataFrame]:
        """Получает данные для всех топ монет"""
        symbols = self.get_top_coins_by_marketcap()
        all_data = {}

        for i, symbol in enumerate(symbols):
            df = self.fetch_ohlcv(symbol)
            if df is not None and len(df) >= 50:
                all_data[symbol] = df

            # Rate limiting
            if (i + 1) % 10 == 0:
                logger.info(f"Загружено {i + 1}/{len(symbols)} монет")
                time.sleep(1)

        logger.info(f"Успешно загружено данных для {len(all_data)} монет")
        return all_data

    def get_current_price(self, symbol: str) -> float:
        """Получает текущую цену"""
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return ticker['last']
        except:
            return 0.0
