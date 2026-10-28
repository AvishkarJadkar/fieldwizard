import { useMemo, useState } from "react";
import { api } from "../lib/api";
import type { Player, Result } from "../lib/types";
import { Heatmap } from "../components/Pitch";

type SortKey = "rating" | "distance_m" | "top_speed" | "touches" | "sprints";

const SORTS: { key: SortKey; label: string }[] = [
  { key: "rating", label: "Rating" },
  { key: "distance_m", label: "Distance" },
  { key: "top_speed", label: "Top speed" },
  { key: "touches", label: "Touches" },
  { key: "sprints", label: "Sprints" },
];

function Detail({ player, team, matchId }: { player: Player; team: Result["teams"][number] | undefined; matchId: string }) {
  const stats: [string, string][] = [
    ["Minutes tracked", player.minutes.toFixed(1)],
    ["Distance", `${player.distance_m.toFixed(0)} m`],
    ["Distance / min", `${player.distance_per_min.toFixed(1)} m`],
    ["Top speed", `${player.top_speed.toFixed(1)} km/h`],
    ["Sprints", String(player.sprints)],
    ["Touches", String(player.touches)],
    ["Passes", String(player.passes)],
    ["Possession lost", String(player.turnovers)],
  ];

  return (
    <div className="panel">
      <div className="panel-head">
        <div className="panel-title">Player profile</div>
        <span className="badge" style={{ color: team?.colour, borderColor: `${team?.colour}55` }}>
          {team?.name ?? "—"}
        </span>
      </div>
      <div className="panel-body">
        <div className="hstack" style={{ gap: 14, marginBottom: 16 }}>
          <div className="pc-avatar" style={{ width: 62, height: 62, borderRadius: 16 }}>
            {player.crop ? (
              <img src={api.cropUrl(matchId, player.crop)} alt={player.name} />
            ) : (
              <span style={{ fontSize: 15, fontWeight: 750, color: "var(--muted)" }}>
                {player.jersey ? `#${player.jersey}` : player.track_id}
              </span>
            )}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 19, fontWeight: 760, letterSpacing: "-0.03em" }}>{player.name}</div>
            <div className="dim" style={{ fontSize: 11.5, marginTop: 3 }}>
              Track ID {player.track_id} · avg position x {player.avg_x.toFixed(0)} m, y {player.avg_y.toFixed(0)} m
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div
              style={{
                fontSize: 34,
                fontWeight: 790,
                letterSpacing: "-0.05em",
                lineHeight: 1,
                color: player.rating >= 7.5 ? "var(--mint)" : player.rating >= 6.5 ? "var(--text)" : "var(--amber)",
              }}
            >
              {player.rating.toFixed(1)}
            </div>
            <div className="kpi-label" style={{ fontSize: 9 }}>rating</div>
          </div>
        </div>

        <div className="grid" style={{ gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 16 }}>
          {stats.map(([k, v]) => (
            <div key={k}>
              <div className="kpi-label" style={{ fontSize: 8.5 }}>{k}</div>
              <div style={{ fontSize: 13, fontWeight: 680, marginTop: 3, fontVariantNumeric: "tabular-nums" }}>{v}</div>
            </div>
          ))}
        </div>

        <Heatmap grid={player.heatmap} colour={player.colour} />
        <div className="note" style={{ marginTop: 8 }}>
          Heatmap is projected through the pitch homography; treat the edges as approximate.
        </div>
      </div>
    </div>
  );
}

export function Players({
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
  const [sort, setSort] = useState<SortKey>("rating");
  const [teamFilter, setTeamFilter] = useState<number | null>(null);

  const rows = useMemo(() => {
    const filtered = result.players.filter((p) => teamFilter === null || p.team === teamFilter);
    return [...filtered].sort((x, y) => (y[sort] as number) - (x[sort] as number));
  }, [result.players, sort, teamFilter]);

  const active = result.players.find((p) => p.track_id === selected) ?? rows[0];
  const activeTeam = result.teams.find((t) => t.id === active?.team);

  return (
    <div className="grid cols-2">
      <div className="panel">
        <div className="panel-head">
          <div className="panel-title">Player metrics</div>
          <div className="hstack">
            <div className="seg">
              <button className={teamFilter === null ? "on" : ""} onClick={() => setTeamFilter(null)}>
                All
              </button>
              <button className={teamFilter === 0 ? "on" : ""} onClick={() => setTeamFilter(0)}>
                {result.teams[0].name.replace("Team ", "")}
              </button>
              <button className={teamFilter === 1 ? "on" : ""} onClick={() => setTeamFilter(1)}>
                {result.teams[1].name.replace("Team ", "")}
              </button>
            </div>
          </div>
        </div>
        <div className="panel-body">
          <div className="hstack" style={{ marginBottom: 10 }}>
            <span className="kpi-label">Sort</span>
            <div className="seg">
              {SORTS.map((s) => (
                <button key={s.key} className={sort === s.key ? "on" : ""} onClick={() => setSort(s.key)}>
                  {s.label}
                </button>
              ))}
            </div>
          </div>
          <div className="table-wrap" style={{ maxHeight: 520 }}>
            <table className="stats">
              <thead>
                <tr>
                  <th>Player</th>
                  <th>Rt</th>
                  <th>Min</th>
                  <th>Dist</th>
                  <th>m/min</th>
                  <th>km/h</th>
                  <th>Spr</th>
                  <th>Tch</th>
                  <th>Pass</th>
                  <th>Lost</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => {
                  const team = result.teams.find((t) => t.id === p.team);
                  return (
                    <tr
                      key={p.track_id}
                      className={active?.track_id === p.track_id ? "sel" : ""}
                      onClick={() => onSelect(p.track_id)}
                    >
                      <td>
                        <span className="t-name">
                          <span className="t-dot" style={{ background: team?.colour ?? "#94a3b8" }} />
                          {p.jersey ? `#${p.jersey}` : `ID ${p.track_id}`}
                        </span>
                      </td>
                      <td style={{ fontWeight: 700 }}>{p.rating.toFixed(1)}</td>
                      <td>{p.minutes.toFixed(1)}</td>
                      <td>{p.distance_m.toFixed(0)}</td>
                      <td>{p.distance_per_min.toFixed(0)}</td>
                      <td>{p.top_speed.toFixed(0)}</td>
                      <td>{p.sprints}</td>
                      <td>{p.touches}</td>
                      <td>{p.passes}</td>
                      <td>{p.turnovers}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="note" style={{ marginTop: 10 }}>
            Distances use player pixel height (1.8 m reference) on a stabilised image, so camera pan does not
            inflate movement.
          </div>
        </div>
      </div>

      {active ? <Detail player={active} team={activeTeam} matchId={matchId} /> : <div className="panel" />}
    </div>
  );
}
