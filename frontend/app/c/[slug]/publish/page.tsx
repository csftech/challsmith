"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { Shell } from "@/app/shell";
import { api, ApiError } from "@/lib/api";
import { useErrorText } from "@/lib/errors";

type Run = { status: "running" | "succeeded" | "failed"; log: string };

export default function Publish() {
  const t = useTranslations("publish");
  const errorText = useErrorText();
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
        setError(errorText(e));
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
      setError(e instanceof ApiError && e.status === 409 ? t("alreadyRunning") : errorText(e));
    }
  }

  return (
    <Shell title={t("title", { slug })}>
      <div className="row">
        <Link className="btn" href={`/c/${slug}`}>{t("back")}</Link>
      </div>
      <div className="row">
        <button className="primary" onClick={start} disabled={running}>{t("start")}</button>
        {run && <strong>{t(run.status)}</strong>}
      </div>
      {error && <div className="error">{error}</div>}
      {runId !== null && <pre className="log" ref={logRef}>{run?.log ?? ""}</pre>}
    </Shell>
  );
}
