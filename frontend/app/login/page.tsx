"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Switchers } from "@/app/switchers";
import { ApiError } from "@/lib/api";
import { useErrorText } from "@/lib/errors";

export default function Login() {
  const t = useTranslations();
  const errorText = useErrorText();
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: f.get("username"), password: f.get("password") }),
    });
    if (res.ok) {
      window.location.href = "/";
      return;
    }
    if (res.status === 401) {
      setError(t("login.invalid"));
      return;
    }
    const body = await res.json().catch(() => ({}));
    const fallback = typeof body.detail === "string" ? body.detail : `HTTP ${res.status}`;
    setError(errorText(new ApiError(res.status, fallback, body.detail, body.code)));
  }

  return (
    <main className="login">
      <Switchers />
      <form className="card" onSubmit={submit}>
        <h1><span className="logo">cs</span>{t("login.title")}</h1>
        <label htmlFor="u">{t("login.username")}</label>
        <input id="u" name="username" autoComplete="username" required />
        <label htmlFor="p">{t("login.password")}</label>
        <input id="p" name="password" type="password" autoComplete="current-password" required />
        {error && <div className="error">{error}</div>}
        <button className="primary">{t("login.submit")}</button>
      </form>
    </main>
  );
}
