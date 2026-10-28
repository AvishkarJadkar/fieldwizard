import { api } from "../lib/api";
import type { Player, Team } from "../lib/types";

export function PlayerCard({
  matchId,
  player,
  team,
  selected,
  onSelect,
}: {
  matchId: string;
  player: Player;
  team?: Team;
  selected?: boolean;
  onSelect: (id: number) => void;
}) {
  return (
    <button
      className={`player-card${selected ? " sel" : ""}`}
      style={{ ["--team-colour" as string]: player.colour }}
      onClick={() => onSelect(player.track_id)}
    >
      <div className="pc-top">
        <div className="pc-avatar">
          {player.crop ? (
            <img src={api.cropUrl(matchId, player.crop)} alt={player.name} loading="lazy" />
          ) : (
            <span style={{ fontSize: 12, color: "#5f6d82", fontWeight: 700 }}>{player.track_id}</span>
          )}
        </div>
        <div style={{ minWidth: 0 }}>
          <div className="pc-num">{player.jersey ? `#${player.jersey}` : player.name}</div>
          <div className="pc-team">{team?.name ?? "Unassigned"}</div>
        </div>
        <div className="pc-rating">
          <b style={{ color: player.rating >= 7.5 ? "var(--mint)" : player.rating >= 6.5 ? "var(--text)" : "var(--amber)" }}>
            {player.rating.toFixed(1)}
          </b>
          <span>rating</span>
        </div>
      </div>
      <div className="pc-stats">
        <div className="pc-stat">
          <b>{player.distance_m.toFixed(0)}</b>
          <span>metres</span>
        </div>
        <div className="pc-stat">
          <b>{player.top_speed.toFixed(0)}</b>
          <span>km/h</span>
        </div>
        <div className="pc-stat">
          <b>{player.touches}</b>
          <span>touches</span>
        </div>
      </div>
    </button>
  );
}
