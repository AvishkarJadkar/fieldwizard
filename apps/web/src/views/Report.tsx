import { fmtTime } from "../lib/api";
import type { Result } from "../lib/types";

export function ReportView({
  result,
  onSeek,
}: {
  result: Result;
  onSeek: (t: number) => void;
}) {
  const report = result.report;

  return (
    <div className="grid" style={{ gap: 18 }}>
      <div className="report-hero">
        <div className="hstack" style={{ marginBottom: 10 }}>
          <span className="pill ok">
            <span className="dot" />
            {report.engine === "rules" ? "Rule-based report" : `${report.engine} coaching report`}
          </span>
          <span className="note">
            {report.engine === "rules"
              ? "Deterministic analysis — add GEMINI_API_KEY for narrative coaching"
              : "Generated from the tracked fact sheet"}
          </span>
        </div>
        <h2 className="report-headline">{report.headline}</h2>
        <p className="report-summary">{report.summary}</p>
      </div>

      <div className="grid cols-2" style={{ alignItems: "start" }}>
        <div>
          <div className="panel-title" style={{ padding: "0 4px 12px" }}>Findings</div>
          {report.findings.map((f, i) => (
            <div className="finding" key={i}>
              <div className="finding-head">
                <span className="finding-title">{f.title}</span>
                <span className={`badge ${f.confidence}`}>{f.confidence} confidence</span>
              </div>
              <p className="finding-detail">{f.detail}</p>
              {f.recommendation && (
                <div className="finding-rec">
                  <b>Coach this:</b> {f.recommendation}
                </div>
              )}
              {f.evidence.length > 0 && (
                <div className="evidence">
                  {f.evidence.map((e, j) => (
                    <button key={j} onClick={() => onSeek(e.ts)}>
                      ▶ {fmtTime(e.ts)} · {e.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>

        <div>
          <div className="panel" style={{ marginBottom: 18 }}>
            <div className="panel-head">
              <div className="panel-title">Training plan</div>
              <span className="note">from this sample</span>
            </div>
            <div className="panel-body">
              {report.training.map((t, i) => (
                <div className="drill" key={i}>
                  <div className="drill-n">{i + 1}</div>
                  <div>
                    <b>{t.focus}</b>
                    <p>
                      <span style={{ color: "var(--text)" }}>{t.drill}</span> — {t.why}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="panel">
            <div className="panel-head">
              <div className="panel-title">Data quality & limitations</div>
              <span
                className={`pill ${result.calibration.quality === "auto" ? "ok" : "warn"}`}
              >
                <span className="dot" />
                {result.calibration.quality}
              </span>
            </div>
            <div className="panel-body">
              <ul className="note" style={{ margin: 0, paddingLeft: 18 }}>
                {result.limitations.map((l, i) => (
                  <li key={i}>{l}</li>
                ))}
              </ul>
              <div
                className="note"
                style={{
                  marginTop: 14,
                  paddingTop: 12,
                  borderTop: "1px solid var(--line)",
                }}
              >
                Calibration coverage {(result.calibration.coverage * 100).toFixed(0)}% of frame ·{" "}
                {result.coverage.tracks_used} of {result.coverage.tracks_total} tracks kept · ball found in{" "}
                {Math.round(result.coverage.ball_detected_rate ?? result.coverage.ball_rate)}% of frames
                {(result.coverage.ball_detected_rate ?? 100) < result.coverage.ball_rate
                  ? ` (path covers ${result.coverage.ball_rate.toFixed(0)}%)`
                  : ""}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
