"""
Desktop-агент: собирает телеметрию ПК и отправляет на бэкенд.
GUI на tkinter — дизайн совпадает с веб-дашбордом.
"""

import platform
import random
import re
import socket
import subprocess
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont
from tkinter import ttk

import psutil
import requests

API_BASE      = "http://localhost:8000"
API_URL       = f"{API_BASE}/api/telemetry"
SEND_INTERVAL = 30
TOKEN_FILE    = Path.home() / ".pcmonitor_token"

# ── Палитра (точно как в styles.css) ──────────────────────────────────────────
C = {
    "bg":       "#1f1d1a",
    "bg_soft":  "#242220",
    "surface":  "#2a2724",
    "card":     "#302d29",
    "border":   "#3d3a34",
    "text":     "#f2ede8",
    "text2":    "#cec8c0",
    "muted":    "#9a9389",
    "accent":   "#7dce82",   # --ok / green
    "warn":     "#c8b84a",   # --warn / yellow
    "crit":     "#e06040",   # --crit / red-orange
    "net":      "#9b72cc",   # --net / purple
    "heat":     "#d48040",   # --heat / orange
}

FAILURE_COLORS = {
    "Норма":        C["accent"],
    "Сбой батареи": C["warn"],
    "Сбой CPU":     C["crit"],
    "Сетевой сбой": C["net"],
    "Перегрев":     C["heat"],
}

OS = platform.system()

# ── Процессы-шум ──────────────────────────────────────────────────────────────
NOISE_PROCESSES = {
    "imagent", "searchpartyuseragent", "ecosystemanalyticsd",
    "mds", "mds_stores", "mdworker", "symptomsd", "trustd",
    "chronod", "corespotlightd", "ContextStoreAgent",
}
RELEVANT_KEYWORDS = [
    "thermal","overheat","temperature","memory pressure","low memory",
    "out of memory","disk","i/o error","apfs","hfs","kernel panic","panic",
    "crash","crashed","segfault","network","interface","ethernet","wifi",
    "wireless","power","battery","ups","gpu","graphics","nand","ssd","nvme",
    "error","fault","failed","failure",
]
IMPORTANT_PROCESSES = {
    "kernel","thermalmonitord","thermald","memoryd","memory_pressure",
    "diskmanagementd","fsck","fsck_apfs","WindowServer","ReportCrash",
    "crash_reporter","powerd","pmtool","configd","networkd","launchd","backupd",
}


# ── Токен ─────────────────────────────────────────────────────────────────────

def load_token() -> str | None:
    return TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else None

def save_token(t: str):  TOKEN_FILE.write_text(t)
def clear_token():
    if TOKEN_FILE.exists(): TOKEN_FILE.unlink()

def validate_token(token: str) -> bool:
    try:
        r = requests.get(f"{API_BASE}/api/auth/me",
                         headers={"Authorization": f"Bearer {token}"}, timeout=5)
        return r.status_code == 200
    except Exception:
        return False


# ── Системные ошибки ──────────────────────────────────────────────────────────

def _parse_macos_log_line(line: str) -> dict | None:
    m = re.match(
        r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+[+-]\d+)\s+'
        r'\S+\s+(\w+)\s+\S+\s+\d+\s+\d+\s+(\S+?):\s+(.+)$', line)
    if not m: return None
    ts, msg_type, process, message = m.groups()
    return {"timestamp": ts,
            "severity": "critical" if msg_type == "Fault" else "error",
            "process": process, "message": message.strip()}

def _is_relevant(e: dict) -> bool:
    proc, msg = e["process"].lower(), e["message"].lower()
    if proc in NOISE_PROCESSES: return False
    if "sandbox" in msg and "deny" in msg: return False
    if proc in IMPORTANT_PROCESSES: return True
    return any(kw in msg for kw in RELEVANT_KEYWORDS)

