import type { Player, Result } from "../lib/types";
import { PlayerCard } from "../components/PlayerCard";

function TeamPanel({ team, players }: { team: Result["teams"][number]; players: Player[] }) {
  const rows: [string, string][] = [
    ["Possession", `${team.possession}%`],
    ["Passes", String(team.passes)],
    ["Pass accuracy", `${team.pass_accuracy}%`],
    ["Turnovers", String(team.turnovers)],
    ["Players tracked", String(team.players)],
  ];
  return (
    <div className="panel" style={{ borderTop: `2px solid ${team.colour}` }}>
      <div className="panel-head" style={{ alignItems: "flex-start" }}>
        <div>
          <div className="hstack" style={{ gap: 9 }}>
            <span className="hero-swatch" style={{ background: team.colour, width: 22, height: 22, borderRadius: 7 }} />
            <span style={{ fontSize: 16, fontWeight: 750, letterSpacing: "-0.02em" }}>{team.name}</span>
          </div>
          <div className="dim" style={{ fontSize: 11, marginTop: 5, letterSpacing: "0.05em", textTransform: "uppercase", fontWeight: 600 }}>
            {players.length} in squad list
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 26, fontWeight: 780, letterSpacing: "-0.04em", fontVariantNumeric: "tabular-nums" }}>
            {team.possession}
            <span style={{ fontSize: 13, color: "var(--muted)" }}>%</span>
          </div>
          <div className="kpi-label" style={{ fontSize: 9 }}>possession</div>
        </div>
      </div>
      <div className="panel-body">
        <div className="grid" style={{ gridTemplateColumns: "repeat(2, 1fr)", gap: 9 }}>
          {rows.slice(1).map(([k, v]) => (
            <div
              key={k}
              style={{
                border: "1px solid var(--line)",
                borderRadius: 11,
                padding: "10px 12px",
                background: "rgba(255,255,255,0.02)",
              }}
            >
              <div className="kpi-label" style={{ fontSize: 9 }}>{k}</div>
              <div style={{ fontSize: 17, fontWeight: 720, letterSpacing: "-0.03em", marginTop: 3 }}>{v}</div>
            </div>
          ))}
        </div>
        <div className="grid" style={{ gridTemplateColumns: "repeat(3, 1fr)", gap: 9, marginTop: 9 }}>
          {[
            ["Width", `${team.width} m`],
            ["Depth", `${team.depth} m`],
            ["Compact", `${team.compactness} m`],
          ].map(([k, v]) => (
            <div key={k}>
              <div className="kpi-label" style={{ fontSize: 9 }}>{k}</div>
              <div style={{ fontSize: 13.5, fontWeight: 650, marginTop: 3 }}>{v}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function CompareRow({
  label,
  a,
  b,
  aColour,
  bColour,
  unit,
}: {
  label: string;
  a: number;
  b: number;
  aColour: string;
  bColour: string;
  unit: string;
}) {
  const max = Math.max(a, b, 0.001);
  return (
    <div style={{ marginBottom: 14 }}>
      <div className="hstack" style={{ justifyContent: "space-between", marginBottom: 6 }}>
        <span className="kpi-label">{label}</span>
        <span className="dim" style={{ fontSize: 11 }}>
          {a.toFixed(1)} {unit} vs {b.toFixed(1)} {unit}
        </span>
      </div>
      <div className="possbar" style={{ height: 7, marginTop: 0 }}>
        <span style={{ width: `${(a / max) * 100}%`, background: aColour }} />
        <span style={{ width: `${(b / max) * 100}%`, background: bColour }} />
      </div>
    </div>
  );
}

export function Squad({
  matchId,
  result,
  selected,
  onSelect,
}: {
  matchId: string;
  result: Result;
  selected: number | null;
  onSelect: (id: number) => void;
}) {
  const a = result.teams[0];
  const b = result.teams[1];

  return (
    <div className="grid" style={{ gap: 18 }}>
      <div className="grid cols-2">
        <TeamPanel team={a} players={result.players.filter((p) => p.team === 0)} />
        <TeamPanel team={b} players={result.players.filter((p) => p.team === 1)} />
      </div>

      <div className="panel">
        <div className="panel-head">
          <div className="panel-title">Shape comparison</div>
          <span className="note">pitch-space, approximate when calibration is partial</span>
        </div>
        <div className="panel-body">
          <CompareRow label="Team width (spread across the pitch)" a={a.width} b={b.width} aColour={a.colour} bColour={b.colour} unit="m" />
          <CompareRow label="Team depth (length between units)" a={a.depth} b={b.depth} aColour={a.colour} bColour={b.colour} unit="m" />
          <CompareRow label="Compactness (distance to centroid)" a={a.compactness} b={b.compactness} aColour={a.colour} bColour={b.colour} unit="m" />
          <CompareRow label="Average x position (0 = own goal)" a={a.avg_x} b={b.avg_x} aColour={a.colour} bColour={b.colour} unit="m" />
        </div>
      </div>

      {[a, b].map((team) => {
        const players = result.players.filter((p) => p.team === team.id);
        if (!players.length) return null;
        return (
          <div key={team.id}>
            <div className="hstack" style={{ marginBottom: 12 }}>
              <span className="legend-dot" style={{ background: team.colour, width: 10, height: 10 }} />
              <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: "0.02em" }}>{team.name}</span>
              <span className="dim" style={{ fontSize: 11.5 }}>
                {players.length} tracked · sorted by rating
              </span>
            </div>
            <div className="player-grid">
              {players.map((p) => (
                <PlayerCard
                  key={p.track_id}
                  matchId={matchId}
                  player={p}
                  team={team}
                  selected={selected === p.track_id}
                  onSelect={onSelect}
                />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
