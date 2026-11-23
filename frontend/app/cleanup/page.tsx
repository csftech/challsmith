"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { Shell } from "@/components/shell";
import { api, jsonInit } from "@/lib/api";
import { useErrorText } from "@/lib/errors";

type Result = {
  instances: number;
  containers: number;
  networks: number;
  users: number;
  sessions: number;
  images: number;
  registry_tags: number;
  reclaimed_bytes: number;
};
type Plan = {
  images: { ref: string; id: string; size: number }[];
  registry: { repo: string; tag: string; digest: string }[];
  kept_images: Record<string, string[]>;
  kept_registry: Record<string, string[]>;
  reclaimable_bytes: number;
};

// reasons come from the api (image_cleanup_service) in English
const REASON = {
  "in use by a container": "inUse",
  "CTFd challenge": "ctfd",
  scenario: "scenario",
  "keep list": "keepList",
  "template base image": "templateBase",
  "outside challsmith/": "outside",
  "same digest as a kept tag": "sameDigest",
} as const;

const mb = (n: number) => `${(n / 1e6).toFixed(0)} MB`;

function Kept({ title, kept }: { title: string; kept: Record<string, string[]> }) {
  const t = useTranslations("cleanup");
  const total = Object.values(kept).reduce((n, refs) => n + refs.length, 0);
  return (
    <details>
      <summary>
        {t("kept", { title, total })}
      </summary>
      <ul>
        {Object.entries(kept).map(([why, refs]) => (
          <li key={why}>
            {t("keptItem", {
              reason: Object.hasOwn(REASON, why) ? t(`reason.${REASON[why as keyof typeof REASON]}`) : why,
              n: refs.length,
              refs: [...refs].sort().join(t("listSep")),
            })}
          </li>
        ))}
      </ul>
    </details>
  );
}

export default function Cleanup() {
  const t = useTranslations("cleanup");
  const nav = useTranslations("nav");
  const common = useTranslations("common");
  const errorText = useErrorText();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [planError, setPlanError] = useState("");

  useEffect(() => {
    api<Plan>("/cleanup/images").then(setPlan, (e) => setPlanError(errorText(e)));
  }, []);

  async function go() {
    setBusy(true);
    setError("");
    try {
      setResult(await api<Result>("/cleanup", jsonInit("POST", { confirm: text })));
      setTimeout(() => {
        window.location.href = "/login";
      }, 3000);
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
    }
  }

  return (
    <Shell title={nav("cleanup")}>
      <div className="card">
        <p>{t("intro")}</p>
        <ul>
          <li>{t("step1")}</li>
          <li>{t("step2")}</li>
          <li>{t("step3")}</li>
          <li>{t("step4")}</li>
        </ul>
        <h2>{t("unused")}</h2>
        {planError && <div className="error">{planError}</div>}
        {!plan && !planError && <p>{common("loading")}</p>}
        {plan && (
          <>
            <p>{t("summary", { images: plan.images.length, size: mb(plan.reclaimable_bytes), tags: plan.registry.length })}</p>
            <ul>
              {plan.images.map((i) => (
                <li key={i.id + i.ref}>
                  <code>{i.ref || t("untagged", { id: i.id.slice(7, 19) })}</code> ({mb(i.size)})
                </li>
              ))}
              {plan.registry.map((g) => (
                <li key={g.repo + g.tag}>
                  {t("registry")}<code>{`${g.repo}:${g.tag}`}</code>
                </li>
              ))}
            </ul>
            <Kept title={t("keptImages")} kept={plan.kept_images} />
            <Kept title={t("keptTags")} kept={plan.kept_registry} />
          </>
        )}
        <label htmlFor="confirm">{t("confirm")}</label>
        <div className="row">
          <input id="confirm" value={text} autoComplete="off" onChange={(e) => setText(e.target.value)} />
          <button className="danger" onClick={go} disabled={busy || text !== "CLEANUP"}>
            {t("run")}
          </button>
        </div>
        {error && <div className="error">{error}</div>}
        {result && (
          <p>
            {t("done", {
              instances: result.instances,
              containers: result.containers,
              networks: result.networks,
              users: result.users,
              sessions: result.sessions,
              images: result.images,
              tags: result.registry_tags,
              size: mb(result.reclaimed_bytes),
            })}
          </p>
        )}
      </div>
    </Shell>
  );
}
