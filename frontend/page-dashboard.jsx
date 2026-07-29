/* Dashboard page */
const { useState: useStateD, useMemo: useMemoD } = React;

function DashboardPage() {
  const latest = HISTORY[0];
  const prev = HISTORY[1];
  const t = latest.telemetry;
  const p = latest.prediction;

  const probs = Object.entries(p.probabilities)
    .map(([k, v]) => ({ k, v }))
    .sort((a, b) => b.v - a.v);

  const WORKLOAD_LBL = ["Низкая", "Средняя", "Высокая"];

  const tiles = [
    { k: "cpu_usage",       lbl: "CPU",        ico: "cpu",     val: t.cpu_usage,       unit: "%",   max: 100, warn: 60, crit: 85 },
    { k: "memory_usage",    lbl: "Память",     ico: "ram",     val: t.memory_usage,    unit: "%",   max: 100, warn: 80, crit: 92 },
    { k: "temperature",     lbl: "Темп.",      ico: "thermo",  val: t.temperature,     unit: "°C",  max: 90,  warn: 60, crit: 75 },
    { k: "battery_level",   lbl: "Батарея",    ico: "battery", val: t.battery_level,   unit: "%",   max: 100, warn: -1, crit: -1, invert: true, lowWarn: 30, lowCrit: 15 },
    { k: "network_latency", lbl: "Задержка",   ico: "net",     val: t.network_latency, unit: " ms", max: 300, warn: 120, crit: 200 },
    { k: "packet_loss",     lbl: "Потери",     ico: "packet",  val: t.packet_loss,     unit: "%",   max: 10,  warn: 2, crit: 5 },
    { k: "uptime_hrs",      lbl: "Аптайм",     ico: "clock",   val: t.uptime_hrs,      unit: " ч",  max: null },
    { k: "workload_intensity", lbl: "Нагрузка", ico: "load",   val: t.workload_intensity, unit: "", max: 2, warn: 2, crit: -1, textVal: WORKLOAD_LBL[t.workload_intensity] ?? "—", hint: "интенсивность 0–2" },
    { k: "error_count",     lbl: "Ошибки",     ico: "bug",     val: t.error_count,     unit: "",    max: 10, warn: 1, crit: 3 },
  ];

  const sevOf = (tile) => {
    if (tile.invert) {
      if (tile.val <= tile.lowCrit) return "alert";
      if (tile.val <= tile.lowWarn) return "warn";
      return "";
    }
    if (tile.crit !== -1 && tile.val >= tile.crit) return "alert";
    if (tile.warn !== -1 && tile.val >= tile.warn) return "warn";
    return "";
  };

  const colorVar = FAILURE_COLOR_VAR[p.failure_type];
  const chipCls  = FAILURE_CHIP[p.failure_type];

  // sparkline data for each tile (last 20 records)
  const recent20 = HISTORY.slice(0, 20).reverse();
  const spark = (key) => recent20.map((h, i) => ({ x: i, y: h.telemetry[key] }));

  // Stats summary
  const dist = STATS.failure_distribution;
  const totalRecords = STATS.total;

  return (
    <div className="page" data-screen-label="Dashboard">
      <div className="dash-grid">
        {/* Risk gauge */}
        <div className="card">
          <h3>Текущий риск</h3>
          <div className="gauge-wrap">
            <div className="gauge">
              <Gauge value={p.risk_score} max={100} size={220} colorVar={colorVar} />
              <div className="gauge-val">
                <div className="num">{fmtNum(p.risk_score, 1)}</div>
                <div className="lbl">RISK SCORE / 100</div>
              </div>
            </div>
            <div className="gauge-status">
              <span className={`chip ${chipCls}`}>
                <span className="dot"/>
                {p.failure_label}
              </span>
            </div>
            <div className="gauge-sub">
              Прогноз обновлён {fmtAgo(latest.timestamp)}
            </div>
          </div>
        </div>

        {/* Probabilities */}
        <div className="card">
          <h3>Вероятности классов</h3>
          <div className="prob-list">
            {probs.map(({ k, v }) => {
              const code = Object.entries(FAILURE_LABELS).find(([_, lbl]) => lbl === k)[0];
              const cvar = FAILURE_COLOR_VAR[code];
              return (
                <div className="prob-row" key={k}>
                  <span className="name">{k}</span>
                  <span className="val">{fmtNum(v, 2)}%</span>
                  <span className="bar">
                    <i style={{ width: `${v}%`, background: `var(${cvar})` }} />
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Top-of-card stats */}
        <div className="col" style={{ gap: 16 }}>
          <div className="stat-tile">
            <div className="k">ВСЕГО ИЗМЕРЕНИЙ</div>
            <div className="v">{totalRecords}</div>
            <div className="d up">↑ 12 за последний час</div>
          </div>
          <div className="stat-tile">
            <div className="k">СОБЫТИЙ «НОРМА»</div>
            <div className="v">{dist["Норма"]} <small style={{ color: "var(--muted)", fontSize: 14, fontWeight: 400 }}>· {fmtNum((dist["Норма"]/totalRecords)*100, 0)}%</small></div>
            <div className="d">{totalRecords - dist["Норма"]} аномалий зафиксировано</div>
          </div>
          <div className="stat-tile">
            <div className="k">СРЕДНИЙ РИСК (ОКНО)</div>
            <div className="v">{fmtNum(STATS.avg_metrics.risk_score, 1)}</div>
            <div className="d">по {totalRecords} наблюдениям</div>
          </div>
        </div>
      </div>

      {/* Telemetry grid */}
      <div>
        <div className="section-title">
          <h2>Телеметрия · live</h2>
          <span className="hr"/>
          <span className="muted mono" style={{ fontSize: 11 }}>обновление каждые 10 с</span>
        </div>
        <div className="tele-grid">
          {tiles.map(tile => {
            const sev = sevOf(tile);
            const pctVal = tile.max ? Math.min(100, (tile.val / tile.max) * 100) : 0;
            const accentForBar = sev === "alert" ? "var(--crit)" : sev === "warn" ? "var(--warn)" : "var(--accent)";
            return (
              <div className={`tele-cell ${sev}`} key={tile.k}>
                <div className="lbl"><Icon name={tile.ico} size={13}/> {tile.lbl}</div>
                {tile.textVal ? (
                  <div className="val" style={{ fontSize: 22 }}>{tile.textVal}<small style={{ marginLeft: 8 }}>{tile.hint}</small></div>
                ) : (
                  <div className="val">{fmtNum(tile.val, tile.unit === "%" || tile.unit.startsWith(" ms") || tile.unit === "°C" ? 1 : 0)}<small>{tile.unit}</small></div>
                )}
                {tile.max && (
                  <div className="minibar"><i style={{ width: `${pctVal}%`, background: accentForBar }} /></div>
                )}
                {!tile.max && <div className="spark"><Sparkline data={spark(tile.k)}/></div>}
              </div>
            );
          })}
        </div>
      </div>

      {/* Risk trend chart full-width */}
      <div className="card">
        <div className="chart-meta">
          <div className="chart-meta-main">
            <div className="caption">Тренд риска · последние 50 измерений</div>
            <div className="now-row">
              <span className="now">{fmtNum(p.risk_score, 1)}<span className="suffix">/ 100</span></span>
              <span className={`delta ${p.risk_score < prev.prediction.risk_score ? "up" : "down"}`}>
                {p.risk_score < prev.prediction.risk_score ? "↓" : "↑"} {fmtNum(Math.abs(p.risk_score - prev.prediction.risk_score), 2)} vs предыдущее
              </span>
            </div>
          </div>
          <div className="avg">
            <span>min · max</span>
            <b>
              {fmtNum(Math.min(...HISTORY.slice(0,50).map(h=>h.prediction.risk_score)), 1)}
              {" — "}
              {fmtNum(Math.max(...HISTORY.slice(0,50).map(h=>h.prediction.risk_score)), 1)}
            </b>
          </div>
        </div>
        <div className="chart-wrap">
          <LineChart
            data={HISTORY.slice(0, 50).reverse().map(h => ({ x: h.timestamp, y: h.prediction.risk_score }))}
            height={180}
            accentVar={colorVar}
            yMin={0} yMax={100}
          />
        </div>
      </div>
    </div>
  );
}

window.DashboardPage = DashboardPage;
