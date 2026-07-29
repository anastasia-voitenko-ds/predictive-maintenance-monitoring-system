"""
FastAPI backend: аутентификация (JWT), телеметрия, предсказания XGBoost, MongoDB.
"""

import json
import pickle
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import numpy as np
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr

# ── Конфигурация ──────────────────────────────────────────────────────────────

MONGO_URL   = "mongodb://localhost:27017"
DB_NAME     = "pc_monitor"
COL_TEL     = "telemetry_logs"
COL_USERS   = "users"

SECRET_KEY  = "pc-monitor-secret-key-change-in-production"
ALGORITHM   = "HS256"
TOKEN_DAYS  = 7

MODEL_PATH  = Path(__file__).parent.parent / "ml" / "model.pkl"
META_PATH   = Path(__file__).parent.parent / "ml" / "model_meta.json"

FAILURE_LABELS = {0: "Норма", 1: "Сбой батареи", 2: "Сбой CPU", 3: "Сетевой сбой", 4: "Перегрев"}

FEATURE_COLS = [
    "cpu_usage", "memory_usage", "battery_level", "network_latency",
    "packet_loss", "temperature", "uptime_hrs", "workload_intensity", "error_count",
]

# ── Безопасность ──────────────────────────────────────────────────────────────

pwd_ctx    = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer     = HTTPBearer(auto_error=False)

def hash_password(plain: str) -> str:
    return pwd_ctx.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)

