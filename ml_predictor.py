"""
Модуль машинного обучения
Использует Random Forest для предсказания направления движения цены
на основе технических индикаторов
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
import joblib
import os
import logging
from datetime import datetime

from config import ML_MODEL_PATH

logger = logging.getLogger(__name__)


class MLPredictor:
    """
    Класс для ML-предсказаний направления цены.
    Использует Random Forest с автоматическим обучением на исторических данных.
    """
    
    # Список признаков для обучения модели
    FEATURES = [
        'rsi', 'macd', 'macd_histogram', 'adx', 
        'stoch_k', 'bb_pband', 'atr_percent'
    ]
    
    def __init__(self):
        """Инициализация ML модели"""
        self.model = RandomForestClassifier(
            n_estimators=200,  # Количество деревьев
            max_depth=10,  # Максимальная глубина дерева
            random_state=42,  # Для воспроизводимости
            n_jobs=-1  # Использовать все ядра CPU
        )
        self.trained = False
        self.last_train_time: Optional[datetime] = None
        
        # Попытка загрузить сохраненную модель
        self._load_model()
    
    def _load_model(self) -> bool:
        """
        Загружает ранее обученную модель из файла.
        
        Returns:
            True если модель успешно загружена
        """
        if os.path.exists(ML_MODEL_PATH):
            try:
                saved_data = joblib.load(ML_MODEL_PATH)
                self.model = saved_data['model']
                self.last_train_time = saved_data.get('train_time')
                self.trained = True
                logger.info(f"ML модель загружена из {ML_MODEL_PATH}")
                return True
            except Exception as e:
                logger.warning(f"Ошибка загрузки модели: {e}")
        return False
    
    def _save_model(self):
        """Сохраняет обученную модель в файл"""
        try:
            saved_data = {
                'model': self.model,
                'train_time': self.last_train_time
            }
            joblib.dump(saved_data, ML_MODEL_PATH)
            logger.info(f"ML модель сохранена в {ML_MODEL_PATH}")
        except Exception as e:
            logger.error(f"Ошибка сохранения модели: {e}")
    
    def train_on_historical(self, df: pd.DataFrame) -> float:
        """
        Обучает модель на исторических данных.
        
        Целевая переменная: 1 если цена выросла на следующей свече, -1 если упала.
        
        Args:
            df: DataFrame с рассчитанными техническими индикаторами
            
        Returns:
            Точность модели на тестовой выборке
        """
        df = df.copy()
        
        # Создаем целевую переменную
        # 1 = цена вырастет (LONG), -1 = цена упадет (SHORT)
        df['target'] = np.where(df['close'].shift(-1) > df['close'], 1, -1)
        df.dropna(inplace=True)
        
        # Проверяем наличие всех необходимых признаков
        missing_features = [f for f in self.FEATURES if f not in df.columns]
        if missing_features:
            logger.error(f"Отсутствуют признаки: {missing_features}")
            return 0.0
        
        X = df[self.FEATURES]
        y = df['target']
        
        # Проверка на достаточное количество данных
        if len(X) < 50:
            logger.warning(f"Недостаточно данных для обучения: {len(X)} строк")
            return 0.0
        
        # Разделение на train/test
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, shuffle=False  # Не перемешиваем временные ряды
        )
        
        # Обучение модели
        self.model.fit(X_train, y_train)
        self.trained = True
        self.last_train_time = datetime.now()
        
        # Оценка точности
        accuracy = self.model.score(X_test, y_test)
        logger.info(f"ML модель обучена. Accuracy: {accuracy:.2%}")
        
        # Сохраняем модель
        self._save_model()
        
        return accuracy
    
    def predict(self, df: pd.DataFrame) -> Dict:
        """
        Предсказывает направление движения цены.
        
        Args:
            df: DataFrame с рассчитанными индикаторами
            
        Returns:
            Словарь с направлением (1=LONG, -1=SHORT) и уверенностью (0-1)
        """
        # Авто-обучение при первом запуске
        if not self.trained:
            logger.info("ML модель не обучена, запускаем обучение...")
            accuracy = self.train_on_historical(df)
            if accuracy == 0.0:
                # Возвращаем нейтральный результат при ошибке
                return {'direction': 0, 'confidence': 0.0}
        
        # Проверяем наличие признаков
        missing_features = [f for f in self.FEATURES if f not in df.columns]
        if missing_features:
            logger.warning(f"Отсутствуют признаки для предсказания: {missing_features}")
            return {'direction': 0, 'confidence': 0.0}
        
        # Получаем последнюю строку данных
        last_row = df.iloc[-1:][self.FEATURES]
        
        # Проверка на NaN значения
        if last_row.isnull().any().any():
            logger.warning("NaN значения в признаках")
            return {'direction': 0, 'confidence': 0.0}
        
        try:
            # Предсказание вероятностей
            proba = self.model.predict_proba(last_row)[0]
            
            # Определяем направление и уверенность
            # classes_: обычно [-1, 1] после обучения
            classes = self.model.classes_
            
            if len(proba) >= 2:
                # Находим индекс класса 1 (LONG) и -1 (SHORT)
                idx_long = np.where(classes == 1)[0]
                idx_short = np.where(classes == -1)[0]
                
                if len(idx_long) > 0 and len(idx_short) > 0:
                    prob_long = proba[idx_long[0]]
                    prob_short = proba[idx_short[0]]
                else:
                    # Fallback если классы другие
                    prob_long = proba[1] if len(proba) > 1 else 0.5
                    prob_short = proba[0]
                
                direction = 1 if prob_long > prob_short else -1
                confidence = max(prob_long, prob_short)
            else:
                direction = 0
                confidence = 0.0
            
            return {'direction': direction, 'confidence': confidence}
            
        except Exception as e:
            logger.error(f"Ошибка предсказания ML: {e}")
            return {'direction': 0, 'confidence': 0.0}
    
    def get_feature_importance(self) -> Dict[str, float]:
        """
        Возвращает важность признаков модели.
        
        Returns:
            Словарь {название признака: важность}
        """
        if not self.trained:
            return {}
        
        importances = self.model.feature_importances_
        return dict(zip(self.FEATURES, importances))
