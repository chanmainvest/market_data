import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import DataTable from "../components/DataTable";

const CPC_CATS = ["total", "index", "etp", "equity", "vix", "spx", "oex"];

export default function Macro() {
  const [series, setSeries] = useState("WALCL");
  const [cat, setCat] = useState("total");

  const fred = useQuery({
    queryKey: ["fred", series],
    queryFn: () => api<{ rows: { date: string; value: number }[] }>(`/fred?series_id=${series}`),
  });
  const cpc = useQuery({
    queryKey: ["cpc", cat],
    queryFn: () => api<{ rows: any[] }>(`/cpc/${cat}`),
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Macro & sentiment</h1>

      <div className="bg-white rounded-lg shadow p-4 space-y-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">FRED series:</span>
          <input
            value={series}
            onChange={(e) => setSeries(e.target.value.toUpperCase())}
            className="px-2 py-1 border rounded text-sm w-32"
          />
          <span className="text-xs text-slate-500">
            {fred.data?.rows.length ?? 0} observations
          </span>
        </div>
        <DataTable
          headers={["Date", "Value"]}
          rows={(fred.data?.rows ?? []).slice(-30).reverse().map((r) => [
            r.date, r.value?.toLocaleString() ?? "—",
          ])}
        />
      </div>

      <div className="bg-white rounded-lg shadow p-4 space-y-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">CBOE put-call ratio:</span>
          {CPC_CATS.map((c) => (
            <button
              key={c}
              onClick={() => setCat(c)}
              className={`px-2 py-1 rounded text-xs ${
                cat === c ? "bg-slate-900 text-white" : "bg-slate-100 hover:bg-slate-200"
              }`}
            >
              {c}
            </button>
          ))}
        </div>
        <DataTable
          headers={["Date", "Ratio", "Vol call", "Vol put", "Vol total"]}
          rows={(cpc.data?.rows ?? []).slice(-30).reverse().map((r) => [
            String(r.date), r.ratio?.toFixed(2) ?? "—",
            r.vol_call ?? "—", r.vol_put ?? "—", r.vol_total ?? "—",
          ])}
        />
      </div>
    </div>
  );
}
