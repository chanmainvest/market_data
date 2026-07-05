import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import PriceChart from "../components/PriceChart";

const SOURCES = ["reconciled", "yahoo", "alpha_vantage", "macrotrends"] as const;

export default function TickerDetail() {
  const { symbol } = useParams<{ symbol: string }>();
  const [source, setSource] = useState<(typeof SOURCES)[number]>("reconciled");

  const prices = useQuery({
    queryKey: ["prices", symbol, source],
    queryFn: () => api<{ rows: any[] }>(`/prices/${symbol}?source=${source}`),
    enabled: !!symbol,
  });
  const compare = useQuery({
    queryKey: ["compare", symbol],
    queryFn: () => api<{ series: Record<string, { date: string; close: number | null }[]> }>(
      `/prices/${symbol}/compare`
    ),
    enabled: !!symbol,
  });

  if (!symbol) return null;

  const ohlc = (prices.data?.rows ?? []).map((r) => ({
    date: String(r.date),
    open: r.open, high: r.high, low: r.low, close: r.close,
  }));

  const lines =
    compare.data && Object.keys(compare.data.series).length > 0
      ? Object.entries(compare.data.series).map(([label, data]) => ({
          label,
          color:
            label === "reconciled" ? "#1e40af"
            : label === "yahoo" ? "#0891b2"
            : label === "alpha_vantage" ? "#ca8a04"
            : "#9333ea",
          data,
        }))
      : undefined;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <h1 className="text-2xl font-bold">{symbol}</h1>
        <Link
          to={`/reconcile/${symbol}`}
          className="text-sm text-blue-600 hover:underline"
        >
          reconcile view →
        </Link>
      </div>

      <div className="bg-white rounded-lg shadow p-4">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-sm text-slate-500">Source:</span>
          {SOURCES.map((s) => (
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
        <PriceChart ohlc={ohlc} />
      </div>

      <div className="bg-white rounded-lg shadow p-4">
        <h2 className="font-semibold mb-3">Multi-source comparison</h2>
        {lines && <PriceChart lines={lines} height={300} />}
      </div>
    </div>
  );
}
