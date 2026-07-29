/* App shell — sidebar nav + topbar + active page */

const { useState: useStateA, useEffect: useEffectA } = React;

const TABS = [
  { id: "dashboard", label: "Дашборд",      ico: "dashboard", desc: "Состояние устройства · live" },
  { id: "history",   label: "История",      ico: "history",   desc: "Журнал измерений и прогнозов" },
  { id: "charts",    label: "Графики",      ico: "charts",    desc: "Тренды телеметрии" },
  { id: "errors",    label: "Ошибки",       ico: "errors",    desc: "Системные события" },
  { id: "model",     label: "Модель",       ico: "model",     desc: "Метрики и feature importance" },
  { id: "profile",   label: "Профиль",      ico: "model",     desc: "Настройки аккаунта" },
];

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "accent": "#7BC97A",
  "theme":  "dark",
  "showSecondsClock": true
}/*EDITMODE-END*/;

const ACCENT_HUE = {
  "#7BC97A": 145,
  "#74B6E0": 210,
  "#B791DD": 300,
  "#D8C36A": 75,
  "#E59C7A": 30,
};

// ── Корневой компонент: только управление авторизацией ────────────────────────

function App() {
  const [authed, setAuthed]   = useStateA(!!getToken());
  const [curUser, setCurUser] = useStateA(null);

  function handleAuth(user) {
    setCurUser(user);
    window.CURRENT_USER = user;
    setAuthed(true);
  }

  function handleLogout() {
    clearToken();
    window.CURRENT_USER = null;
    window.HISTORY = [];
    setCurUser(null);
    setAuthed(false);
  }

  if (!authed) {
    return <AuthPage onAuth={handleAuth} />;
  }

  return <MainApp curUser={curUser} setCurUser={setCurUser} onLogout={handleLogout} />;
}

// ── Основное приложение: все хуки и дашборд ───────────────────────────────────

