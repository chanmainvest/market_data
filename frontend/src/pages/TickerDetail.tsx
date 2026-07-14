import { useState, useMemo } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import PriceChart from "../components/PriceChart";

const SOURCES = ["reconciled", "yahoo", "alpha_vantage", "macrotrends"] as const;

export default function TickerDetail() {
  const { symbol } = useParams<{ symbol: string }>();
  const nav = useNavigate();
  const [source, setSource] = useState<(typeof SOURCES)[number]>("reconciled");

  const prices = useQuery({
    queryKey: ["prices", symbol, source],
    queryFn: () => api<{ rows: any[]; count: number }>(`/prices/${symbol}?source=${source}`),
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

  const rows = prices.data?.rows ?? [];
  // Memoize so the array identity is stable across re-renders (when the
  // data hasn't actually changed). Without this the chart's useEffect
  // fires on every render and churns the chart instance.
  const ohlc = useMemo(
    () =>
      rows.map((r) => ({
        date: String(r.date),
        open: r.open, high: r.high, low: r.low, close: r.close,
      })),
    [rows]
  );

  // If the selected source has no data, surface which sources do (from the
  // compare query) so the user isn't staring at a blank chart.
  const sourceAvailability =
    compare.data
      ? Object.fromEntries(
          Object.entries(compare.data.series).map(([k, v]) => [k, v.length])
        )
      : {};
  const hasNoData = rows.length === 0 && !prices.isLoading;
  const totalAcrossSources = Object.values(sourceAvailability).reduce((a, b) => a + b, 0);
  const alternatives = Object.entries(sourceAvailability)
    .filter(([, n]) => n > 0)
    .map(([k]) => k);

  // "Did you mean?" — only when NO source has data (likely a typo / unknown
  // ticker). Asks the backend for similar tickers via levenshtein distance.
  const suggest = useQuery({
    queryKey: ["suggest", symbol],
    queryFn: () => api<{ suggestions: { ticker: string; distance: number }[] }>(
      `/tickers/suggest?q=${symbol}`
    ),
    enabled: !!symbol && totalAcrossSources === 0 && !compare.isLoading,
  });
  const topSuggestions = (suggest.data?.suggestions ?? [])
    .filter((s) => s.distance <= 2)
    .slice(0, 5);

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
          {SOURCES.map((s) => {
            const n = sourceAvailability[s];
            return (
              <button
                key={s}
                onClick={() => setSource(s)}
                className={`px-3 py-1 rounded text-sm ${
                  source === s ? "bg-slate-900 text-white" : "bg-slate-100 hover:bg-slate-200"
                }`}
              >
                {s}
                {n != null && (
                  <span className={`ml-1 text-xs ${n > 0 ? "text-emerald-500" : "text-slate-400"}`}>
                    {n > 0 ? n.toLocaleString() : "—"}
                  </span>
                )}
              </button>
            );
          })}
        </div>
        {hasNoData ? (
          <div className="text-center py-12 text-slate-500">
            <p className="mb-2">No <code className="text-sm">{source}</code> data for {symbol}.</p>
            {alternatives.length > 0 ? (
              <p className="text-sm">
                Try:{" "}
                {alternatives.map((a, i) => (
                  <span key={a}>
                    {i > 0 && ", "}
                    <button
                      onClick={() => setSource(a as (typeof SOURCES)[number])}
                      className="text-blue-600 hover:underline"
                    >
                      {a}
                    </button>
                  </span>
                ))}
              </p>
            ) : totalAcrossSources === 0 ? (
              <>
                <p className="text-sm mb-3">No data from any source for this ticker.</p>
                {topSuggestions.length > 0 && (
                  <p className="text-sm">
                    Did you mean:{" "}
                    {topSuggestions.map((s, i) => (
                      <span key={s.ticker}>
                        {i > 0 && ", "}
                        <button
                          onClick={() => nav(`/ticker/${s.ticker}`)}
                          className="text-blue-600 hover:underline font-medium"
                        >
                          {s.ticker}
                        </button>
                      </span>
                    ))}
                    ?
                  </p>
                )}
              </>
            ) : null}
          </div>
        ) : (
          <PriceChart ohlc={ohlc} />
        )}
      </div>

      <div className="bg-white rounded-lg shadow p-4">
        <h2 className="font-semibold mb-3">Multi-source comparison</h2>
        {lines && <PriceChart lines={lines} height={300} />}
      </div>
    </div>
  );
}
