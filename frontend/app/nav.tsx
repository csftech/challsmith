import Link from "next/link";

import { logout } from "@/lib/api";

export function Nav() {
  return (
    <>
      <Link className="btn" href="/">題目</Link>
      <Link className="btn" href="/sync">同步</Link>
      <Link className="btn" href="/cleanup">發佈前清理</Link>
      <button onClick={logout}>登出</button>
    </>
  );
}
