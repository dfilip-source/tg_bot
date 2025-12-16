"""
Модуль работы с базой данных SQLite
Управляет таблицами trades для хранения сигналов и их результатов
"""

import sqlite3
from contextlib import contextmanager
from typing import Optional, Tuple, List, Dict
from config import DB_NAME
import logging

logger = logging.getLogger(__name__)


@contextmanager
def get_connection():
    """
    Контекстный менеджер для безопасной работы с соединением БД.
    Автоматически закрывает соединение при выходе из контекста.
    """
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row  # Позволяет обращаться к колонкам по имени
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Ошибка БД: {e}")
        raise
    finally:
        conn.close()


def init_db():
    """
    Инициализирует базу данных, создает необходимые таблицы.
    Добавлены поля tp1_hit, tp2_hit для отслеживания достигнутых TP уровней.
    """
    with get_connection() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            entry_a REAL NOT NULL,
            entry_b REAL,
            stop REAL NOT NULL,
            tp1 REAL NOT NULL,
            tp2 REAL NOT NULL,
            tp3 REAL NOT NULL,
            status TEXT DEFAULT 'OPEN',
            pnl REAL,
            tp1_hit INTEGER DEFAULT 0,
            tp2_hit INTEGER DEFAULT 0,
            tp3_hit INTEGER DEFAULT 0,
            opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            closed_at TIMESTAMP
        )
        """)
        logger.info("База данных инициализирована")


def open_trade(symbol: str, side: str, entry_a: float, entry_b: Optional[float],
               stop: float, tp1: float, tp2: float, tp3: float) -> int:
    """
    Открывает новую сделку в базе данных.
    
    Args:
        symbol: Торговая пара (например, BTCUSDT)
        side: Направление (LONG или SHORT)
        entry_a: Основная точка входа (70% позиции)
        entry_b: Точка усреднения (30% позиции), может быть None
        stop: Уровень стоп-лосса
        tp1, tp2, tp3: Уровни тейк-профитов
        
    Returns:
        ID созданной записи
    """
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO trades 
               (symbol, side, entry_a, entry_b, stop, tp1, tp2, tp3, status) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'OPEN')""",
            (symbol, side, entry_a, entry_b, stop, tp1, tp2, tp3)
        )
        trade_id = cursor.lastrowid
        logger.info(f"Открыта сделка #{trade_id}: {symbol} {side}")
        return trade_id


def close_trade(trade_id: int, pnl: float):
    """
    Закрывает сделку с указанным PnL.
    
    Args:
        trade_id: ID сделки
        pnl: Процент прибыли/убытка
    """
    with get_connection() as conn:
        conn.execute(
            """UPDATE trades 
               SET status='CLOSED', pnl=?, closed_at=CURRENT_TIMESTAMP 
               WHERE id=?""",
            (pnl, trade_id)
        )
        logger.info(f"Закрыта сделка #{trade_id} с PnL: {pnl:.2f}%")


def mark_tp_hit(trade_id: int, tp_level: int):
    """
    Помечает достижение определенного TP уровня.
    Предотвращает повторные уведомления.
    
    Args:
        trade_id: ID сделки
        tp_level: Номер TP (1, 2 или 3)
    """
    if tp_level not in [1, 2, 3]:
        return
    
    column = f"tp{tp_level}_hit"
    with get_connection() as conn:
        conn.execute(
            f"UPDATE trades SET {column} = 1 WHERE id = ?",
            (trade_id,)
        )
        logger.info(f"Сделка #{trade_id}: TP{tp_level} достигнут")


def get_open_trades() -> List[Dict]:
    """
    Получает все открытые сделки.
    
    Returns:
        Список словарей с данными сделок
    """
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM trades WHERE status = 'OPEN'")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def is_tp_hit(trade_id: int, tp_level: int) -> bool:
    """
    Проверяет, был ли уже достигнут указанный TP уровень.
    
    Args:
        trade_id: ID сделки
        tp_level: Номер TP (1, 2 или 3)
        
    Returns:
        True если TP уже был достигнут
    """
    if tp_level not in [1, 2, 3]:
        return False
    
    column = f"tp{tp_level}_hit"
    with get_connection() as conn:
        cursor = conn.execute(
            f"SELECT {column} FROM trades WHERE id = ?",
            (trade_id,)
        )
        row = cursor.fetchone()
        return bool(row[0]) if row else False


def stats() -> Tuple[int, int, float]:
    """
    Получает базовую статистику по закрытым сделкам.
    
    Returns:
        Кортеж (всего сделок, выигрышных, общий PnL)
    """
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT 
                COUNT(*),
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END),
                SUM(pnl)
            FROM trades
            WHERE status = 'CLOSED'
        """)
        total, wins, pnl = cursor.fetchone()
        return total or 0, wins or 0, pnl or 0.0


def get_tp_stats() -> Dict[str, int]:
    """
    Получает статистику по достижению TP уровней.
    
    Returns:
        Словарь с количеством достигнутых TP1, TP2, TP3
    """
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT 
                SUM(tp1_hit) as tp1_count,
                SUM(tp2_hit) as tp2_count,
                SUM(tp3_hit) as tp3_count
            FROM trades
        """)
        row = cursor.fetchone()
        return {
            'tp1_hits': row[0] or 0,
            'tp2_hits': row[1] or 0,
            'tp3_hits': row[2] or 0
        }
