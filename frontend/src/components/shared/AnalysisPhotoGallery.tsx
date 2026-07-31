import { useState } from 'react';
import type { AnnotatedFrame } from '@/data/types';

interface Props { frames: AnnotatedFrame[]; }

// Group frames by camera view when the analyzer tags them with 'side' / 'front'.
// Other analyzers use 'left' / 'right' / 'center' for bilateral exercises and
// fall back to a single ungrouped strip.
const CAMERA_GROUPS: Record<string, string> = {
  side:  'SIDE VIEW',
  front: 'FRONT VIEW',
};

function FrameCard({ f, onClick }: { f: AnnotatedFrame; onClick: () => void }) {
  const isBest = f.is_best;
  const accent = isBest ? '#00e5b0' : '#a855f7';
  return (
    <div className="flex-shrink-0 snap-start cursor-pointer relative" onClick={onClick}
      style={{ width: 380, borderRadius: 16, overflow: 'hidden', border: `2px solid ${isBest ? '#00e5b0' : 'rgba(68,136,255,0.18)'}`, background: 'rgba(13,23,40,0.92)', transition: 'transform 0.2s, box-shadow 0.2s', boxShadow: isBest ? '0 0 24px rgba(0,229,176,0.15)' : 'none' }}
      onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-4px)'; e.currentTarget.style.boxShadow = `0 12px 36px ${isBest ? 'rgba(0,229,176,0.25)' : 'rgba(168,85,247,0.15)'}`; }}
      onMouseLeave={e => { e.currentTarget.style.transform = 'translateY(0)'; e.currentTarget.style.boxShadow = isBest ? '0 0 24px rgba(0,229,176,0.15)' : 'none'; }}>
      <div style={{ position: 'absolute', top: 10, left: 10, zIndex: 2, background: 'rgba(6,8,15,0.85)', backdropFilter: 'blur(6px)', border: `1px solid ${accent}55`, borderRadius: 8, padding: '4px 10px', fontFamily: 'Space Grotesk', fontWeight: 700, fontSize: 10, letterSpacing: '0.12em', color: accent, textTransform: 'uppercase' }}>
        {f.label}
      </div>
      {isBest && (
        <div style={{ position: 'absolute', top: 10, right: 10, zIndex: 2, background: 'rgba(0,229,176,0.18)', backdropFilter: 'blur(6px)', border: '1px solid rgba(0,229,176,0.4)', borderRadius: 8, padding: '4px 10px', fontFamily: 'Space Grotesk', fontWeight: 800, fontSize: 10, letterSpacing: '0.14em', color: '#00e5b0' }}>
          ★ BEST REP
        </div>
      )}
      <img src={f.image_base64} alt={f.label}
        style={{ width: '100%', height: 240, objectFit: 'cover', display: 'block' }} />
      <div style={{ padding: '12px 14px' }}>
        <div className="flex gap-2 flex-wrap">
          {f.metrics_shown.map((m, j) => {
            const isFail = m.toLowerCase().includes('fail') ||
                           m.toLowerCase().includes('lift') && !m.toLowerCase().includes('ok') ||
                           m.toLowerCase().includes('no') ||
                           m.includes('✗');
            const isPass = m.includes('✓') || m.toLowerCase().includes('ok');
            const tone = isFail ? '#ff4466' : (isPass ? '#00e5b0' : '#8899bb');
            const bg   = isFail ? 'rgba(255,68,102,0.10)' : (isPass ? 'rgba(0,229,176,0.10)' : 'rgba(68,136,255,0.08)');
            const bd   = isFail ? 'rgba(255,68,102,0.25)' : (isPass ? 'rgba(0,229,176,0.25)' : 'rgba(68,136,255,0.15)');
            return (
              <span key={j} style={{ background: bg, border: `1px solid ${bd}`, borderRadius: 6, padding: '3px 9px', fontSize: 11, color: tone, fontFamily: 'Space Grotesk', fontWeight: 600, letterSpacing: '0.02em' }}>{m}</span>
            );
          })}
        </div>
        <div className="mt-2.5 flex items-center justify-between" style={{ borderTop: '1px solid rgba(68,136,255,0.08)', paddingTop: 8 }}>
          <span style={{ fontFamily: 'Space Grotesk', fontSize: 10, letterSpacing: '0.12em', color: '#4a5a7a', textTransform: 'uppercase' }}>Click to enlarge</span>
          <span style={{ fontFamily: 'Space Grotesk', fontWeight: 700, fontSize: 11, color: accent }}>↗</span>
        </div>
      </div>
    </div>
  );
}

