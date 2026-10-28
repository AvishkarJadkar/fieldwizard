import { useEffect, useMemo, useRef, useState } from "react";
import { api, fmtTime } from "../lib/api";
import type { Result, Tracks } from "../lib/types";

export function VideoStage({
  matchId,
  result,
  tracks,
  seek,
}: {
  matchId: string;
  result: Result;
  tracks: Tracks | null;
  seek: { t: number; k: number } | null;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>(0);
  const [showBoxes, setShowBoxes] = useState(true);
  const [showBall, setShowBall] = useState(true);
  const [time, setTime] = useState(0);

  const colours = useMemo(
    () => new Map(result.teams.map((t) => [t.id, t.colour])),
    [result.teams]
  );

  useEffect(() => {
    if (!seek) return;
    const v = videoRef.current;
    if (!v) return;
    v.currentTime = Math.max(0, Math.min(seek.t, result.video.duration || seek.t));
    v.play().catch(() => undefined);
  }, [seek, result.video.duration]);

  useEffect(() => {
    const v = videoRef.current;
    const c = canvasRef.current;
    if (!v || !c) return;

    const draw = () => {
      const w = c.clientWidth;
      const h = c.clientHeight;
      if (c.width !== w || c.height !== h) {
        c.width = w;
        c.height = h;
      }
      const ctx = c.getContext("2d");
      if (!ctx) return;
      ctx.clearRect(0, 0, w, h);

      if (!tracks || !tracks.frames.length) return;
      const idx = Math.min(
        tracks.frames.length - 1,
        Math.max(0, Math.round(v.currentTime * tracks.fps))
      );
      const frame = tracks.frames[idx];
      if (!frame) return;

      const vw = v.videoWidth || result.video.width;
      const vh = v.videoHeight || result.video.height;
      const scale = Math.min(w / vw, h / vh);
      const ox = (w - vw * scale) / 2;
      const oy = (h - vh * scale) / 2;

      if (showBoxes) {
        for (const p of frame.p) {
          const [id, team, x1, y1, x2, y2] = p;
          const colour = colours.get(team) ?? "#94a3b8";
          const bx = ox + x1 * vw * scale;
          const by = oy + y1 * vh * scale;
          const bw = (x2 - x1) * vw * scale;
          const bh = (y2 - y1) * vh * scale;
          ctx.strokeStyle = colour;
          ctx.lineWidth = 1.6;
          ctx.strokeRect(bx, by, bw, bh);
          const label = String(id);
          ctx.font = "600 10px Inter, system-ui, sans-serif";
          const tw = ctx.measureText(label).width + 8;
          ctx.fillStyle = colour;
          ctx.globalAlpha = 0.92;
          ctx.fillRect(bx, Math.max(0, by - 14), tw, 13);
          ctx.globalAlpha = 1;
          ctx.fillStyle = "#06110d";
          ctx.fillText(label, bx + 4, Math.max(10, by - 4));
        }
      }

      if (showBall && frame.b) {
        const bx = ox + frame.b[0] * vw * scale;
        const by = oy + frame.b[1] * vh * scale;
        ctx.beginPath();
        ctx.arc(bx, by, 5, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(255,255,255,0.92)";
        ctx.fill();
        ctx.beginPath();
        ctx.arc(bx, by, 9, 0, Math.PI * 2);
        ctx.strokeStyle = "rgba(255,255,255,0.5)";
        ctx.lineWidth = 1.4;
        ctx.stroke();
      }
    };

    const loop = () => {
      draw();
      rafRef.current = requestAnimationFrame(loop);
    };

    if (!v.paused) loop();
    else draw();

    const onPlay = () => {
      cancelAnimationFrame(rafRef.current);
      loop();
    };
    const onStop = () => {
      cancelAnimationFrame(rafRef.current);
      draw();
    };

    v.addEventListener("play", onPlay);
    v.addEventListener("pause", onStop);
    v.addEventListener("seeked", draw);
    v.addEventListener("loadeddata", draw);
    window.addEventListener("resize", draw);
    return () => {
      cancelAnimationFrame(rafRef.current);
      v.removeEventListener("play", onPlay);
      v.removeEventListener("pause", onStop);
      v.removeEventListener("seeked", draw);
      v.removeEventListener("loadeddata", draw);
      window.removeEventListener("resize", draw);
    };
  }, [tracks, showBoxes, showBall, result.video.width, result.video.height, colours]);

  return (
    <div>
      <div className="stage">
        <video ref={videoRef} src={api.videoUrl(matchId)} poster={api.thumbUrl(matchId)} controls playsInline preload="metadata" onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)} />
        <canvas ref={canvasRef} />
        {!tracks && <div className="stage-empty">Tracking overlay loads with the analysis.</div>}
      </div>
      <div className="stage-bar">
        <span className="timecode">
          {fmtTime(time)} / {fmtTime(result.video.duration)}
        </span>
        <span className="dim" style={{ fontSize: 11 }}>
          {result.video.width}×{result.video.height} · {result.video.fps} fps analysis
        </span>
        <span style={{ flex: 1 }} />
        <div className="seg">
          <button className={showBoxes ? "on" : ""} onClick={() => setShowBoxes((v) => !v)}>
            Players
          </button>
          <button className={showBall ? "on" : ""} onClick={() => setShowBall((v) => !v)}>
            Ball
          </button>
        </div>
      </div>
    </div>
  );
}
