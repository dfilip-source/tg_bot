
import numpy as np
from sklearn.ensemble import RandomForestClassifier

class MLModel:
    def __init__(self):
        self.model = RandomForestClassifier(n_estimators=100)

    def train(self, X, y):
        self.model.fit(X, y)

    def predict(self, X):
        p = self.model.predict_proba(X)[0]
        return p[1], p[0]