export function AnalysisPhotoGallery({ frames }: Props) {
  const [selected, setSelected] = useState<AnnotatedFrame | null>(null);
  if (!frames || frames.length === 0) return null;

  // Group by camera label only if the analyzer split frames between cameras.
  const hasMultiCam = frames.some(f => CAMERA_GROUPS[f.side]) &&
                      new Set(frames.map(f => f.side)).size > 1;

  if (hasMultiCam) {
    const groups = ['side', 'front'].map(g => ({
      key: g,
      title: CAMERA_GROUPS[g],
      items: frames.filter(f => f.side === g),
    })).filter(g => g.items.length > 0);

    return (
      <>
        <div className="flex flex-col gap-6">
          {groups.map(g => (
            <div key={g.key}>
              <div className="flex items-center gap-3 mb-3 px-1">
                <div style={{ width: 3, height: 16, borderRadius: 2, background: '#00e5b0', boxShadow: '0 0 8px #00e5b0' }} />
                <span style={{ fontFamily: 'Space Grotesk', fontWeight: 700, fontSize: 11, letterSpacing: '0.18em', color: '#8899bb', textTransform: 'uppercase' }}>{g.title}</span>
                <span style={{ background: 'rgba(0,229,176,0.10)', border: '1px solid rgba(0,229,176,0.25)', borderRadius: 20, padding: '2px 10px', fontFamily: 'Space Grotesk', fontWeight: 600, fontSize: 10, color: '#00e5b0' }}>{g.items.length} rep{g.items.length !== 1 ? 's' : ''}</span>
              </div>
              <div className="flex gap-4 overflow-x-auto pb-3 snap-x" style={{ scrollbarWidth: 'thin' }}>
                {g.items.map((f, i) => <FrameCard key={i} f={f} onClick={() => setSelected(f)} />)}
              </div>
            </div>
          ))}
        </div>
        {selected && <FrameModal frame={selected} onClose={() => setSelected(null)} />}
      </>
    );
  }

  return (
    <>
      <div className="flex gap-4 overflow-x-auto pb-3 snap-x" style={{ scrollbarWidth: 'thin' }}>
        {frames.map((f, i) => <FrameCard key={i} f={f} onClick={() => setSelected(f)} />)}
      </div>
      {selected && <FrameModal frame={selected} onClose={() => setSelected(null)} />}
    </>
  );
}

function FrameModal({ frame, onClose }: { frame: AnnotatedFrame; onClose: () => void }) {
  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 9999, background: 'rgba(6,8,15,0.95)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'zoom-out', padding: 24 }}>
      <div style={{ maxWidth: '92vw', maxHeight: '92vh', position: 'relative' }} onClick={e => e.stopPropagation()}>
        <img src={frame.image_base64} alt={frame.label}
          style={{ maxWidth: '92vw', maxHeight: '82vh', borderRadius: 16, border: '1px solid rgba(68,136,255,0.2)', display: 'block' }} />
        <div style={{ textAlign: 'center', marginTop: 14 }}>
          <span style={{ fontFamily: 'Space Grotesk', fontWeight: 700, fontSize: 16, color: '#e2e8f8', letterSpacing: '0.04em' }}>{frame.label}</span>
          <div className="flex gap-2 justify-center mt-3 flex-wrap">
            {frame.metrics_shown.map((m, j) => (
              <span key={j} style={{ background: 'rgba(68,136,255,0.12)', border: '1px solid rgba(68,136,255,0.22)', borderRadius: 8, padding: '5px 12px', fontSize: 13, color: '#cfd8e8', fontFamily: 'Space Grotesk', fontWeight: 600 }}>{m}</span>
            ))}
          </div>
        </div>
        <button onClick={onClose}
          style={{ position: 'absolute', top: -14, right: -14, width: 36, height: 36, borderRadius: '50%', background: 'rgba(255,68,102,0.25)', border: '1px solid rgba(255,68,102,0.5)', color: '#ff4466', fontSize: 18, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>✕</button>
      </div>
    </div>
  );
}
