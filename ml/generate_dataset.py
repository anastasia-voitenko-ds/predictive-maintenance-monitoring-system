"""
Генерация синтетического датасета с реальными корреляциями
между признаками и типами отказов.
"""

import numpy as np
import pandas as pd
from pathlib import Path

RNG = np.random.default_rng(42)
OUT_PATH = Path(__file__).parent.parent / "IoT_Failure_Prediction_Dataset.csv"

N_PER_CLASS = 600  # итого 3000 записей, по 600 на класс (сбалансированный)

FAILURE_LABELS = {
    0: "Норма",
    1: "Сбой батареи",
    2: "Сбой CPU",
    3: "Сетевой сбой",
    4: "Перегрев",
}


def clip(arr, lo, hi):
    return np.clip(arr, lo, hi)


def normal(mean, std, n):
    return RNG.normal(mean, std, n)


def generate_class(cls: int, n: int) -> pd.DataFrame:
    if cls == 0:  # Норма — все метрики в штатных диапазонах
        cpu         = clip(normal(40, 15, n), 0, 75)
        memory      = clip(normal(45, 15, n), 10, 75)
        battery     = clip(normal(72, 15, n), 30, 100)
        latency     = clip(normal(60, 25, n), 1, 150)
        packet_loss = clip(normal(0.5, 0.8, n), 0, 5)
        temperature = clip(normal(42, 8, n), 25, 65)
        uptime      = clip(normal(50, 30, n), 1, 120)
        workload    = RNG.choice([1, 2], n, p=[0.6, 0.4])
        error_count = RNG.integers(0, 4, n)

    elif cls == 1:  # Сбой батареи — низкий заряд, долгий uptime
        cpu         = clip(normal(35, 15, n), 0, 70)
        memory      = clip(normal(45, 15, n), 10, 75)
        battery     = clip(normal(10, 7, n), 0, 25)   # ключевой признак
        latency     = clip(normal(65, 25, n), 1, 160)
        packet_loss = clip(normal(0.8, 1.0, n), 0, 6)
        temperature = clip(normal(44, 8, n), 25, 65)
        uptime      = clip(normal(130, 40, n), 60, 240)  # долго работает
        workload    = RNG.choice([1, 2, 3], n, p=[0.4, 0.4, 0.2])
        error_count = RNG.integers(3, 9, n)

    elif cls == 2:  # Сбой CPU — высокая нагрузка, много ошибок
        cpu         = clip(normal(88, 8, n), 70, 100)  # ключевой признак
        memory      = clip(normal(78, 10, n), 55, 100) # тоже высокая
        battery     = clip(normal(55, 20, n), 15, 100)
        latency     = clip(normal(70, 25, n), 1, 160)
        packet_loss = clip(normal(1.0, 1.2, n), 0, 8)
        temperature = clip(normal(62, 8, n), 45, 85)   # немного повышена
        uptime      = clip(normal(60, 35, n), 1, 150)
        workload    = RNG.choice([2, 3], n, p=[0.25, 0.75])  # высокая нагрузка
        error_count = RNG.integers(7, 15, n)  # ключевой признак

    elif cls == 3:  # Сетевой сбой — высокая задержка и потери пакетов
        cpu         = clip(normal(38, 15, n), 0, 70)
        memory      = clip(normal(45, 15, n), 10, 75)
        battery     = clip(normal(65, 18, n), 20, 100)
        latency     = clip(normal(230, 50, n), 150, 400)  # ключевой признак
        packet_loss = clip(normal(20, 8, n), 10, 50)      # ключевой признак
        temperature = clip(normal(42, 8, n), 25, 65)
        uptime      = clip(normal(55, 35, n), 1, 150)
        workload    = RNG.choice([1, 2], n, p=[0.55, 0.45])
        error_count = RNG.integers(4, 12, n)

    else:  # cls == 4: Перегрев — высокая температура + нагрузка
        cpu         = clip(normal(78, 12, n), 55, 100)   # высокая нагрузка
        memory      = clip(normal(65, 15, n), 35, 100)
        battery     = clip(normal(50, 20, n), 10, 100)
        latency     = clip(normal(70, 25, n), 1, 160)
        packet_loss = clip(normal(0.8, 1.0, n), 0, 6)
        temperature = clip(normal(82, 7, n), 68, 100)    # ключевой признак
        uptime      = clip(normal(80, 40, n), 10, 200)
        workload    = RNG.choice([2, 3], n, p=[0.3, 0.7])
        error_count = RNG.integers(3, 10, n)

    device_id = RNG.integers(1001, 4001, n)

    return pd.DataFrame({
        "Device_ID":            device_id,
        "CPU_Usage (%)":        cpu.round(4),
        "Memory_Usage (%)":     memory.round(4),
        "Battery_Level (%)":    battery.round(4),
        "Network_Latency (ms)": latency.round(4),
        "Packet_Loss (%)":      packet_loss.round(4),
        "Temperature (°C)":     temperature.round(4),
        "Uptime (hrs)":         uptime.round(4),
        "Workload_Intensity":   workload.astype(int),
        "Error_Count":          error_count.astype(int),
        "Failure_Type":         cls,
    })


def generate():
    parts = [generate_class(cls, N_PER_CLASS) for cls in range(5)]
    df = pd.concat(parts, ignore_index=True)
    df = df.sample(frac=1, random_state=42).reset_index(drop=True)

    df.to_csv(OUT_PATH, index=False)
    print(f"Датасет сохранён: {OUT_PATH}")
    print(f"Размер: {len(df)} записей\n")

    print("Распределение классов:")
    for cls, label in FAILURE_LABELS.items():
        n = (df["Failure_Type"] == cls).sum()
        print(f"  {cls} ({label}): {n}")

    print("\nСредние значения по классам (ключевые признаки):")
    cols = ["CPU_Usage (%)", "Battery_Level (%)", "Network_Latency (ms)",
            "Packet_Loss (%)", "Temperature (°C)", "Error_Count"]
    print(df.groupby("Failure_Type")[cols].mean().round(1).to_string())


if __name__ == "__main__":
    generate()
