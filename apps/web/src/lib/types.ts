export type Team = {
  id: number;
  name: string;
  colour: string;
  possession: number;
  players: number;
  passes: number;
  turnovers: number;
  pass_accuracy: number;
  width: number;
  depth: number;
  compactness: number;
  avg_x: number;
  heatmap: number[][];
  avg_positions: { track_id: number; x: number; y: number }[];
  network: {
    nodes: { id: number; x: number; y: number }[];
    edges: { from: number; to: number; count: number }[];
  };
};

export type Player = {
  track_id: number;
  team: number;
  jersey: number | null;
  jersey_conf: number;
  name: string;
  minutes: number;
  distance_m: number;
  distance_per_min: number;
  top_speed: number;
  sprints: number;
  touches: number;
  passes: number;
  turnovers: number;
  avg_x: number;
  avg_y: number;
  heatmap: number[][];
  colour: string;
  crop: string | null;
  rating: number;
};

export type MatchEvent = {
  t: number;
  type: string;
  team: number;
  player: number | null;
  detail: string;
  x: number;
  y: number;
};

export type Finding = {
  title: string;
  detail: string;
  confidence: string;
  evidence: { ts: number; label: string }[];
  recommendation: string;
};

export type Report = {
  headline: string;
  summary: string;
  findings: Finding[];
  training: { focus: string; drill: string; why: string }[];
  limitations: string[];
  engine: string;
};

export type Result = {
  id: string;
  title: string;
  status: string;
  video: {
    duration: number;
    fps: number;
    width: number;
    height: number;
    source_duration: number;
    proxy: string;
    thumb: string | null;
  };
  calibration: { quality: string; coverage: number; clipped: boolean };
  teams: Team[];
  players: Player[];
  events: MatchEvent[];
  momentum: { t: number; v: number }[];
  possession: { a: number; b: number; neutral: number };
  coverage: {
    ball_rate: number;
    ball_detected_rate?: number;
    avg_players: number;
    pitch_points: number;
    tracks_total: number;
    tracks_used: number;
  };
  totals: { passes: number; turnovers: number; shots: number; goals: number; distance_m: number };
  limitations: string[];
  jersey_enabled: boolean;
  report: Report;
};

export type Meta = {
  id: string;
  title: string;
  status: "queued" | "processing" | "done" | "error";
  progress: number;
  message: string;
  created_at: number;
  duration: number | null;
  error: string | null;
  teams?: { id: number; name: string; colour: string; possession: number; passes: number; pass_accuracy: number }[];
  possession?: { a: number; b: number; neutral: number };
  players?: number;
  events?: number;
  report_engine?: string;
  headline?: string;
  thumb?: string | null;
};

export type MatchResponse = { meta: Meta; result: Result | null };

export type Tracks = {
  fps: number;
  width: number;
  height: number;
  frames: { t: number; p: number[][]; b: number[] | null }[];
};
