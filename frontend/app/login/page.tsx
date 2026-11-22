"use client";

import { useState } from "react";

export default function Login() {
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: f.get("username"), password: f.get("password") }),
    });
    if (res.ok) window.location.href = "/";
    else setError(res.status === 401 ? "帳號或密碼錯誤" : `登入失敗（HTTP ${res.status}）`);
  }

  return (
    <main>
      <form className="card" onSubmit={submit} style={{ margin: "10vh auto", maxWidth: 360 }}>
        <h1 style={{ fontSize: 20 }}>challsmith 登入</h1>
        <label htmlFor="u">帳號</label>
        <input id="u" name="username" autoComplete="username" required />
        <label htmlFor="p">密碼</label>
        <input id="p" name="password" type="password" autoComplete="current-password" required />
        {error && <div className="error">{error}</div>}
        <p>
          <button className="primary">登入</button>
        </p>
      </form>
    </main>
  );
}