def _deduplicate(entries: list[dict], n: int = 20) -> list[dict]:
    seen: dict[str, dict] = {}
    for e in entries:
        seen[f"{e['process']}:{e['message'][:80]}"] = e
    unique = sorted(seen.values(), key=lambda x: x["timestamp"], reverse=True)
    return unique[:n]

def get_system_errors() -> tuple[int, list[dict]]:
    errors: list[dict] = []
    try:
        if OS == "Darwin":
            r = subprocess.run(["/usr/bin/log","show","--predicate","messageType >= 16","--last","1m"],
                               capture_output=True, text=True, timeout=10)
            for line in r.stdout.splitlines():
                if line.startswith("Timestamp") or not line.strip(): continue
                e = _parse_macos_log_line(line)
                if e and _is_relevant(e): errors.append(e)
        elif OS == "Linux":
            r = subprocess.run(["journalctl","-p","err","--since","1 minute ago","--no-pager","-o","short-iso"],
                               capture_output=True, text=True, timeout=10)
            for line in r.stdout.splitlines():
                if line.strip():
                    errors.append({"timestamp":line[:24],"severity":"error","process":"system","message":line})
        elif OS == "Windows":
            r = subprocess.run(["wevtutil","qe","System","/q:*[System[(Level=1 or Level=2)]]","/c:20","/rd:true","/f:text"],
                               capture_output=True, text=True, timeout=10)
            for line in r.stdout.splitlines():
                if "Message:" in line:
                    errors.append({"timestamp":"","severity":"error","process":"system","message":line.replace("Message:","").strip()})
    except Exception:
        pass
    errors = _deduplicate(errors)
    return sum(1 for e in errors if e["severity"] == "critical"), errors


# ── Метрики ───────────────────────────────────────────────────────────────────

def get_cpu_usage() -> float:        return psutil.cpu_percent(interval=1)
def get_memory_usage() -> float:     return psutil.virtual_memory().percent
def get_battery_level() -> float:
    b = psutil.sensors_battery()
    return round(b.percent, 1) if b else 100.0
def get_temperature() -> float:
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            for k in ("coretemp","cpu_thermal","k10temp","acpitz"):
                if k in temps and temps[k]: return round(temps[k][0].current, 1)
    except (AttributeError, NotImplementedError): pass
    return round(35.0 + psutil.cpu_percent() * 0.45 + random.uniform(-2,2), 1)
def get_uptime_hrs() -> float:       return round((time.time()-psutil.boot_time())/3600, 2)
def get_network_latency() -> float:
    try:
        cmd = (["ping","-n","1","-w","1000","8.8.8.8"] if OS=="Windows"
               else ["ping","-c","1","-W","1","8.8.8.8"])
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        for p in r.stdout.split():
            if "time=" in p: return round(float(p.split("=")[1].replace("ms","")), 2)
    except Exception: pass
    return round(random.uniform(5,80), 2)
def get_packet_loss() -> float:
    lost = sum(1 for _ in range(5) if subprocess.run(
        ["ping","-n","1","-w","500","8.8.8.8"] if OS=="Windows"
        else ["ping","-c","1","-W","1","8.8.8.8"],
        capture_output=True, timeout=2).returncode != 0)
    return round(lost/5*100, 1)
def get_workload_intensity(cpu: float) -> int:
    return 1 if cpu < 33 else (2 if cpu < 66 else 3)

def collect_telemetry() -> dict:
    cpu = get_cpu_usage()
    crit, errors = get_system_errors()
    return {
        "cpu_usage": cpu, "memory_usage": get_memory_usage(),
        "battery_level": get_battery_level(), "network_latency": get_network_latency(),
        "packet_loss": get_packet_loss(), "temperature": get_temperature(),
        "uptime_hrs": get_uptime_hrs(), "workload_intensity": get_workload_intensity(cpu),
        "error_count": crit, "total_error_count": len(errors),
        "system_errors": errors, "device_name": socket.gethostname(),
    }