function MainApp({ curUser, setCurUser, onLogout }) {
  const [tab, setTab]     = useStateA("dashboard");
  const [now, setNow]     = useStateA(new Date());
  const [t, setTweak]     = useTweaks(TWEAK_DEFAULTS);
  const [loading, setLoading] = useStateA(true);
  const [tick, setTick]   = useStateA(0);
  const [error, setError] = useStateA(null);

  // Часы
  useEffectA(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  // Акцент
  useEffectA(() => {
    const hue = ACCENT_HUE[t.accent] ?? 145;
    document.documentElement.style.setProperty("--accent",      `oklch(0.80 0.16 ${hue})`);
    document.documentElement.style.setProperty("--accent-soft", `oklch(0.80 0.16 ${hue} / 0.15)`);
    document.documentElement.style.setProperty("--ok",          `oklch(0.80 0.16 ${hue})`);
    document.documentElement.style.setProperty("--ok-bg",       `oklch(0.80 0.16 ${hue} / 0.12)`);
  }, [t.accent]);

  // Тема
  useEffectA(() => {
    document.body.classList.toggle("theme-light", t.theme === "light");
  }, [t.theme]);

  // Загрузка данных + авто-обновление каждые 30 сек
  const doFetch = () => {
    setError(null);
    window.__authExpired = false;

    const mePromise = curUser
      ? Promise.resolve()
      : apiFetch(`${API}/api/auth/me`).then(r => r.json()).then(u => {
          setCurUser(u);
          window.CURRENT_USER = u;
        }).catch(() => {});

    Promise.all([mePromise, fetchAllData()])
      .then(() => { setLoading(false); setTick(n => n + 1); })
      .catch(() => {
        setLoading(false);
        if (window.__authExpired) {
          onLogout();
        } else {
          setError("Сервер недоступен");
        }
      });
  };

  useEffectA(() => {
    doFetch();
    const id = setInterval(doFetch, 30_000);
    return () => clearInterval(id);
  }, []);

  // ── Loading / Error ────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div style={{ display:"flex", alignItems:"center", justifyContent:"center",
                    height:"100vh", flexDirection:"column", gap:16, color:"var(--muted)" }}>
        <div style={{ fontSize:32 }}>⬡</div>
        <div>Подключение к серверу…</div>
        <div className="mono" style={{ fontSize:12 }}>http://localhost:8000</div>
      </div>
    );
  }

  if (error || HISTORY.length === 0) {
    return (
      <div style={{ display:"flex", alignItems:"center", justifyContent:"center",
                    height:"100vh", flexDirection:"column", gap:16, color:"var(--muted)" }}>
        <div style={{ fontSize:32, color:"var(--crit)" }}>✖</div>
        <div style={{ color:"var(--text)" }}>{error ?? "Нет данных"}</div>
        <div style={{ fontSize:13 }}>Убедитесь что бэкенд запущен и Desktop-агент отправил данные</div>
        <div style={{ display:"flex", gap:8 }}>
          <button className="btn" onClick={doFetch}>↻ Повторить</button>
          <button className="btn" onClick={onLogout} style={{ opacity:.7 }}>Выйти</button>
        </div>
      </div>
    );
  }

  // ── Основной рендер ────────────────────────────────────────────────────────
  const counts = { errors: ERRORS.length, history: HISTORY.length };

  const cur = HISTORY[0];
  const statusClass = cur.prediction.failure_type === 0 ? "ok"
                    : cur.prediction.risk_score > 60   ? "crit" : "warn";
  const statusText  = cur.prediction.failure_type === 0
                    ? "Все системы в норме"
                    : cur.prediction.failure_label;

  const allTabs = [
    ...TABS,
    ...(curUser?.is_admin ? [{ id: "admin", label: "Админ-панель", ico: "errors", desc: "Управление пользователями" }] : []),
  ];

  const activeTab = allTabs.find(tb => tb.id === tab) ?? allTabs[0];

  const Page = {
    dashboard: DashboardPage,
    history:   HistoryPage,
    charts:    ChartsPage,
    errors:    ErrorsPage,
    model:     ModelPage,
    profile:   ProfilePage,
    admin:     AdminPage,
  }[tab] ?? DashboardPage;

  return (
    <>
      <div className="app">
        {/* Sidebar */}
        <aside className="sidebar">
          <div className="brand">
            <div className="brand-mark">PC</div>
            <div className="brand-name">
              <b>PC Monitor</b>
              <span>v 2.4 · local</span>
            </div>
          </div>

          <div className="nav-group-label">Мониторинг</div>
          {TABS.slice(0, 4).map(tb => (
            <button
              key={tb.id}
              className={`nav-item ${tab === tb.id ? "active" : ""}`}
              onClick={() => setTab(tb.id)}
            >
              <span className="nav-ico"><Icon name={tb.ico}/></span>
              {tb.label}
              {tb.id === "errors"  && <span className="nav-count">{counts.errors}</span>}
              {tb.id === "history" && <span className="nav-count">{counts.history}</span>}
            </button>
          ))}

          <div className="nav-group-label">Аналитика</div>
          {TABS.slice(4, 5).map(tb => (
            <button
              key={tb.id}
              className={`nav-item ${tab === tb.id ? "active" : ""}`}
              onClick={() => setTab(tb.id)}
            >
              <span className="nav-ico"><Icon name={tb.ico}/></span>
              {tb.label}
            </button>
          ))}

          <div className="nav-group-label">Аккаунт</div>
          {TABS.slice(5).map(tb => (
            <button
              key={tb.id}
              className={`nav-item ${tab === tb.id ? "active" : ""}`}
              onClick={() => setTab(tb.id)}
            >
              <span className="nav-ico"><Icon name={tb.ico}/></span>
              {tb.label}
            </button>
          ))}

          {curUser?.is_admin && (
            <>
              <div className="nav-group-label">Система</div>
              <button
                className={`nav-item ${tab === "admin" ? "active" : ""}`}
                onClick={() => setTab("admin")}
                style={{ color: tab === "admin" ? undefined : "var(--crit)" }}
              >
                <span className="nav-ico"><Icon name="errors"/></span>
                Админ-панель
              </button>
            </>
          )}

          <div className="sidebar-footer">
            <span className="dot"/>
            <div style={{ display:"flex", flexDirection:"column", lineHeight:1.3, flex:1 }}>
              <span style={{ color:"var(--text-2)" }} className="mono">{cur.device_name}</span>
              <span>агент онлайн</span>
            </div>
            <button
              title="Выйти"
              onClick={onLogout}
              style={{
                background:"none", border:"none", cursor:"pointer",
                color:"var(--muted)", fontSize:16, padding:"2px 4px", lineHeight:1,
              }}
            >⏻</button>
          </div>
        </aside>

        {/* Main column */}
        <div className="main">
          <div className="topbar">
            <div>
              <h1>{activeTab.label}</h1>
              <div className="crumb">{activeTab.desc}</div>
            </div>
            <span className="spacer"/>
            <span className={`status-pill ${statusClass}`}>
              <span className="dot"/> {statusText}
            </span>
            <div className="device-meta">
              <span>
                <b className="mono">
                  {t.showSecondsClock ? fmtTime(now.toISOString()) : fmtTime(now.toISOString()).slice(0, 5)}
                </b> MSK
              </span>
              <span>·</span>
              <span>обновлено <b>{fmtAgo(cur.timestamp)}</b></span>
            </div>
            <button className="btn" onClick={doFetch}>
              <Icon name="refresh" size={14}/> Обновить
            </button>
          </div>

          <Page/>
        </div>
      </div>

      {/* Tweaks panel */}
      <TweaksPanel title="Tweaks">
        <TweakSection label="Акцент"/>
        <TweakColor
          label="Цвет"
          value={t.accent}
          options={["#7BC97A", "#74B6E0", "#B791DD", "#D8C36A", "#E59C7A"]}
          onChange={(v) => setTweak("accent", v)}
        />
        <TweakSection label="Тема"/>
        <TweakRadio
          label="Режим"
          value={t.theme}
          options={["dark", "light"]}
          onChange={(v) => setTweak("theme", v)}
        />
        <TweakSection label="Часы"/>
        <TweakToggle
          label="Показывать секунды"
          value={t.showSecondsClock}
          onChange={(v) => setTweak("showSecondsClock", v)}
        />
      </TweaksPanel>
    </>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App/>);
