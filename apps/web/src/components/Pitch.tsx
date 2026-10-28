import type { Player, Team } from "../lib/types";

const L = 105;
const W = 68;

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const n = parseInt(full.slice(0, 6) || "94a3b8", 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

export function Pitch({
  teams,
  players,
  mode,
  selectedTeam,
  selectedPlayer,
}: {
  teams: Team[];
  players: Player[];
  mode: "positions" | "heat";
  selectedTeam: number | null;
  selectedPlayer?: number | null;
}) {
  const shown = teams.filter((t) => selectedTeam === null || t.id === selectedTeam);

  return (
    <svg className="pitch" viewBox={`-3 -3 ${L + 6} ${W + 6}`} role="img" aria-label="Pitch map">
      <defs>
        <linearGradient id="grass" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#123d27" />
          <stop offset="100%" stopColor="#0a2417" />
        </linearGradient>
        {shown.map((t) => {
          const [r, g, b] = hexToRgb(t.colour);
          return (
            <radialGradient key={t.id} id={`glow-${t.id}`}>
              <stop offset="0%" stopColor={`rgb(${r},${g},${b})`} stopOpacity="0.95" />
              <stop offset="100%" stopColor={`rgb(${r},${g},${b})`} stopOpacity="0.35" />
            </radialGradient>
          );
        })}
      </defs>

      <rect x={0} y={0} width={L} height={W} fill="url(#grass)" rx={0.4} />
      {Array.from({ length: 10 }).map((_, i) => (
        <rect
          key={i}
          x={(i * L) / 10}
          y={0}
          width={L / 10}
          height={W}
          fill="#ffffff"
          opacity={i % 2 === 0 ? 0.022 : 0}
        />
      ))}

      <g fill="none" stroke="rgba(255,255,255,0.34)" strokeWidth={0.22}>
        <rect x={0} y={0} width={L} height={W} />
        <line x1={L / 2} y1={0} x2={L / 2} y2={W} />
        <circle cx={L / 2} cy={W / 2} r={9.15} />
        <circle cx={L / 2} cy={W / 2} r={0.45} fill="rgba(255,255,255,0.5)" stroke="none" />
        <rect x={0} y={W / 2 - 20.16} width={16.5} height={40.32} />
        <rect x={0} y={W / 2 - 9.16} width={5.5} height={18.32} />
        <rect x={L - 16.5} y={W / 2 - 20.16} width={16.5} height={40.32} />
        <rect x={L - 5.5} y={W / 2 - 9.16} width={5.5} height={18.32} />
        <circle cx={11} cy={W / 2} r={0.45} fill="rgba(255,255,255,0.5)" stroke="none" />
        <circle cx={L - 11} cy={W / 2} r={0.45} fill="rgba(255,255,255,0.5)" stroke="none" />
        <path d={`M 16.5 ${W / 2 - 9.16} A 9.15 9.15 0 0 1 16.5 ${W / 2 + 9.16}`} />
        <path d={`M ${L - 16.5} ${W / 2 - 9.16} A 9.15 9.15 0 0 0 ${L - 16.5} ${W / 2 + 9.16}`} />
        <path d={`M 0 0.8 A 0.8 0.8 0 0 0 0.8 0`} />
        <path d={`M ${L - 0.8} 0 A 0.8 0.8 0 0 1 ${L} 0.8`} />
        <path d={`M 0 ${W - 0.8} A 0.8 0.8 0 0 1 0.8 ${W}`} />
        <path d={`M ${L - 0.8} ${W} A 0.8 0.8 0 0 0 ${L} ${W - 0.8}`} />
      </g>

      {mode === "heat" &&
        shown.map((t) =>
          t.heatmap.flatMap((row, iy) =>
            row.map((v, ix) => {
              if (v < 0.08) return null;
              const [r, g, b] = hexToRgb(t.colour);
              return (
                <rect
                  key={`${t.id}-${ix}-${iy}`}
                  x={(ix * L) / row.length}
                  y={(iy * W) / t.heatmap.length}
                  width={L / row.length}
                  height={W / t.heatmap.length}
                  fill={`rgb(${r},${g},${b})`}
                  opacity={0.06 + v * 0.62}
                />
              );
            })
          )
        )}

      {mode === "positions" &&
        shown.map((t) => {
          const [r, g, b] = hexToRgb(t.colour);
          return (
            <g key={t.id}>
              {t.network.edges.map((e, i) => {
                const a = t.network.nodes.find((n) => n.id === e.from);
                const c = t.network.nodes.find((n) => n.id === e.to);
                if (!a || !c) return null;
                return (
                  <line
                    key={i}
                    x1={a.x}
                    y1={a.y}
                    x2={c.x}
                    y2={c.y}
                    stroke={`rgb(${r},${g},${b})`}
                    strokeWidth={0.18 + Math.min(0.5, e.count * 0.18)}
                    opacity={0.35}
                  />
                );
              })}
              {t.avg_positions.map((p) => {
                const isSel = selectedPlayer === p.track_id;
                return (
                  <g key={p.track_id}>
                    <circle
                      cx={p.x}
                      cy={p.y}
                      r={isSel ? 2.6 : 1.75}
                      fill={`url(#glow-${t.id})`}
                      stroke={isSel ? "#fff" : `rgba(${r},${g},${b},0.9)`}
                      strokeWidth={isSel ? 0.4 : 0.25}
                    />
                    <text
                      x={p.x}
                      y={p.y + 0.55}
                      textAnchor="middle"
                      fontSize={p.track_id >= 100 ? 1.05 : 1.5}
                      fontWeight={700}
                      fill="#04140d"
                    >
                      {p.track_id}
                    </text>
                  </g>
                );
              })}
            </g>
          );
        })}

      <text x={L - 1} y={W - 1.4} textAnchor="end" fontSize={1.5} fill="rgba(255,255,255,0.28)">
        attack →
      </text>
    </svg>
  );
}

export function Heatmap({ grid, colour }: { grid: number[][]; colour: string }) {
  const [r, g, b] = hexToRgb(colour);
  return (
    <svg className="pitch" viewBox={`0 0 ${L} ${W}`} role="img" aria-label="Player heatmap">
      <defs>
        <linearGradient id="grass-heat" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#123d27" />
          <stop offset="100%" stopColor="#0a2417" />
        </linearGradient>
      </defs>
      <rect x={0} y={0} width={L} height={W} fill="url(#grass-heat)" />
      <g fill="none" stroke="rgba(255,255,255,0.16)" strokeWidth={0.2}>
        <rect x={0} y={0} width={L} height={W} />
        <line x1={L / 2} y1={0} x2={L / 2} y2={W} />
        <circle cx={L / 2} cy={W / 2} r={9.15} />
        <rect x={0} y={W / 2 - 20.16} width={16.5} height={40.32} />
        <rect x={L - 16.5} y={W / 2 - 20.16} width={16.5} height={40.32} />
      </g>
      {grid.flatMap((row, iy) =>
        row.map((v, ix) => {
          if (v < 0.05) return null;
          return (
            <rect
              key={`${ix}-${iy}`}
              x={(ix * L) / row.length}
              y={(iy * W) / grid.length}
              width={L / row.length}
              height={W / grid.length}
              fill={`rgb(${r},${g},${b})`}
              opacity={0.08 + v * 0.7}
            />
          );
        })
      )}
    </svg>
  );
}
