import type { MatchResponse, Meta, Tracks } from "./types";

const base = "";

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(base + url, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* keep statusText */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  list: () => json<Meta[]>("/api/matches"),
  get: (id: string) => json<MatchResponse>(`/api/matches/${id}`),
  status: (id: string) => json<Meta>(`/api/matches/${id}/status`),
  tracks: (id: string) => json<Tracks>(`/api/matches/${id}/tracks`),
  remove: (id: string) => json<{ deleted: string }>(`/api/matches/${id}`, { method: "DELETE" }),
  health: () => json<{ ok: boolean; llm: boolean; jersey: boolean; queued: number }>("/api/health"),
  upload: async (file: File, title: string, opts: { start: number; max: number; fps: number }) => {
    const form = new FormData();
    form.append("file", file);
    form.append("title", title);
    form.append("start_seconds", String(opts.start));
    form.append("max_seconds", String(opts.max));
    form.append("fps", String(opts.fps));
    return json<Meta>("/api/matches", { method: "POST", body: form });
  },
  videoUrl: (id: string) => `${base}/api/matches/${id}/video`,
  thumbUrl: (id: string) => `${base}/api/matches/${id}/thumb`,
  cropUrl: (id: string, name: string) => `${base}/api/matches/${id}/crops/${name}`,
};

export function fmtTime(seconds: number): string {
  const s = Math.max(0, seconds);
  const m = Math.floor(s / 60);
  const rest = Math.floor(s % 60);
  return `${m}:${rest.toString().padStart(2, "0")}`;
}

export function fmtDate(ts: number): string {
  return new Date(ts * 1000).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
