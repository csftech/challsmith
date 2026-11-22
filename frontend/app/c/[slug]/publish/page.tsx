"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Nav } from "@/app/nav";
import { api, ApiError } from "@/lib/api";

type Run = { status: "running" | "succeeded" | "failed"; log: string };
const LABEL = { running: "發佈中…", succeeded: "發佈成功", failed: "發佈失敗" };

export default function Publish() {
  const { slug } = useParams<{ slug: string }>();
  const [runId, setRunId] = useState<number | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState("");
  const logRef = useRef<HTMLPreElement>(null);
  const running = runId !== null && (run === null || run.status === "running");

  useEffect(() => {
    if (runId === null) return;
    let stop = false;
    let fails = 0;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const r = await api<Run>(`/publish-runs/${runId}`);
        if (stop) return;
        fails = 0;
        setError("");
        setRun(r);
        if (r.status !== "running") return;
      } catch (e) {
        if (stop) return;
        setError((e as Error).message);
        // 4xx will not fix itself; other errors get a few retries
        if ((e instanceof ApiError && e.status >= 400 && e.status < 500) || ++fails >= 5) return;
      }
      timer = setTimeout(tick, 1000);
    };
    tick();
    return () => { stop = true; clearTimeout(timer); };
  }, [runId]);

  useEffect(() => {
    logRef.current?.scrollTo(0, logRef.current.scrollHeight);
  }, [run?.log]);

  async function start() {
    setError("");
    setRun(null);
    try {
      const r = await api<{ run_id: number }>(`/challenges/${encodeURIComponent(slug)}/publish`, { method: "POST" });
      setRunId(r.run_id);
    } catch (e) {
      // the 409 body carries no run id, so there is nothing to attach to
      setError(e instanceof ApiError && e.status === 409 ? "這題正在發佈中" : (e as Error).message);
    }
  }

  return (
    <>
      <header className="bar">
        <h1>發佈 {slug}</h1>
        <Link className="btn" href={`/c/${slug}`}>回編輯</Link>
        <Nav />
      </header>
      <main>
        <div className="row">
          <button className="primary" onClick={start} disabled={running}>發佈</button>
          {run && <strong>{LABEL[run.status]}</strong>}
        </div>
        {error && <div className="error">{error}</div>}
        {runId !== null && <pre className="log" ref={logRef}>{run?.log ?? ""}</pre>}
      </main>
    </>
  );
}
