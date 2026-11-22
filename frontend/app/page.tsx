"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Nav } from "./nav";
import { api, type Summary } from "@/lib/api";

const PUBLISH = { draft: "草稿", published: "已發佈", modified: "有未發佈的修改" };
const SYNC = { never: "未同步", synced: "已同步", modified: "有未匯出的修改" };

export default function Home() {
  const [rows, setRows] = useState<Summary[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<{ items: Summary[] }>("/challenges").then((r) => setRows(r.items), (e) => setError(e.message));
  }, []);

  return (
    <>
      <header className="bar">
        <h1>題目清單</h1>
        <Link className="btn primary" href="/new">新增題目</Link>
        <Nav />
      </header>
      <main>
        {error && <div className="error">{error}</div>}
        {rows && (
          <table>
            <thead>
              <tr><th>名稱</th><th>slug</th><th>分類</th><th>發佈狀態</th><th>git 同步</th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.slug}>
                  <td><Link href={`/c/${r.slug}`}>{r.name}</Link></td>
                  <td>{r.slug}</td>
                  <td>{r.category}</td>
                  <td>{PUBLISH[r.publish]}</td>
                  <td>{SYNC[r.sync]}</td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={5}>還沒有題目</td></tr>}
            </tbody>
          </table>
        )}
      </main>
    </>
  );
}
