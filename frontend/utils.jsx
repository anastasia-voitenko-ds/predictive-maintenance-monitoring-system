/* Small utilities shared across components */

const fmtNum = (n, digits = 1) => {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return Number(n).toFixed(digits).replace(/\.0+$/, "");
};
const fmtPct = (n) => `${fmtNum(n, 1)}%`;
const fmtTime = (iso, withDate = false) => {
  const d = new Date(iso);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  if (!withDate) return `${hh}:${mm}:${ss}`;
  const dd = String(d.getDate()).padStart(2, "0");
  const mo = String(d.getMonth() + 1).padStart(2, "0");
  return `${dd}.${mo} ${hh}:${mm}:${ss}`;
};
const fmtAgo = (iso) => {
  const ms = Date.now() - new Date(iso).getTime();
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s} с назад`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} мин назад`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} ч назад`;
  return `${Math.floor(h / 24)} д назад`;
};

/* ---------- Icons (single 16/18px stroke set) ---------- */
const Icon = ({ name, size = 16 }) => {
  const p = {
    width: size, height: size, viewBox: "0 0 24 24",
    fill: "none", stroke: "currentColor", strokeWidth: 1.6,
    strokeLinecap: "round", strokeLinejoin: "round",
  };
  switch (name) {
    case "dashboard":
      return <svg {...p}><rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/></svg>;
    case "history":
      return <svg {...p}><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>;
    case "charts":
      return <svg {...p}><path d="M3 3v18h18"/><path d="M7 14l4-4 3 3 5-6"/></svg>;
    case "errors":
      return <svg {...p}><path d="M10.3 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4"/><circle cx="12" cy="17" r=".6" fill="currentColor"/></svg>;
    case "model":
      return <svg {...p}><circle cx="6" cy="6" r="2"/><circle cx="18" cy="6" r="2"/><circle cx="12" cy="13" r="2"/><circle cx="6" cy="20" r="2"/><circle cx="18" cy="20" r="2"/><path d="M7.5 7.2 10.7 11.6M16.5 7.2 13.3 11.6M10.7 14.6 7.5 18.6M13.3 14.6 16.5 18.6"/></svg>;
    case "search":
      return <svg {...p}><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>;
    case "refresh":
      return <svg {...p}><path d="M3 12a9 9 0 0 1 15.5-6.3L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15.5 6.3L3 16"/><path d="M3 21v-5h5"/></svg>;
    case "chev-l":
      return <svg {...p}><path d="m15 18-6-6 6-6"/></svg>;
    case "chev-r":
      return <svg {...p}><path d="m9 18 6-6-6-6"/></svg>;
    case "cpu":
      return <svg {...p}><rect x="5" y="5" width="14" height="14" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/></svg>;
    case "ram":
      return <svg {...p}><rect x="2" y="7" width="20" height="10" rx="1.5"/><path d="M6 11v2M10 11v2M14 11v2M18 11v2"/></svg>;
    case "battery":
      return <svg {...p}><rect x="3" y="7" width="16" height="10" rx="1.5"/><path d="M21 10v4"/><path d="M6 10v4M9 10v4M12 10v4"/></svg>;
    case "thermo":
      return <svg {...p}><path d="M14 14.76V4.5a2.5 2.5 0 0 0-5 0v10.26a4 4 0 1 0 5 0z"/></svg>;
    case "net":
      return <svg {...p}><path d="M5 12.5a10 10 0 0 1 14 0"/><path d="M8.5 16a5 5 0 0 1 7 0"/><circle cx="12" cy="19" r="1" fill="currentColor"/><path d="M2 9a14 14 0 0 1 20 0"/></svg>;
    case "packet":
      return <svg {...p}><path d="m21 16-9 5-9-5V8l9-5 9 5z"/><path d="M3.3 8 12 13l8.7-5M12 22V13"/></svg>;
    case "clock":
      return <svg {...p}><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>;
    case "load":
      return <svg {...p}><path d="M2 12a10 10 0 1 0 4-8"/><path d="M2 4v6h6"/></svg>;
    case "bug":
      return <svg {...p}><path d="M8 6h8M9 6V4a3 3 0 1 1 6 0v2"/><rect x="6" y="6" width="12" height="13" rx="6"/><path d="M2 11h4M2 15h4M18 11h4M18 15h4M12 19v3"/></svg>;
    case "filter":
      return <svg {...p}><path d="M3 5h18l-7 9v6l-4-2v-4z"/></svg>;
    case "download":
      return <svg {...p}><path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/></svg>;
    default: return null;
  }
};

Object.assign(window, { fmtNum, fmtPct, fmtTime, fmtAgo, Icon });
