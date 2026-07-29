"""
Обучение модели XGBoost для предсказания типа отказа ПК.
Датасет: IoT_Failure_Prediction_Dataset.csv

Примечание: датасет синтетический — распределения признаков практически
идентичны по всем классам отказов, что ограничивает достижимую точность ~58%.
Система использует predict_proba для отображения вероятностей по каждому классу.
"""

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from imblearn.over_sampling import SMOTE
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import cross_val_score, train_test_split
from xgboost import XGBClassifier

FAILURE_LABELS = {
    0: "Норма",
    1: "Сбой батареи",
    2: "Сбой CPU",
    3: "Сетевой сбой",
    4: "Перегрев",
}

FEATURE_COLS = [
    "CPU_Usage (%)",
    "Memory_Usage (%)",
    "Battery_Level (%)",
    "Network_Latency (ms)",
    "Packet_Loss (%)",
    "Temperature (°C)",
    "Uptime (hrs)",
    "Workload_Intensity",
    "Error_Count",
]

DATA_PATH = Path(__file__).parent.parent / "IoT_Failure_Prediction_Dataset.csv"
MODEL_PATH = Path(__file__).parent / "model.pkl"
META_PATH = Path(__file__).parent / "model_meta.json"


def load_data():
    df = pd.read_csv(DATA_PATH)
    X = df[FEATURE_COLS].values
    y = df["Failure_Type"].values
    return X, y


def train():
    print("Загрузка данных...")
    X, y = load_data()
    print(f"Размер датасета: {X.shape[0]} записей, {X.shape[1]} признаков")

    class_counts = np.bincount(y)
    print("Распределение классов (до балансировки):")
    for cls, count in enumerate(class_counts):
        print(f"  {cls} ({FAILURE_LABELS[cls]}): {count}")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    print("\nПрименение SMOTE для балансировки обучающей выборки...")
    smote = SMOTE(random_state=42)
    X_train_bal, y_train_bal = smote.fit_resample(X_train, y_train)
    bal_counts = np.bincount(y_train_bal)
    print("Распределение классов (после SMOTE):")
    for cls, count in enumerate(bal_counts):
        print(f"  {cls} ({FAILURE_LABELS[cls]}): {count}")

    print("\nОбучение XGBoost...")
    model = XGBClassifier(
        n_estimators=500,
        max_depth=7,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=3,
        gamma=0.1,
        reg_alpha=0.1,
        reg_lambda=1.0,
        eval_metric="mlogloss",
        random_state=42,
        n_jobs=1,
    )
    model.fit(X_train_bal, y_train_bal, verbose=False)

    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    macro_f1 = f1_score(y_test, y_pred, average="macro")

    print(f"\nТочность на тесте:  {acc:.4f} ({acc*100:.2f}%)")
    print(f"Macro F1-score:      {macro_f1:.4f}")

    n_classes = len(FAILURE_LABELS)
    target_names = [FAILURE_LABELS[i] for i in range(n_classes)]
    print("\nОтчёт по классам:")
    print(classification_report(y_test, y_pred, target_names=target_names))

    print("Кросс-валидация (5 fold)...")
    cv_acc = cross_val_score(model, X, y, cv=5, scoring="accuracy", n_jobs=1)
    print(f"CV Accuracy: {cv_acc.mean():.4f} ± {cv_acc.std():.4f}")

    importances = model.feature_importances_
    print("\nВажность признаков:")
    for feat, imp in sorted(zip(FEATURE_COLS, importances), key=lambda x: -x[1]):
        print(f"  {feat}: {imp:.4f}")

    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)
    print(f"\nМодель сохранена: {MODEL_PATH}")

    meta = {
        "feature_cols": FEATURE_COLS,
        "failure_labels": {str(k): v for k, v in FAILURE_LABELS.items()},
        "accuracy": float(acc),
        "macro_f1": float(macro_f1),
        "cv_accuracy_mean": float(cv_acc.mean()),
        "cv_accuracy_std": float(cv_acc.std()),
        "n_classes": n_classes,
        "feature_importances": dict(zip(FEATURE_COLS, importances.tolist())),
    }
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"Метаданные сохранены: {META_PATH}")


if __name__ == "__main__":
    train()
