import { useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fmtTime } from "../lib/api";
import type { Result, Tracks } from "../lib/types";
import { Pitch } from "../components/Pitch";
import { VideoStage } from "../components/VideoStage";

function Kpi({ label, value, unit, foot }: { label: string; value: string; unit?: string; foot?: string }) {
  return (
    <div className="kpi">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">
        {value}
        {unit && <span className="kpi-unit">{unit}</span>}
      </div>
      {foot && <div className="kpi-foot">{foot}</div>}
    </div>
  );
}

export function Overview({
  matchId,
  result,
  tracks,
  seek,
  onSeek,
}: {
  matchId: string;
  result: Result;
  tracks: Tracks | null;
  seek: { t: number; k: number } | null;
  onSeek: (t: number) => void;
}) {
  const [pitchMode, setPitchMode] = useState<"positions" | "heat">("positions");
  const [teamFilter, setTeamFilter] = useState<number | null>(null);

  const momentum = useMemo(
    () =>
      result.momentum.map((m) => ({
        t: m.t,
        up: m.v > 0 ? m.v : 0,
        down: m.v < 0 ? m.v : 0,
        v: m.v,
      })),
    [result.momentum]
  );

  const a = result.teams[0];
  const b = result.teams[1];
  const km = (result.totals.distance_m / 1000).toFixed(1);

  return (
    <div className="grid" style={{ gap: 18 }}>
      <div className="kpi-grid">
        <Kpi
          label="Passes"
          value={String(result.totals.passes)}
          foot={`${a.passes} · ${b.passes} by team`}
        />
        <Kpi
          label="Turnovers"
          value={String(result.totals.turnovers)}
          foot={`${a.turnovers} · ${b.turnovers} by team`}
        />
        <Kpi label="Distance covered" value={km} unit="km" foot="sum of tracked players" />
        <Kpi
          label="Ball detection"
          value={String(Math.round(result.coverage.ball_detected_rate ?? result.coverage.ball_rate))}
          unit="%"
          foot={`${result.coverage.tracks_used}/${result.coverage.tracks_total} tracks kept`}
        />
      </div>

      <div className="grid cols-2">
        <div className="panel">
          <div className="panel-head">
            <div className="panel-title">Tracking preview</div>
            <span className="pill">
              <span className="dot" style={{ background: "var(--mint)" }} />
              {result.coverage.avg_players} players / frame
            </span>
          </div>
          <div className="panel-body">
            <VideoStage matchId={matchId} result={result} tracks={tracks} seek={seek} />
          </div>
        </div>

        <div className="panel">
          <div className="panel-head">
            <div className="panel-title">Momentum</div>
            <span className="note">possession + territory</span>
          </div>
          <div className="panel-body" style={{ paddingTop: 4 }}>
            <div style={{ height: 232 }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={momentum} margin={{ top: 8, right: 6, bottom: 0, left: -18 }}>
                  <defs>
                    <linearGradient id="mUp" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={a.colour} stopOpacity={0.55} />
                      <stop offset="100%" stopColor={a.colour} stopOpacity={0.02} />
                    </linearGradient>
                    <linearGradient id="mDown" x1="0" y1="1" x2="0" y2="0">
                      <stop offset="0%" stopColor={b.colour} stopOpacity={0.55} />
                      <stop offset="100%" stopColor={b.colour} stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
                  <XAxis
                    dataKey="t"
                    tick={{ fill: "#5f6d82", fontSize: 10 }}
                    tickFormatter={(v) => `${v}s`}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    domain={[-1, 1]}
                    tick={{ fill: "#5f6d82", fontSize: 10 }}
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={(v) => (v > 0 ? "A" : v < 0 ? "B" : "")}
                  />
                  <ReferenceLine y={0} stroke="rgba(255,255,255,0.18)" />
                  <Tooltip
                    contentStyle={{
                      background: "#111823",
                      border: "1px solid rgba(255,255,255,0.12)",
                      borderRadius: 10,
                      fontSize: 12,
                    }}
                    labelFormatter={(v) => `at ${fmtTime(Number(v))}`}
                    formatter={(value: number) => [value.toFixed(2), value >= 0 ? a.name : b.name]}
                  />
                  <Area
                    type="monotone"
                    dataKey="up"
                    stroke={a.colour}
                    strokeWidth={1.6}
                    fill="url(#mUp)"
                    isAnimationActive={false}
                  />
                  <Area
                    type="monotone"
                    dataKey="down"
                    stroke={b.colour}
                    strokeWidth={1.6}
                    fill="url(#mDown)"
                    isAnimationActive={false}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
            <div className="pitch-legend" style={{ paddingTop: 8 }}>
              <span className="legend-item">
                <span className="legend-dot" style={{ background: a.colour }} />
                {a.name} on top
              </span>
              <span className="legend-item">
                <span className="legend-dot" style={{ background: b.colour }} />
                {b.name} on top
              </span>
            </div>
          </div>
        </div>
      </div>

      <div className="grid cols-2">
        <div className="panel">
          <div className="panel-head">
            <div className="panel-title">Pitch map</div>
            <div className="hstack">
              <div className="seg">
                <button className={pitchMode === "positions" ? "on" : ""} onClick={() => setPitchMode("positions")}>
                  Shape
                </button>
                <button className={pitchMode === "heat" ? "on" : ""} onClick={() => setPitchMode("heat")}>
                  Heat
                </button>
              </div>
              <div className="seg">
                <button className={teamFilter === null ? "on" : ""} onClick={() => setTeamFilter(null)}>
                  Both
                </button>
                <button className={teamFilter === 0 ? "on" : ""} onClick={() => setTeamFilter(0)}>
                  A
                </button>
                <button className={teamFilter === 1 ? "on" : ""} onClick={() => setTeamFilter(1)}>
                  B
                </button>
              </div>
            </div>
          </div>
          <div className="panel-body">
            <Pitch teams={result.teams} players={result.players} mode={pitchMode} selectedTeam={teamFilter} />
            <div className="pitch-legend" style={{ paddingTop: 10, paddingBottom: 0 }}>
              <span className="legend-item">
                <span className="legend-dot" style={{ background: a.colour }} />
                {a.name} · {a.possession}%
              </span>
              <span className="legend-item">
                <span className="legend-dot" style={{ background: b.colour }} />
                {b.name} · {b.possession}%
              </span>
              <span className="dim" style={{ marginLeft: "auto", fontSize: 11 }}>
                {result.calibration.quality === "auto" ? "auto-calibrated" : "approximate registration"}
              </span>
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-head">
            <div className="panel-title">Event timeline</div>
            <span className="note">click to jump</span>
          </div>
          <div className="panel-body tight">
            {result.events.length === 0 ? (
              <div className="note" style={{ padding: 14 }}>
                No discrete events were detected in this sample. Longer clips produce more passes and
                turnovers.
              </div>
            ) : (
              <div className="events">
                {result.events.map((e, i) => {
                  const team = result.teams.find((t) => t.id === e.team);
                  return (
                    <button key={i} className="event" onClick={() => onSeek(e.t)}>
                      <span className="event-t">{fmtTime(e.t)}</span>
                      <span className="event-main">
                        <span className="event-team" style={{ background: team?.colour ?? "#94a3b8" }} />
                        <span className="event-type">{e.type}</span>
                        <span className="event-detail">
                          {team?.name}
                          {e.player != null ? ` · #${e.player}` : ""} · {e.detail}
                        </span>
                      </span>
                      <span className="dim" style={{ fontSize: 11 }}>
                        ▸
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
