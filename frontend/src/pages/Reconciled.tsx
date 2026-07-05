import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import PriceChart from "../components/PriceChart";
import DataTable from "../components/DataTable";

export default function Reconciled() {
  const { symbol } = useParams<{ symbol: string }>();
  const { data, isLoading } = useQuery({
    queryKey: ["reconciled", symbol],
    queryFn: () =>
      api<{ rows: any[] }>(`/prices/${symbol}/reconciled`),
    enabled: !!symbol,
  });

  if (!symbol) return null;
  const rows = data?.rows ?? [];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">{symbol} — reconciled</h1>
      <div className="bg-white rounded-lg shadow p-4">
        {isLoading && <div className="text-slate-500">Loading…</div>}
        <PriceChart
          ohlc={rows.map((r) => ({
            date: String(r.date),
            open: r.open, high: r.high, low: r.low, close: r.close,
          }))}
        />
      </div>
      <div className="bg-white rounded-lg shadow p-4">
        <h2 className="font-semibold mb-3">Source agreement</h2>
        <DataTable
          headers={["Date", "Close", "Source count", "Sources"]}
          rows={rows.slice(-50).reverse().map((r) => [
            String(r.date),
            r.close ?? "—",
            r.source_count ?? "—",
            Array.isArray(r.sources) ? r.sources.join(", ") : "—",
          ])}
        />
      </div>
    </div>
  );
}
