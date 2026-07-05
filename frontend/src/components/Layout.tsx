import { NavLink, Outlet } from "react-router-dom";

const NAV = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/earnings", label: "Earnings" },
  { to: "/macro", label: "Macro" },
  { to: "/bonds", label: "Bonds" },
];

export default function Layout() {
  return (
    <div className="min-h-screen flex">
      <aside className="w-56 bg-slate-900 text-slate-100 p-4 flex flex-col gap-1">
        <div className="text-xl font-bold mb-4 px-2">market_data</div>
        {NAV.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            end={n.end}
            className={({ isActive }) =>
              `px-3 py-2 rounded text-sm ${
                isActive
                  ? "bg-slate-700 text-white"
                  : "text-slate-300 hover:bg-slate-800"
              }`
            }
          >
            {n.label}
          </NavLink>
        ))}
        <div className="mt-auto text-xs text-slate-500 px-2">
          Ticker search:
          <Search />
        </div>
      </aside>
      <main className="flex-1 p-6 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}

import { useNavigate } from "react-router-dom";
import { useState } from "react";

function Search() {
  const [q, setQ] = useState("");
  const nav = useNavigate();
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (q.trim()) nav(`/ticker/${q.trim().toUpperCase()}`);
      }}
    >
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="AAPL"
        className="mt-1 w-full px-2 py-1 rounded bg-slate-800 text-slate-100 text-sm"
      />
    </form>
  );
}
