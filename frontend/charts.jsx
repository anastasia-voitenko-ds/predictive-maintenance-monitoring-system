/* Hand-rolled SVG charts — minimal, consistent with design language */

const { useMemo } = React;

function LineChart({ data, height = 140, accentVar = "--accent", fill = true, yMin, yMax, suffix = "" }) {
  // SVG (preserveAspectRatio="none") fills width, paths use non-scaling-stroke.
  // Axis labels rendered as HTML overlays in % to keep typography crisp.
  const W = 1000;
  const padL = 44, padR = 16, padT = 12, padB = 28;
  const w = W - padL - padR;
  const h = height - padT - padB;

  const xs = data.map(d => +new Date(d.x));
  const ys = data.map(d => d.y);
  const xMin = Math.min(...xs), xMax = Math.max(...xs);
  const realYMin = yMin ?? Math.min(...ys);
  const realYMax = yMax ?? Math.max(...ys);
  const yPad = (realYMax - realYMin) * 0.12 || 1;
  const lo = yMin ?? (realYMin - yPad);
  const hi = yMax ?? (realYMax + yPad);

  const sx = (x) => padL + ((x - xMin) / (xMax - xMin || 1)) * w;
  const sy = (y) => padT + (1 - (y - lo) / (hi - lo || 1)) * h;

  const path = data.map((d, i) => `${i === 0 ? "M" : "L"}${sx(+new Date(d.x))},${sy(d.y)}`).join(" ");
  const area = `${path} L${sx(xMax)},${padT + h} L${sx(xMin)},${padT + h} Z`;

  const ticks = 4;
  const yTicks = Array.from({ length: ticks + 1 }, (_, i) => lo + ((hi - lo) * i) / ticks);
  const xLabels = [data[0], data[Math.floor(data.length / 2)], data[data.length - 1]].filter(Boolean);

  const last = data[data.length - 1];
  const gradId = "g_" + Math.random().toString(36).slice(2, 8);

  const pctX = (x) => (x / W) * 100;
  const pctY = (y) => (y / height) * 100;

  return (
    <div className="lc-wrap" style={{ position: "relative", width: "100%", height }}>
      <svg
        viewBox={`0 0 ${W} ${height}`}
        preserveAspectRatio="none"
        style={{ position: "absolute", inset: 0, width: "100%", height: "100%", display: "block" }}
      >
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"   stopColor={`var(${accentVar})`} stopOpacity="0.28" />
            <stop offset="100%" stopColor={`var(${accentVar})`} stopOpacity="0" />
          </linearGradient>
        </defs>
        {yTicks.map((t, i) => (
          <line key={i} x1={padL} x2={W - padR} y1={sy(t)} y2={sy(t)}
                stroke="var(--border)" strokeDasharray="3 6" opacity="0.55"
                vectorEffect="non-scaling-stroke" />
        ))}
        {fill && <path d={area} fill={`url(#${gradId})`} />}
        <path d={path} fill="none" stroke={`var(${accentVar})`} strokeWidth="1.6"
              vectorEffect="non-scaling-stroke" strokeLinejoin="round" strokeLinecap="round" />
      </svg>

      {/* Y-axis labels — HTML overlay */}
      {yTicks.map((t, i) => (
        <div key={i} style={{
          position: "absolute",
          right: `${100 - pctX(padL - 6)}%`,
          top: `${pctY(sy(t))}%`,
          transform: "translateY(-50%)",
          fontFamily: "var(--font-mono)", fontSize: 10,
          color: "var(--muted)", whiteSpace: "nowrap", pointerEvents: "none",
        }}>
          {fmtNum(t, Math.abs(t) >= 10 ? 0 : 1)}{suffix}
        </div>
      ))}

      {/* X-axis labels — first, middle, last */}
      {xLabels.map((d, i) => {
        const xx = sx(+new Date(d.x));
        const pos = i === 0
          ? { left: `${pctX(xx)}%`, transform: "translateX(0)" }
          : i === xLabels.length - 1
          ? { right: `${100 - pctX(xx)}%`, transform: "translateX(0)" }
          : { left: `${pctX(xx)}%`, transform: "translateX(-50%)" };
        return (
          <div key={i} style={{
            position: "absolute",
            bottom: 4,
            ...pos,
            fontFamily: "var(--font-mono)", fontSize: 10,
            color: "var(--muted)", whiteSpace: "nowrap", pointerEvents: "none",
          }}>
            {fmtTime(d.x)}
          </div>
        );
      })}

      {/* last-point dot — HTML so it stays circular */}
      {last && (
        <div style={{
          position: "absolute",
          left: `${pctX(sx(+new Date(last.x)))}%`,
          top:  `${pctY(sy(last.y))}%`,
          transform: "translate(-50%, -50%)",
          width: 8, height: 8, borderRadius: "50%",
          background: `var(${accentVar})`,
          boxShadow: `0 0 0 5px color-mix(in oklab, var(${accentVar}) 22%, transparent)`,
          pointerEvents: "none",
        }}/>
      )}
    </div>
  );
}