# ── UI-хелперы ────────────────────────────────────────────────────────────────

def card(parent, **kw) -> tk.Frame:
    """Карточка с границей как на вебе."""
    wrap = tk.Frame(parent, bg=C["border"], **kw)
    inner = tk.Frame(wrap, bg=C["surface"])
    inner.pack(fill="both", expand=True, padx=1, pady=1)
    return inner

def section_label(parent, text: str, font):
    tk.Label(parent, text=text.upper(), font=font,
             bg=C["bg"], fg=C["muted"]).pack(anchor="w", pady=(14,4), padx=0)


# ── Окно входа / регистрации ──────────────────────────────────────────────────

class LoginWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PC Monitor")
        self.resizable(False, False)
        self.configure(bg=C["bg"])
        self.token: str | None = None
        self._mode = tk.StringVar(value="login")
        self._build_ui()
        self.geometry("400x360")

    def _build_ui(self):
        sf  = tkfont.Font(family="Helvetica", size=10)
        lf  = tkfont.Font(family="Helvetica", size=13, weight="bold")
        mf  = tkfont.Font(family="Courier",   size=9)

        # Логотип
        hdr = tk.Frame(self, bg=C["bg"], pady=16)
        hdr.pack(fill="x", padx=24)
        mark = tk.Frame(hdr, bg=C["accent"], width=30, height=30)
        mark.pack(side="left", padx=(0,10))
        mark.pack_propagate(False)
        tk.Label(mark, text="PC", font=tkfont.Font(family="Courier", size=10, weight="bold"),
                 bg=C["accent"], fg=C["bg"]).place(relx=.5, rely=.5, anchor="center")
        name_col = tk.Frame(hdr, bg=C["bg"])
        name_col.pack(side="left")
        tk.Label(name_col, text="PC Monitor", font=lf,   bg=C["bg"], fg=C["text"]).pack(anchor="w")
        tk.Label(name_col, text="v 2.4 · local", font=mf, bg=C["bg"], fg=C["muted"]).pack(anchor="w")

        # Переключатель
        sw = tk.Frame(self, bg=C["surface"], pady=3, padx=3)
        sw.pack(fill="x", padx=24, pady=(0,14))
        self._tab_btns = {}
        for mode, label in [("login","Войти"),("register","Регистрация")]:
            b = tk.Button(sw, text=label, font=sf, relief="flat",
                          bg=C["card"] if mode=="login" else C["surface"],
                          fg=C["text"] if mode=="login" else C["muted"],
                          activebackground=C["card"], activeforeground=C["text"],
                          padx=12, pady=5,
                          command=lambda m=mode: self._set_mode(m))
            b.pack(side="left", expand=True, fill="x")
            self._tab_btns[mode] = b

        # Форма
        self._form = tk.Frame(self, bg=C["bg"])
        self._form.pack(fill="x", padx=24)

        self._name_row  = self._field("Имя",    sf, mf)
        self._email_row = self._field("Email",  sf, mf)
        self._pass_row  = self._field("Пароль", sf, mf, show="●")
        self._name_var  = self._name_row[1]
        self._email_var = self._email_row[1]
        self._pass_var  = self._pass_row[1]

        self._btn = tk.Button(self, text="Войти", font=sf,
                              bg=C["accent"], fg=C["bg"], relief="flat",
                              padx=10, pady=9, command=self._submit)
        self._btn.pack(fill="x", padx=24, pady=(10,6))

        self._msg_var = tk.StringVar()
        tk.Label(self, textvariable=self._msg_var, font=sf, bg=C["bg"],
                 fg=C["crit"], wraplength=340).pack(padx=24)

        self._set_mode("login")
        self.bind("<Return>", lambda _: self._submit())

    def _field(self, label, sf, mf, show=""):
        row = tk.Frame(self._form, bg=C["bg"], pady=5)
        row.pack(fill="x")
        tk.Label(row, text=label, font=sf, bg=C["bg"], fg=C["muted"],
                 width=9, anchor="w").pack(side="left")
        var = tk.StringVar()
        wrap = tk.Frame(row, bg=C["border"])
        wrap.pack(side="left", fill="x", expand=True, padx=(4,0))
        e = tk.Entry(wrap, textvariable=var, font=mf, bg=C["surface"],
                     fg=C["text"], insertbackground=C["text"],
                     relief="flat", show=show, bd=0)
        e.pack(fill="x", padx=1, pady=1, ipady=6)
        return row, var

    def _set_mode(self, mode: str):
        self._mode.set(mode)
        for m, b in self._tab_btns.items():
            b.configure(bg=C["card"] if m==mode else C["surface"],
                        fg=C["text"] if m==mode else C["muted"])
        self._name_row[0].pack_forget()
        if mode == "register":
            self._name_row[0].pack(fill="x", before=self._email_row[0])
        self._btn.configure(text="Войти" if mode=="login" else "Зарегистрироваться")
        self._msg_var.set("")

    def _submit(self):
        self._msg_var.set("")
        self._btn.configure(state="disabled")
        threading.Thread(target=self._do_submit, daemon=True).start()

    def _do_submit(self):
        mode  = self._mode.get()
        email = self._email_var.get().strip()
        pw    = self._pass_var.get()
        if not email or not pw:
            self.after(0, lambda: self._err("Заполните все поля")); return
        try:
            if mode == "login":
                r = requests.post(f"{API_BASE}/api/auth/login",
                                  json={"email":email,"password":pw}, timeout=5)
            else:
                name = self._name_var.get().strip()
                if not name:
                    self.after(0, lambda: self._err("Введите имя")); return
                r = requests.post(f"{API_BASE}/api/auth/register",
                                  json={"name":name,"email":email,"password":pw}, timeout=5)
            if r.status_code in (200,201):
                save_token(r.json()["token"])
                self.token = r.json()["token"]
                self.after(0, self.destroy)
            else:
                msg = r.json().get("detail","Ошибка")
                self.after(0, lambda: self._err(msg))
        except requests.exceptions.ConnectionError:
            self.after(0, lambda: self._err("Сервер недоступен (localhost:8000)"))
        except Exception as ex:
            self.after(0, lambda: self._err(str(ex)))

    def _err(self, msg: str):
        self._msg_var.set(msg)
        self._btn.configure(state="normal")


