import { useCallback, useEffect, useRef, useState } from "react";
import { api, fmtDate, fmtTime } from "./lib/api";
import type { MatchResponse, Meta, Result, Tracks } from "./lib/types";
import { Overview } from "./views/Overview";
import { Players } from "./views/Players";
import { ReportView } from "./views/Report";
import { Squad } from "./views/Squad";

type Tab = "match" | "squad" | "players" | "report";

const TABS: { id: Tab; label: string }[] = [
  { id: "match", label: "Match" },
  { id: "squad", label: "Squad" },
  { id: "players", label: "Players" },
  { id: "report", label: "Report" },
];

function Logo() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 2.4 20.4 7v10L12 21.6 3.6 17V7L12 2.4Z" stroke="#04140d" strokeWidth="1.7" strokeLinejoin="round" />
      <path d="M12 7.2 15.8 9.4v4.4L12 16l-3.8-2.2V9.4L12 7.2Z" fill="#04140d" opacity="0.9" />
    </svg>
  );
}

function UploadModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (m: Meta) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [start, setStart] = useState(0);
  const [max, setMax] = useState(20);
  const [fps, setFps] = useState(15);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const submit = async () => {
    if (!file) {
      setError("Choose a video file first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const meta = await api.upload(file, title || file.name.replace(/\.[^.]+$/, ""), {
        start,
        max,
        fps,
      });
      onCreated(meta);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && !busy && onClose()}>
      <div className="modal">
        <h3>New analysis</h3>
        <p className="sub">
          Upload match footage. For a full match, raise the window; the first pass runs on CPU, so start
          with a short clip to validate the camera.
        </p>

        <div
          className={`drop${over ? " over" : ""}`}
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setOver(false);
            const f = e.dataTransfer.files?.[0];
            if (f) {
              setFile(f);
              if (!title) setTitle(f.name.replace(/\.[^.]+$/, ""));
            }
          }}
        >
          <b>{file ? file.name : "Drop a video or click to browse"}</b>
          <span>
            {file
              ? `${(file.size / (1024 * 1024)).toFixed(1)} MB`
              : "mp4, mov, mkv, webm · wide-angle footage works best"}
          </span>
          <input
            ref={inputRef}
            type="file"
            accept="video/*"
            hidden
            onChange={(e) => {
              const f = e.target.files?.[0] ?? null;
              setFile(f);
              if (f && !title) setTitle(f.name.replace(/\.[^.]+$/, ""));
            }}
          />
        </div>

        <div className="field">
          <label>Match title</label>
          <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Sunday League — Pitch 3" />
        </div>

        <div className="row-3">
          <div className="field">
            <label>Start (s)</label>
            <input type="number" min={0} value={start} onChange={(e) => setStart(Number(e.target.value))} />
          </div>
          <div className="field">
            <label>Window (s)</label>
            <input type="number" min={1} max={600} value={max} onChange={(e) => setMax(Number(e.target.value))} />
          </div>
          <div className="field">
            <label>Analysis fps</label>
            <input type="number" min={5} max={30} value={fps} onChange={(e) => setFps(Number(e.target.value))} />
          </div>
        </div>

        {error && <div className="error-box" style={{ maxHeight: 120 }}>{error}</div>}

        <div className="modal-actions">
          <button className="btn btn-ghost" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="btn btn-primary" onClick={submit} disabled={busy || !file}>
            {busy ? (
              <>
                <span className="spin" /> Uploading…
              </>
            ) : (
              "Start analysis"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

function ProgressPanel({ meta }: { meta: Meta }) {
  return (
    <div className="panel">
      <div className="panel-head">
        <div className="panel-title">Analysing footage</div>
        <span className="pill warn">
          <span className="dot" />
          {meta.status}
        </span>
      </div>
      <div className="panel-body">
        <div className="hstack" style={{ justifyContent: "space-between", marginBottom: 10 }}>
          <span style={{ fontSize: 13, fontWeight: 600 }}>{meta.message}</span>
          <span className="mono" style={{ fontSize: 13, color: "var(--muted)" }}>
            {meta.progress}%
          </span>
        </div>
        <div className={`progress${meta.progress === 0 ? " indeterminate" : ""}`}>
          <span style={{ width: `${Math.max(3, meta.progress)}%` }} />
        </div>
        <div className="note" style={{ marginTop: 14 }}>
          Tracking, kit clustering, pitch registration and the coaching report run in sequence. A 20-second
          clip takes a few minutes on CPU; this page updates automatically.
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [matches, setMatches] = useState<Meta[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [data, setData] = useState<MatchResponse | null>(null);
  const [tracks, setTracks] = useState<Tracks | null>(null);
  const [tab, setTab] = useState<Tab>("match");
  const [selectedPlayer, setSelectedPlayer] = useState<number | null>(null);
  const [seek, setSeek] = useState<{ t: number; k: number } | null>(null);
  const [showUpload, setShowUpload] = useState(false);
  const [health, setHealth] = useState<{ llm: boolean; jersey: boolean; queued: number } | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshList = useCallback(async () => {
    try {
      const list = await api.list();
      setMatches(list);
      setSelectedId((cur) => cur ?? list[0]?.id ?? null);
      return list;
    } catch {
      return [];
    }
  }, []);

  useEffect(() => {
    api.health().then(setHealth).catch(() => undefined);
    refreshList().finally(() => setLoading(false));
  }, [refreshList]);

  useEffect(() => {
    if (!selectedId) {
      setData(null);
      setTracks(null);
      return;
    }
    let alive = true;
    let timer: number | undefined;

    const load = async () => {
      try {
        const res = await api.get(selectedId);
        if (!alive) return;
        setData(res);
        if (res.meta.status === "done" && res.result) {
          const t = await api.tracks(selectedId).catch(() => null);
          if (!alive) return;
          setTracks(t);
          setSelectedPlayer((prev) => prev ?? res.result?.players[0]?.track_id ?? null);
          refreshList();
        } else if (res.meta.status === "queued" || res.meta.status === "processing") {
          timer = window.setTimeout(load, 2000);
        }
      } catch {
        if (alive) timer = window.setTimeout(load, 4000);
      }
    };

    setLoading(true);
    load().finally(() => alive && setLoading(false));
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [selectedId, refreshList]);

  const onSeek = useCallback((t: number) => {
    setTab("match");
    setSeek({ t, k: Date.now() });
  }, []);

  const meta = data?.meta;
  const result: Result | null = data?.result ?? null;

  const statusClass =
    meta?.status === "done" ? "ok" : meta?.status === "error" ? "bad" : meta?.status ? "warn" : "";

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">
            <Logo />
          </div>
          <div>
            <div className="brand-name">FieldWizard</div>
            <div className="brand-sub">Football Intelligence</div>
          </div>
        </div>

        <div className="topbar-spacer" />

        {matches.length > 0 && (
          <select
            className="match-select"
            value={selectedId ?? ""}
            onChange={(e) => {
              setSelectedId(e.target.value);
              setSelectedPlayer(null);
              setTracks(null);
              setTab("match");
            }}
          >
            {matches.map((m) => (
              <option key={m.id} value={m.id}>
                {m.title}
                {m.status === "done" ? "" : ` · ${m.status}`}
              </option>
            ))}
          </select>
        )}

        <span className={`pill ${health?.llm ? "ok" : ""}`} title="Coaching report engine">
          <span className="dot" />
          {health?.llm ? "LLM on" : "Rules engine"}
        </span>

        <button className="btn btn-primary" onClick={() => setShowUpload(true)}>
          + New analysis
        </button>
      </header>

      <main className="shell">
        {loading && !data && (
          <div className="empty">
            <span className="spin" />
            <p>Loading match…</p>
          </div>
        )}

        {!loading && matches.length === 0 && (
          <div className="empty">
            <h2>No matches yet</h2>
            <p>
              Upload a clip to generate tracking, possession, heatmaps and a coaching report. Wide-angle,
              elevated footage gives the best tracking.
            </p>
            <button className="btn btn-primary" onClick={() => setShowUpload(true)}>
              Analyse a clip
            </button>
          </div>
        )}

        {meta && (
          <>
            <section className="hero">
              <div className="hero-top">
                <div style={{ minWidth: 0 }}>
                  <h1 className="hero-title">{meta.title}</h1>
                  <div className="hero-meta">
                    <span className={`pill ${statusClass}`}>
                      <span className="dot" />
                      {meta.status}
                    </span>
                    {result && (
                      <>
                        <span>{fmtTime(result.video.duration)} analysed</span>
                        <span className="dim">·</span>
                        <span>{result.players.length} players</span>
                        <span className="dim">·</span>
                        <span>{result.coverage.tracks_used} tracks</span>
                        <span className="dim">·</span>
                        <span>{result.events.length} events</span>
                      </>
                    )}
                    <span className="dim">·</span>
                    <span>{fmtDate(meta.created_at)}</span>
                  </div>
                </div>
                {result && (
                  <div className="hstack">
                    <span className={`pill ${result.calibration.quality === "auto" ? "ok" : "warn"}`}>
                      <span className="dot" />
                      {result.calibration.quality === "auto" ? "auto-calibrated" : "approx. calibration"}
                    </span>
                    <span className="pill">
                      <span className="dot" />
                      {result.report.engine === "rules" ? "rule report" : "AI report"}
                    </span>
                  </div>
                )}
              </div>

              {result && (
                <>
                  <div className="hero-score">
                    <div className="hero-team" style={{ flex: 1, minWidth: 0 }}>
                      <span className="hero-swatch" style={{ background: result.teams[0].colour }} />
                      <div style={{ minWidth: 0 }}>
                        <div className="hero-team-name">{result.teams[0].name}</div>
                        <div className="hero-team-sub">{result.teams[0].players} players tracked</div>
                      </div>
                    </div>
                    <div className="hstack" style={{ gap: 10, flex: "none" }}>
                      <span className="hero-poss" style={{ color: result.teams[0].colour }}>
                        {result.teams[0].possession}
                        <span style={{ fontSize: 16 }}>%</span>
                      </span>
                      <span className="hero-dash">–</span>
                      <span className="hero-poss" style={{ color: result.teams[1].colour }}>
                        {result.teams[1].possession}
                        <span style={{ fontSize: 16 }}>%</span>
                      </span>
                    </div>
                    <div
                      className="hero-team"
                      style={{ flex: 1, minWidth: 0, justifyContent: "flex-end", textAlign: "right" }}
                    >
                      <span className="hero-swatch" style={{ background: result.teams[1].colour }} />
                      <div style={{ minWidth: 0 }}>
                        <div className="hero-team-name">{result.teams[1].name}</div>
                        <div className="hero-team-sub">{result.teams[1].players} players tracked</div>
                      </div>
                    </div>
                  </div>
                  <div className="possbar">
                    <span style={{ width: `${result.teams[0].possession}%`, background: result.teams[0].colour }} />
                    <span style={{ width: `${result.teams[1].possession}%`, background: result.teams[1].colour }} />
                  </div>
                </>
              )}
            </section>

            {meta.status === "error" && (
              <div className="error-box">{meta.error ?? "Analysis failed."}</div>
            )}

            {(meta.status === "queued" || meta.status === "processing") && <ProgressPanel meta={meta} />}

            {result && (
              <>
                <div className="hstack" style={{ justifyContent: "space-between", marginBottom: 16 }}>
                  <div className="tabs">
                    {TABS.map((t) => (
                      <button
                        key={t.id}
                        className={`tab${tab === t.id ? " active" : ""}`}
                        onClick={() => setTab(t.id)}
                      >
                        {t.label}
                      </button>
                    ))}
                  </div>
                  <span className="note">
                    {result.video.width}×{result.video.height} · {result.video.fps} fps · ball{" "}
                    {Math.round(result.coverage.ball_detected_rate ?? result.coverage.ball_rate)}%
                  </span>
                </div>

                {tab === "match" && (
                  <Overview
                    matchId={meta.id}
                    result={result}
                    tracks={tracks}
                    seek={seek}
                    onSeek={onSeek}
                  />
                )}
                {tab === "squad" && (
                  <Squad
                    matchId={meta.id}
                    result={result}
                    selected={selectedPlayer}
                    onSelect={(id) => {
                      setSelectedPlayer(id);
                      setTab("players");
                    }}
                  />
                )}
                {tab === "players" && (
                  <Players
                    matchId={meta.id}
                    result={result}
                    selected={selectedPlayer}
                    onSelect={setSelectedPlayer}
                  />
                )}
                {tab === "report" && <ReportView result={result} onSeek={onSeek} />}
              </>
            )}
          </>
        )}

        <div className="footer">
          FieldWizard · single-camera tracking, estimates not official statistics
        </div>
      </main>

      {showUpload && (
        <UploadModal
          onClose={() => setShowUpload(false)}
          onCreated={(m) => {
            setShowUpload(false);
            setMatches((prev) => [m, ...prev.filter((x) => x.id !== m.id)]);
            setSelectedId(m.id);
            setData({ meta: m, result: null });
            setTracks(null);
            setSelectedPlayer(null);
            setTab("match");
          }}
        />
      )}
    </div>
  );
}