function Sparkline({ data, accentVar = "--accent", height = 28 }) {
  const width = 120;
  const ys = data.map(d => d.y);
  const lo = Math.min(...ys);
  const hi = Math.max(...ys);
  const sx = (i) => (i / (data.length - 1)) * width;
  const sy = (y) => (1 - (y - lo) / (hi - lo || 1)) * (height - 4) + 2;
  const path = data.map((d, i) => `${i === 0 ? "M" : "L"}${sx(i)},${sy(d.y)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" style={{ width: "100%", height }}>
      <path d={path} fill="none" stroke={`var(${accentVar})`} strokeWidth="1.4" />
    </svg>
  );
}

function Doughnut({ data, size = 200, thickness = 28 }) {
  // data: [{ label, value, color }]
  const total = data.reduce((a, b) => a + b.value, 0) || 1;
  const r = size / 2 - thickness / 2 - 4;
  const cx = size / 2, cy = size / 2;
  const circ = 2 * Math.PI * r;
  let off = 0;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--card)" strokeWidth={thickness} />
      {data.map((d, i) => {
        const len = (d.value / total) * circ;
        const el = (
          <circle
            key={i}
            cx={cx} cy={cy} r={r}
            fill="none"
            stroke={d.color}
            strokeWidth={thickness}
            strokeDasharray={`${len} ${circ - len}`}
            strokeDashoffset={-off}
            transform={`rotate(-90 ${cx} ${cy})`}
            strokeLinecap="butt"
          />
        );
        off += len;
        return el;
      })}
      <text x={cx} y={cy - 6} textAnchor="middle" fontSize="28" fontWeight="500" fontFamily="var(--font-mono)" fill="var(--text)" letterSpacing="-1">
        {total}
      </text>
      <text x={cx} y={cy + 14} textAnchor="middle" fontSize="10" fontFamily="var(--font-mono)" fill="var(--muted)" letterSpacing="0.6">
        ВСЕГО ЗАПИСЕЙ
      </text>
    </svg>
  );
}

function Gauge({ value, max = 100, size = 220, thickness = 14, colorVar = "--accent" }) {
  // Top-half semicircle gauge 0..max.
  // SVG y points DOWN, so we negate sin to make the arc go ABOVE the baseline.
  const vbH = Math.round(size * 0.62);
  const cx = size / 2;
  const cy = vbH - thickness / 2 - 4; // baseline near the bottom of the viewBox
  const r  = size / 2 - thickness / 2 - 2;

  const start = Math.PI; // left end of baseline
  const end   = 0;       // right end of baseline
  const pct   = Math.max(0, Math.min(1, value / max));
  const ang   = start + (end - start) * pct;

  const pt = (a) => [cx + r * Math.cos(a), cy - r * Math.sin(a)];
  const arcPath = (a0, a1) => {
    const [x0, y0] = pt(a0);
    const [x1, y1] = pt(a1);
    const large = Math.abs(a1 - a0) > Math.PI ? 1 : 0;
    // From left baseline up over the top to the right is CLOCKWISE on screen (y-down) → sweep 1
    const sweep = 1;
    return `M ${x0} ${y0} A ${r} ${r} 0 ${large} ${sweep} ${x1} ${y1}`;
  };

  return (
    <svg width={size} height={vbH} viewBox={`0 0 ${size} ${vbH}`}>
      <path d={arcPath(start, end)} fill="none" stroke="var(--card)" strokeWidth={thickness} strokeLinecap="round" />
      {pct > 0.001 && (
        <path d={arcPath(start, ang)} fill="none" stroke={`var(${colorVar})`} strokeWidth={thickness} strokeLinecap="round" />
      )}
      {/* tick marks */}
      {[0, 0.25, 0.5, 0.75, 1].map((tk, i) => {
        const a = start + (end - start) * tk;
        const r1 = r + thickness / 2 + 4;
        const r2 = r + thickness / 2 + 9;
        const x1 = cx + r1 * Math.cos(a), y1 = cy - r1 * Math.sin(a);
        const x2 = cx + r2 * Math.cos(a), y2 = cy - r2 * Math.sin(a);
        return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--muted-2)" strokeWidth="1" />;
      })}
    </svg>
  );
}

Object.assign(window, { LineChart, Sparkline, Doughnut, Gauge });
