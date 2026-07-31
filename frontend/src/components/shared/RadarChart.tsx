import type { Metric } from '@/data/types';

interface Props { metrics: Metric[]; size?: number; }

export function RadarChart({ metrics, size = 280 }: Props) {
  if (!metrics || metrics.length < 3) return null;

  const cx = size / 2, cy = size / 2, r = size * 0.38;
  const n = Math.min(metrics.length, 8);
  const items = metrics.slice(0, n);

  const getPoint = (i: number, val: number, max: number) => {
    const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
    const ratio = Math.min(val / (max || 1), 1);
    return { x: cx + r * ratio * Math.cos(angle), y: cy + r * ratio * Math.sin(angle) };
  };

  const gridLevels = [0.25, 0.5, 0.75, 1];
  const targetRatio = 0.7;

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {/* Grid */}
      {gridLevels.map(level => (
        <polygon key={level} fill="none" stroke="rgba(68,136,255,0.1)" strokeWidth="1"
          points={items.map((_, i) => { const p = getPoint(i, level, 1); return `${p.x},${p.y}`; }).join(' ')} />
      ))}
      {/* Axis lines */}
      {items.map((_, i) => { const p = getPoint(i, 1, 1); return <line key={i} x1={cx} y1={cy} x2={p.x} y2={p.y} stroke="rgba(68,136,255,0.08)" strokeWidth="1" />; })}
      {/* Target zone */}
      <polygon fill="rgba(0,229,176,0.06)" stroke="rgba(0,229,176,0.2)" strokeWidth="1" strokeDasharray="4 3"
        points={items.map((_, i) => { const p = getPoint(i, targetRatio, 1); return `${p.x},${p.y}`; }).join(' ')} />
      {/* Data polygon */}
      <polygon fill="rgba(68,136,255,0.12)" stroke="#4488ff" strokeWidth="2"
        points={items.map((m, i) => { const p = getPoint(i, m.raw, m.max); return `${p.x},${p.y}`; }).join(' ')} />
      {/* Data dots */}
      {items.map((m, i) => { const p = getPoint(i, m.raw, m.max); const c = m.status === 'good' ? '#00e5b0' : '#ff4466'; return <circle key={i} cx={p.x} cy={p.y} r="4" fill={c} stroke={c} strokeWidth="1" />; })}
      {/* Labels */}
      {items.map((m, i) => {
        const p = getPoint(i, 1.22, 1);
        const anchor = p.x < cx - 10 ? 'end' : p.x > cx + 10 ? 'start' : 'middle';
        const name = m.name.length > 14 ? m.name.slice(0, 12) + '…' : m.name;
        return (
          <g key={i}>
            <text x={p.x} y={p.y - 6} textAnchor={anchor} fill="#8899bb" fontSize="9" fontFamily="Space Grotesk" fontWeight="500">{name}</text>
            <text x={p.x} y={p.y + 6} textAnchor={anchor} fill={m.status === 'good' ? '#00e5b0' : '#ff4466'} fontSize="10" fontFamily="Space Grotesk" fontWeight="700">{m.value}</text>
          </g>
        );
      })}
    </svg>
  );
}
