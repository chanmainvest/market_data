import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import DataTable from "../components/DataTable";

export default function Earnings() {
  const [week, setWeek] = useState("");
  const { data } = useQuery({
    queryKey: ["earnings", week],
    queryFn: () =>
      api<{ items: any[] }>(`/earnings${week ? `?week=${week}` : ""}`),
  });
  const items = data?.items ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-bold">Earnings</h1>
        <input
          type="date"
          value={week}
          onChange={(e) => setWeek(e.target.value)}
          className="px-2 py-1 border rounded text-sm"
        />
        <span className="text-xs text-slate-500">week starting Monday</span>
      </div>
      <div className="bg-white rounded-lg shadow p-4">
        <DataTable
          headers={["Ticker", "Date", "Report", "EPS avg", "EPS low", "EPS high"]}
          rows={items.map((it) => [
            it.ticker, String(it.earnings_date ?? "—"),
            it.report_time ?? "—",
            it.eps_avg ?? "—", it.eps_low ?? "—", it.eps_high ?? "—",
          ])}
        />
      </div>
    </div>
  );
}
