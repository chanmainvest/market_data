import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import DataTable from "../components/DataTable";

export default function Bonds() {
  const [source, setSource] = useState<"bi" | "finra">("bi");
  const { data } = useQuery({
    queryKey: ["bonds", source],
    queryFn: () => api<{ date: string | null; items: { payload: any }[] }>(
      `/bonds?source=${source}`
    ),
  });
  const items = data?.items ?? [];
  // Flatten a few common payload keys for display.
  const flatRows = items.map((it) => {
    const p = it.payload ?? {};
    return p;
  });

  // Build a column union from the first few rows.
  const cols: string[] = [];
  for (const r of flatRows.slice(0, 20)) {
    for (const k of Object.keys(r)) {
      if (!cols.includes(k)) cols.push(k);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-bold">Bonds</h1>
        <div className="flex gap-1">
          {(["bi", "finra"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setSource(s)}
              className={`px-3 py-1 rounded text-sm ${
                source === s ? "bg-slate-900 text-white" : "bg-slate-100 hover:bg-slate-200"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
        <span className="text-xs text-slate-500">
          {data?.date ?? "—"} · {items.length} rows
        </span>
      </div>
      <div className="bg-white rounded-lg shadow p-4">
        <DataTable
          headers={cols.slice(0, 12)}
          rows={flatRows.slice(0, 200).map((r) =>
            cols.slice(0, 12).map((c) => (r[c] != null ? String(r[c]) : "—"))
          )}
        />
      </div>
    </div>
  );
}