# ── Главное окно ──────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self, token: str):
        super().__init__()
        self._token   = token
        self._running = True
        self.title("PC Monitor — Агент")
        self.configure(bg=C["bg"])
        self.resizable(True, True)
        self._build_ui()
        self._start_worker()

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"}

    # ── Построение UI ─────────────────────────────────────────────────────────

    def _build_ui(self):
        sf   = tkfont.Font(family="Helvetica", size=10)
        xsf  = tkfont.Font(family="Helvetica", size=9)
        mf   = tkfont.Font(family="Courier",   size=10)
        smf  = tkfont.Font(family="Courier",   size=9)
        valf = tkfont.Font(family="Courier",   size=19, weight="bold")
        lblf = tkfont.Font(family="Courier",   size=8)

        # ── Корневой layout: sidebar | main ────────────────────────────────
        root_frame = tk.Frame(self, bg=C["bg"])
        root_frame.pack(fill="both", expand=True)

        # ── SIDEBAR ────────────────────────────────────────────────────────
        sidebar = tk.Frame(root_frame, bg=C["bg_soft"], width=190)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        # Бренд
        brand = tk.Frame(sidebar, bg=C["bg_soft"], pady=16, padx=14)
        brand.pack(fill="x")
        mark = tk.Frame(brand, bg=C["accent"], width=32, height=32)
        mark.pack(side="left", padx=(0,10))
        mark.pack_propagate(False)
        tk.Label(mark, text="PC", font=tkfont.Font(family="Courier", size=11, weight="bold"),
                 bg=C["accent"], fg=C["bg"]).place(relx=.5, rely=.5, anchor="center")
        nm = tk.Frame(brand, bg=C["bg_soft"])
        nm.pack(side="left")
        tk.Label(nm, text="PC Monitor", font=sf,
                 bg=C["bg_soft"], fg=C["text"]).pack(anchor="w")
        tk.Label(nm, text="v 2.4 · local", font=smf,
                 bg=C["bg_soft"], fg=C["muted"]).pack(anchor="w")

        # Separator
        tk.Frame(sidebar, bg=C["border"], height=1).pack(fill="x", padx=14, pady=(0,10))

        # Nav-label
        tk.Label(sidebar, text="МОНИТОРИНГ", font=lblf,
                 bg=C["bg_soft"], fg=C["muted"]).pack(anchor="w", padx=14, pady=(6,2))
        nav_item = tk.Frame(sidebar, bg=C["card"], padx=10, pady=8)
        nav_item.pack(fill="x", padx=8)
        tk.Label(nav_item, text="●  Телеметрия", font=xsf,
                 bg=C["card"], fg=C["accent"]).pack(anchor="w")

        # Статус в сайдбаре
        tk.Frame(sidebar, bg=C["border"], height=1).pack(fill="x", padx=14, pady=(10,0), side="bottom")
        footer = tk.Frame(sidebar, bg=C["bg_soft"], padx=14, pady=12)
        footer.pack(side="bottom", fill="x")

        dot_frame = tk.Frame(footer, bg=C["bg_soft"])
        dot_frame.pack(side="left")
        self._dot = tk.Label(dot_frame, text="●", font=sf,
                             bg=C["bg_soft"], fg=C["muted"])
        self._dot.pack()

        info = tk.Frame(footer, bg=C["bg_soft"], padx=6)
        info.pack(side="left", fill="x", expand=True)
        self._device_var = tk.StringVar(value=socket.gethostname())
        tk.Label(info, textvariable=self._device_var, font=smf,
                 bg=C["bg_soft"], fg=C["text2"]).pack(anchor="w")
        self._status_var = tk.StringVar(value="Ожидание…")
        tk.Label(info, textvariable=self._status_var, font=smf,
                 bg=C["bg_soft"], fg=C["muted"]).pack(anchor="w")

        tk.Button(footer, text="⏻", font=sf, bg=C["bg_soft"], fg=C["muted"],
                  relief="flat", bd=0, cursor="hand2",
                  activebackground=C["bg_soft"], activeforeground=C["crit"],
                  command=self._logout).pack(side="right")

        # ── MAIN ───────────────────────────────────────────────────────────
        main = tk.Frame(root_frame, bg=C["bg"])
        main.pack(side="left", fill="both", expand=True)

        # Topbar
        topbar = tk.Frame(main, bg=C["bg"], pady=12, padx=20)
        topbar.pack(fill="x")
        tk.Frame(main, bg=C["border"], height=1).pack(fill="x")

        h1f = tkfont.Font(family="Helvetica", size=15, weight="bold")
        tk.Label(topbar, text="Телеметрия", font=h1f,
                 bg=C["bg"], fg=C["text"]).pack(side="left")

        # Таймер отправки
        self._countdown_var = tk.StringVar(value="")
        tk.Label(topbar, textvariable=self._countdown_var, font=smf,
                 bg=C["bg"], fg=C["muted"]).pack(side="right", padx=(8,0))

        # Кнопка "Отправить"
        send_btn = tk.Frame(topbar, bg=C["accent"])
        send_btn.pack(side="right")
        tk.Button(send_btn, text="↑ Отправить", font=xsf,
                  bg=C["accent"], fg=C["bg"], relief="flat", padx=10, pady=5,
                  activebackground=C["accent"], cursor="hand2",
                  command=self._force_send).pack(padx=1, pady=1)

        # Status pill
        self._pill_frame = tk.Frame(topbar, bg=C["surface"], padx=10, pady=4)
        self._pill_frame.pack(side="right", padx=12)
        self._pill_dot = tk.Label(self._pill_frame, text="●", font=smf,
                                  bg=C["surface"], fg=C["muted"])
        self._pill_dot.pack(side="left", padx=(0,5))
        self._pill_text = tk.Label(self._pill_frame, text="—", font=smf,
                                   bg=C["surface"], fg=C["muted"])
        self._pill_text.pack(side="left")

        # Прокручиваемая область контента
        content = tk.Frame(main, bg=C["bg"])
        content.pack(fill="both", expand=True, padx=20, pady=16)

        # ── TELE-GRID ──────────────────────────────────────────────────────
        tk.Label(content, text="МЕТРИКИ", font=lblf,
                 bg=C["bg"], fg=C["muted"]).pack(anchor="w", pady=(0,6))

        self._metric_vars: dict[str, tk.StringVar] = {}
        metrics_def = [
            ("CPU",           "cpu_usage",         "%"),
            ("ПАМЯТЬ",        "memory_usage",       "%"),
            ("ТЕМПЕРАТУРА",   "temperature",        "°C"),
            ("БАТАРЕЯ",       "battery_level",      "%"),
            ("СЕТЬ",          "network_latency",    "ms"),
            ("ПОТЕРИ",        "packet_loss",        "%"),
            ("UPTIME",        "uptime_hrs",         "ч"),
            ("НАГРУЗКА",      "workload_intensity", ""),
            ("КР. ОШИБОК",    "error_count",        "шт"),
        ]

        # Сетка = Frame с цветом border как фон, cells с gap 1px
        grid_bg = tk.Frame(content, bg=C["border"])
        grid_bg.pack(fill="x")

        ALERT_KEYS = {"cpu_usage", "temperature", "packet_loss", "error_count"}
        for i, (label, key, unit) in enumerate(metrics_def):
            cell = tk.Frame(grid_bg, bg=C["surface"], padx=14, pady=12)
            cell.grid(row=i//3, column=i%3, sticky="nsew", padx=1, pady=1)
            grid_bg.columnconfigure(i%3, weight=1)

            tk.Label(cell, text=label, font=lblf,
                     bg=C["surface"], fg=C["muted"]).pack(anchor="w")

            var = tk.StringVar(value="—")
            self._metric_vars[key] = var
            val_lbl = tk.Label(cell, textvariable=var, font=valf,
                               bg=C["surface"], fg=C["text2"])
            val_lbl.pack(anchor="w")
            # Единица
            tk.Label(cell, text=unit, font=smf,
                     bg=C["surface"], fg=C["muted"]).pack(anchor="w")

            # Мини-бар для % метрик
            if unit == "%":
                bar_bg = tk.Frame(cell, bg=C["card"], height=3)
                bar_bg.pack(fill="x", pady=(6,0))
                bar_bg.pack_propagate(False)
                bar_fill = tk.Frame(bar_bg, bg=C["accent"], height=3)
                bar_fill.place(x=0, y=0, relheight=1, relwidth=0)
                self._metric_vars[f"_bar_{key}"] = bar_fill  # type: ignore

        # ── ПРЕДСКАЗАНИЕ ───────────────────────────────────────────────────
        tk.Label(content, text="ПРЕДСКАЗАНИЕ МОДЕЛИ", font=lblf,
                 bg=C["bg"], fg=C["muted"]).pack(anchor="w", pady=(16,6))

        pred_inner = card(content)
        pred_inner.pack(fill="x")

        pred_top = tk.Frame(pred_inner, bg=C["surface"], padx=16, pady=14)
        pred_top.pack(fill="x")

        self._pred_label_var = tk.StringVar(value="—")
        biglf = tkfont.Font(family="Helvetica", size=17, weight="bold")
        self._pred_lbl = tk.Label(pred_top, textvariable=self._pred_label_var,
                                  font=biglf, bg=C["surface"], fg=C["muted"])
        self._pred_lbl.pack(side="left")

        self._risk_var = tk.StringVar(value="Риск: —")
        tk.Label(pred_top, textvariable=self._risk_var, font=smf,
                 bg=C["surface"], fg=C["muted"]).pack(side="right", padx=4)

        # Separator
        tk.Frame(pred_inner, bg=C["border"], height=1).pack(fill="x", padx=16)

        # Probability bars
        prob_area = tk.Frame(pred_inner, bg=C["surface"], padx=16, pady=10)
        prob_area.pack(fill="x")

        self._prob_vars: dict[str, tk.StringVar] = {}
        self._prob_fills: dict[str, tk.Frame]    = {}
        prob_colors = {
            "Норма":        C["accent"],
            "Сбой батареи": C["warn"],
            "Сбой CPU":     C["crit"],
            "Сетевой сбой": C["net"],
            "Перегрев":     C["heat"],
        }
        for pl, color in prob_colors.items():
            row = tk.Frame(prob_area, bg=C["surface"])
            row.pack(fill="x", pady=4)

            # Имя + процент в одну строку
            name_row = tk.Frame(row, bg=C["surface"])
            name_row.pack(fill="x")
            tk.Label(name_row, text=pl, font=xsf,
                     bg=C["surface"], fg=C["text2"]).pack(side="left")
            pv = tk.StringVar(value="0%")
            self._prob_vars[pl] = pv
            tk.Label(name_row, textvariable=pv, font=smf,
                     bg=C["surface"], fg=C["text2"]).pack(side="right")

            # Бар
            bar_bg = tk.Frame(row, bg=C["card"], height=5)
            bar_bg.pack(fill="x", pady=(2,0))
            bar_bg.pack_propagate(False)
            fill = tk.Frame(bar_bg, bg=color, height=5)
            fill.place(x=0, y=0, relheight=1, relwidth=0)
            self._prob_fills[pl] = fill

        # ── ОШИБКИ ─────────────────────────────────────────────────────────
        tk.Label(content, text="СИСТЕМНЫЕ ОШИБКИ", font=lblf,
                 bg=C["bg"], fg=C["muted"]).pack(anchor="w", pady=(16,6))

        err_inner = card(content)
        err_inner.pack(fill="x")

        err_area = tk.Frame(err_inner, bg=C["surface"], padx=14, pady=10)
        err_area.pack(fill="x")

        self.errors_text = tk.Text(err_area, height=4, bg=C["surface"], fg=C["muted"],
                                   font=smf, relief="flat", state="disabled",
                                   wrap="word", bd=0,
                                   selectbackground=C["card"])
        self.errors_text.pack(fill="x")

        self.geometry("700x640")

    # ── Логика ────────────────────────────────────────────────────────────────

    def _logout(self):
        clear_token()
        self._running = False
        self.destroy()
        lw = LoginWindow()
        lw.mainloop()
        if lw.token:
            a = App(lw.token)
            a.protocol("WM_DELETE_WINDOW", a.on_close)
            a.mainloop()

    def _start_worker(self):
        self._next_send = time.time()
        threading.Thread(target=self._worker_loop, daemon=True).start()
        self._tick()

    def _worker_loop(self):
        while self._running:
            if time.time() >= self._next_send:
                self._collect_and_send()
                self._next_send = time.time() + SEND_INTERVAL
            time.sleep(0.5)

    def _force_send(self): self._next_send = 0

    def _collect_and_send(self):
        self._set_status("Сбор метрик…", C["warn"])
        try:
            tel = collect_telemetry()
            self.after(0, lambda: self._update_metrics(tel))
            self.after(0, lambda: self._update_errors(tel.get("system_errors",[])))
            self._set_status("Отправка…", C["warn"])
            resp = requests.post(API_URL, json=tel, headers=self._auth_headers(), timeout=5)
            if resp.status_code == 401:
                self._set_status("Сессия истекла", C["crit"]); return
            resp.raise_for_status()
            self.after(0, lambda: self._update_prediction(resp.json()))
            self._set_status(f"Отправлено {time.strftime('%H:%M:%S')}", C["accent"])
        except requests.exceptions.ConnectionError:
            self._set_status("Сервер недоступен", C["crit"])
        except Exception as e:
            self._set_status(f"Ошибка: {e}", C["crit"])

    def _update_metrics(self, t: dict):
        thresholds = {
            "cpu_usage": 80, "temperature": 70,
            "packet_loss": 5, "error_count": 1,
        }
        for key, var in self._metric_vars.items():
            if key.startswith("_bar_"): continue
            val = t.get(key, "—")
            if isinstance(val, float):
                var.set(f"{val:.1f}")
            else:
                var.set(str(val))

            # Цвет значения
            threshold = thresholds.get(key)
            widget = var  # найдём Label через parent
            color = C["crit"] if (threshold and isinstance(val, (int,float)) and val >= threshold) else C["text"]
            # Обновить цвет мини-бара
            bar_key = f"_bar_{key}"
            if bar_key in self._metric_vars:
                bar_fill = self._metric_vars[bar_key]
                pct = min(val / 100, 1.0) if isinstance(val, (int,float)) else 0
                bar_color = C["crit"] if (threshold and isinstance(val,(int,float)) and val>=threshold) else C["accent"]
                bar_fill.configure(bg=bar_color)  # type: ignore
                bar_fill.place(relwidth=pct)      # type: ignore

    def _update_errors(self, errors: list[dict]):
        self.errors_text.configure(state="normal")
        self.errors_text.delete("1.0","end")
        if not errors:
            self.errors_text.configure(fg=C["accent"])
            self.errors_text.insert("end","Ошибок не обнаружено  ✓")
        else:
            self.errors_text.configure(fg=C["crit"])
            for e in errors[:5]:
                sev  = "✖" if e.get("severity") == "critical" else "⚠"
                proc = e.get("process","?")
                msg  = e.get("message","")[:110]
                self.errors_text.insert("end", f"{sev} [{proc}]  {msg}\n")
        self.errors_text.configure(state="disabled")

    def _update_prediction(self, data: dict):
        label = data.get("failure_label","—")
        risk  = data.get("risk_score", 0)
        probs = data.get("probabilities",{})
        color = FAILURE_COLORS.get(label, C["muted"])

        self._pred_label_var.set(label)
        self._pred_lbl.configure(fg=color)
        self._risk_var.set(f"Риск: {risk:.1f}%")

        # Status pill
        pill_color = (C["accent"] if label == "Норма"
                      else C["crit"] if risk > 60 else C["warn"])
        self._pill_dot.configure(fg=pill_color)
        self._pill_text.configure(text=label, fg=pill_color)

        # Probability bars
        for pl, fill in self._prob_fills.items():
            p = probs.get(pl, 0)
            self._prob_vars[pl].set(f"{p:.1f}%")
            fill.place(relwidth=min(p/100, 1.0))

    def _set_status(self, text: str, color: str):
        def _ui():
            self._status_var.set(text)
            self._dot.configure(fg=color)
        self.after(0, _ui)

    def _tick(self):
        remaining = max(0, int(self._next_send - time.time()))
        self._countdown_var.set(f"след. через {remaining} с")
        self.after(1000, self._tick)

    def on_close(self):
        self._running = False
        self.destroy()


# ── Точка входа ───────────────────────────────────────────────────────────────

def main():
    token = load_token()
    if not (token and validate_token(token)):
        lw = LoginWindow()
        lw.mainloop()
        token = lw.token
    if token:
        app = App(token)
        app.protocol("WM_DELETE_WINDOW", app.on_close)
        app.mainloop()

if __name__ == "__main__":
    main()