def create_token(user_id: str, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=TOKEN_DAYS)
    return jwt.encode({"sub": user_id, "email": email, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Недействительный токен")

# ── Модель ────────────────────────────────────────────────────────────────────

model      = None
model_meta = {}

def load_model():
    global model, model_meta
    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)
    with open(META_PATH, "r", encoding="utf-8") as f:
        model_meta = json.load(f)
    print(f"Модель загружена. Accuracy: {model_meta.get('accuracy', 0):.4f}")

# ── FastAPI ───────────────────────────────────────────────────────────────────

app = FastAPI(title="PC Monitor API", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

mongo_client: AsyncIOMotorClient = None
db = None

@app.on_event("startup")
async def startup():
    global mongo_client, db
    load_model()
    mongo_client = AsyncIOMotorClient(MONGO_URL)
    db = mongo_client[DB_NAME]
    await db[COL_TEL].create_index("timestamp")
    await db[COL_TEL].create_index("user_id")
    await db[COL_USERS].create_index("email", unique=True)
    print("MongoDB подключена.")

@app.on_event("shutdown")
async def shutdown():
    mongo_client.close()

# ── Dependency: текущий пользователь ─────────────────────────────────────────

async def get_current_user(creds: HTTPAuthorizationCredentials = Depends(bearer)):
    if not creds:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется авторизация")
    payload = decode_token(creds.credentials)
    user_id = payload.get("sub")
    user = await db[COL_USERS].find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не найден")
    return user

async def get_admin_user(current_user=Depends(get_current_user)):
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Доступ запрещён")
    return current_user

# ── Схемы ─────────────────────────────────────────────────────────────────────

class RegisterIn(BaseModel):
    name: str
    email: EmailStr
    password: str

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    password: Optional[str] = None

class SystemError(BaseModel):
    timestamp: str
    severity: str
    process: str
    message: str

class TelemetryIn(BaseModel):
    cpu_usage: float
    memory_usage: float
    battery_level: float
    network_latency: float
    packet_loss: float
    temperature: float
    uptime_hrs: float
    workload_intensity: int
    error_count: int
    total_error_count: Optional[int] = None
    system_errors: Optional[list[SystemError]] = []
    device_name: Optional[str] = "PC"

# ── Auth эндпоинты ────────────────────────────────────────────────────────────

@app.post("/api/auth/register")
async def register(data: RegisterIn):
    existing = await db[COL_USERS].find_one({"email": data.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email уже зарегистрирован")

    import uuid
    # Первый зарегистрированный пользователь становится администратором
    is_first = await db[COL_USERS].count_documents({}) == 0
    user_id = str(uuid.uuid4())
    user_doc = {
        "_id":             user_id,
        "email":           data.email,
        "name":            data.name,
        "hashed_password": hash_password(data.password),
        "created_at":      datetime.now(timezone.utc).isoformat(),
        "is_admin":        is_first,
    }
    await db[COL_USERS].insert_one(user_doc)
    token = create_token(user_id, data.email)
    return {"token": token, "user": {
        "id": user_id, "email": data.email,
        "name": data.name, "is_admin": is_first,
    }}

@app.post("/api/auth/login")
async def login(data: LoginIn):
    user = await db[COL_USERS].find_one({"email": data.email})
    if not user or not verify_password(data.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    token = create_token(user["_id"], user["email"])
    return {"token": token, "user": {
        "id": user["_id"], "email": user["email"],
        "name": user["name"], "is_admin": user.get("is_admin", False),
    }}

@app.get("/api/auth/me")
async def me(current_user=Depends(get_current_user)):
    return {
        "id":         current_user["_id"],
        "email":      current_user["email"],
        "name":       current_user["name"],
        "created_at": current_user.get("created_at", ""),
        "is_admin":   current_user.get("is_admin", False),
    }

@app.put("/api/auth/profile")
async def update_profile(data: ProfileUpdate, current_user=Depends(get_current_user)):
    update: dict = {}
    if data.name and data.name.strip():
        update["name"] = data.name.strip()
    if data.password:
        update["hashed_password"] = hash_password(data.password)
    if update:
        await db[COL_USERS].update_one({"_id": current_user["_id"]}, {"$set": update})
    user = await db[COL_USERS].find_one({"_id": current_user["_id"]})
    return {
        "id":         user["_id"],
        "email":      user["email"],
        "name":       user["name"],
        "created_at": user.get("created_at", ""),
    }

# ── Телеметрия ────────────────────────────────────────────────────────────────

@app.post("/api/telemetry")
async def receive_telemetry(data: TelemetryIn, current_user=Depends(get_current_user)):
    features = np.array([[
        data.cpu_usage, data.memory_usage, data.battery_level,
        data.network_latency, data.packet_loss, data.temperature,
        data.uptime_hrs, data.workload_intensity, data.error_count,
    ]])

    failure_type = int(model.predict(features)[0])
    proba        = model.predict_proba(features)[0].tolist()
    risk_score   = round((1 - proba[0]) * 100, 2)
    probabilities = {FAILURE_LABELS[i]: round(p * 100, 2) for i, p in enumerate(proba)}

    errors_list = [e.model_dump() for e in (data.system_errors or [])]

    doc = {
        "timestamp":    datetime.now(timezone.utc).isoformat(),
        "user_id":      current_user["_id"],
        "device_name":  data.device_name,
        "telemetry":    data.model_dump(exclude={"device_name", "system_errors"}),
        "system_errors": errors_list,
        "prediction": {
            "failure_type":  failure_type,
            "failure_label": FAILURE_LABELS[failure_type],
            "probabilities": probabilities,
            "risk_score":    risk_score,
        },
    }
    result = await db[COL_TEL].insert_one(doc)
    doc["_id"] = str(result.inserted_id)

    return {
        "id":            doc["_id"],
        "failure_type":  failure_type,
        "failure_label": FAILURE_LABELS[failure_type],
        "probabilities": probabilities,
        "risk_score":    risk_score,
    }

@app.get("/api/history")
async def get_history(
    limit: int = Query(50, ge=1, le=500),
    skip:  int = Query(0, ge=0),
    failure_type: Optional[int] = Query(None),
    current_user=Depends(get_current_user),
):
    query = {"user_id": current_user["_id"]}
    if failure_type is not None:
        query["prediction.failure_type"] = failure_type

    cursor = (
        db[COL_TEL]
        .find(query, {"_id": 1, "timestamp": 1, "device_name": 1, "telemetry": 1, "prediction": 1})
        .sort("timestamp", -1).skip(skip).limit(limit)
    )
    docs = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        docs.append(doc)
    total = await db[COL_TEL].count_documents(query)
    return {"total": total, "items": docs}

@app.get("/api/stats")
async def get_stats(current_user=Depends(get_current_user)):
    uid = current_user["_id"]
    total = await db[COL_TEL].count_documents({"user_id": uid})
    if total == 0:
        return {"total": 0, "failure_distribution": {}, "avg_metrics": {}, "risk_trend": []}

    pipeline_dist = [
        {"$match": {"user_id": uid}},
        {"$group": {"_id": "$prediction.failure_type", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    dist_raw     = await db[COL_TEL].aggregate(pipeline_dist).to_list(None)
    distribution = {FAILURE_LABELS[d["_id"]]: d["count"] for d in dist_raw}

    pipeline_avg = [
        {"$match": {"user_id": uid}},
        {"$group": {"_id": None,
            "avg_cpu":   {"$avg": "$telemetry.cpu_usage"},
            "avg_memory":{"$avg": "$telemetry.memory_usage"},
            "avg_temp":  {"$avg": "$telemetry.temperature"},
            "avg_risk":  {"$avg": "$prediction.risk_score"},
        }},
    ]
    avg_raw     = await db[COL_TEL].aggregate(pipeline_avg).to_list(None)
    avg_metrics = {}
    if avg_raw:
        r = avg_raw[0]
        avg_metrics = {
            "cpu_usage":    round(r["avg_cpu"], 1),
            "memory_usage": round(r["avg_memory"], 1),
            "temperature":  round(r["avg_temp"], 1),
            "risk_score":   round(r["avg_risk"], 1),
        }

    trend_cursor = (
        db[COL_TEL]
        .find({"user_id": uid}, {"timestamp": 1, "prediction.risk_score": 1})
        .sort("timestamp", -1).limit(20)
    )
    trend = []
    async for doc in trend_cursor:
        trend.append({"timestamp": doc["timestamp"], "risk_score": doc["prediction"]["risk_score"]})
    trend.reverse()

    return {"total": total, "failure_distribution": distribution, "avg_metrics": avg_metrics, "risk_trend": trend}

@app.get("/api/errors")
async def get_errors(
    limit: int = Query(100, ge=1, le=1000),
    severity: Optional[str] = Query(None),
    current_user=Depends(get_current_user),
):
    pipeline = [
        {"$match": {"user_id": current_user["_id"]}},
        {"$unwind": "$system_errors"},
        {"$replaceRoot": {"newRoot": {"$mergeObjects": [
            "$system_errors",
            {"device_name": "$device_name", "telemetry_ts": "$timestamp"},
        ]}}},
    ]
    if severity:
        pipeline.append({"$match": {"severity": severity}})
    pipeline += [{"$sort": {"telemetry_ts": -1}}, {"$limit": limit}]

    docs = await db[COL_TEL].aggregate(pipeline).to_list(None)
    return {"total": len(docs), "items": docs}

@app.get("/api/model-info")
async def get_model_info(current_user=Depends(get_current_user)):
    return model_meta

@app.get("/api/health")
async def health():
    return {"status": "ok", "model_loaded": model is not None}

# ── Admin эндпоинты ───────────────────────────────────────────────────────────

def _user_out(u: dict, tel_count: int = 0, last_active: str = "") -> dict:
    return {
        "id":          u["_id"],
        "name":        u["name"],
        "email":       u["email"],
        "is_admin":    u.get("is_admin", False),
        "created_at":  u.get("created_at", ""),
        "tel_count":   tel_count,
        "last_active": last_active,
    }

@app.get("/api/admin/users")
async def admin_list_users(_=Depends(get_admin_user)):
    users = await db[COL_USERS].find({}, {"hashed_password": 0}).to_list(None)

    # Считаем кол-во телеметрий и последнюю активность для каждого пользователя
    pipeline = [
        {"$group": {
            "_id":         "$user_id",
            "count":       {"$sum": 1},
            "last_active": {"$max": "$timestamp"},
        }},
    ]
    agg = {r["_id"]: r async for r in db[COL_TEL].aggregate(pipeline)}

    result = []
    for u in users:
        uid  = u["_id"]
        stat = agg.get(uid, {})
        result.append(_user_out(u, stat.get("count", 0), stat.get("last_active", "")))

    result.sort(key=lambda x: x["created_at"], reverse=True)
    return {"total": len(result), "users": result}

@app.get("/api/admin/users/{uid}/history")
async def admin_user_history(
    uid: str,
    limit: int = Query(50, ge=1, le=500),
    skip:  int = Query(0, ge=0),
    _=Depends(get_admin_user),
):
    cursor = (
        db[COL_TEL]
        .find({"user_id": uid}, {"_id": 1, "timestamp": 1, "device_name": 1, "telemetry": 1, "prediction": 1})
        .sort("timestamp", -1).skip(skip).limit(limit)
    )
    docs = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        docs.append(doc)
    total = await db[COL_TEL].count_documents({"user_id": uid})
    return {"total": total, "items": docs}

@app.get("/api/admin/users/{uid}/stats")
async def admin_user_stats(uid: str, _=Depends(get_admin_user)):
    total = await db[COL_TEL].count_documents({"user_id": uid})
    if total == 0:
        return {"total": 0, "failure_distribution": {}, "avg_metrics": {}, "risk_trend": []}

    dist_raw = await db[COL_TEL].aggregate([
        {"$match": {"user_id": uid}},
        {"$group": {"_id": "$prediction.failure_type", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]).to_list(None)
    distribution = {FAILURE_LABELS[d["_id"]]: d["count"] for d in dist_raw}

    avg_raw = await db[COL_TEL].aggregate([
        {"$match": {"user_id": uid}},
        {"$group": {"_id": None,
            "avg_cpu":    {"$avg": "$telemetry.cpu_usage"},
            "avg_memory": {"$avg": "$telemetry.memory_usage"},
            "avg_temp":   {"$avg": "$telemetry.temperature"},
            "avg_risk":   {"$avg": "$prediction.risk_score"},
        }},
    ]).to_list(None)
    avg_metrics = {}
    if avg_raw:
        r = avg_raw[0]
        avg_metrics = {
            "cpu_usage":    round(r["avg_cpu"], 1),
            "memory_usage": round(r["avg_memory"], 1),
            "temperature":  round(r["avg_temp"], 1),
            "risk_score":   round(r["avg_risk"], 1),
        }

    trend = []
    async for doc in (
        db[COL_TEL]
        .find({"user_id": uid}, {"timestamp": 1, "prediction.risk_score": 1})
        .sort("timestamp", -1).limit(20)
    ):
        trend.append({"timestamp": doc["timestamp"], "risk_score": doc["prediction"]["risk_score"]})
    trend.reverse()

    return {"total": total, "failure_distribution": distribution, "avg_metrics": avg_metrics, "risk_trend": trend}

@app.put("/api/admin/users/{uid}")
async def admin_update_user(uid: str, data: dict, admin=Depends(get_admin_user)):
    target = await db[COL_USERS].find_one({"_id": uid})
    if not target:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    update: dict = {}
    if data.get("name") and str(data["name"]).strip():
        update["name"] = str(data["name"]).strip()
    if data.get("password"):
        update["hashed_password"] = hash_password(str(data["password"]))
    if data.get("email") and str(data["email"]).strip():
        conflict = await db[COL_USERS].find_one({"email": data["email"], "_id": {"$ne": uid}})
        if conflict:
            raise HTTPException(status_code=400, detail="Email уже занят другим пользователем")
        update["email"] = str(data["email"]).strip()
    if update:
        await db[COL_USERS].update_one({"_id": uid}, {"$set": update})
    user = await db[COL_USERS].find_one({"_id": uid}, {"hashed_password": 0})
    return _user_out(user)

@app.put("/api/admin/users/{uid}/role")
async def admin_set_role(uid: str, data: dict, admin=Depends(get_admin_user)):
    if uid == admin["_id"]:
        raise HTTPException(status_code=400, detail="Нельзя изменить собственную роль")
    await db[COL_USERS].update_one({"_id": uid}, {"$set": {"is_admin": bool(data.get("is_admin"))}})
    user = await db[COL_USERS].find_one({"_id": uid}, {"hashed_password": 0})
    return _user_out(user)

@app.delete("/api/admin/users/{uid}")
async def admin_delete_user(uid: str, admin=Depends(get_admin_user)):
    if uid == admin["_id"]:
        raise HTTPException(status_code=400, detail="Нельзя удалить собственный аккаунт")
    await db[COL_TEL].delete_many({"user_id": uid})
    await db[COL_USERS].delete_one({"_id": uid})
    return {"ok": True}
