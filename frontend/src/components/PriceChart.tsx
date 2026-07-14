import { useEffect, useRef } from "react";
import { createChart, ColorType, type IChartApi } from "lightweight-charts";

type Props = {
  ohlc?: { date: string; open: number; high: number; low: number; close: number }[];
  lines?: { label: string; color: string; data: { date: string; close: number | null }[] }[];
  height?: number;
};

/**
 * Price chart using lightweight-charts v4.
 *
 * The chart instance is created once (on mount) and kept in a ref. Data is
 * pushed to it via a separate effect. This avoids the churn of re-creating
 * the chart on every render — the parent passes freshly-mapped arrays
 * (new references each time), so putting them in a single useEffect's
 * dependency list caused the chart to be created, populated, then
 * immediately torn down and re-created empty.
 */
export default function PriceChart({ ohlc, lines, height = 420 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<{
    candle: ReturnType<IChartApi["addCandlestickSeries"]> | null;
    lines: ReturnType<IChartApi["addLineSeries"]>[];
  }>({ candle: null, lines: [] });

  // --- Create / destroy chart on mount only ---
  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: { background: { type: ColorType.Solid, color: "#ffffff" }, textColor: "#333" },
      grid: { vertLines: { color: "#eee" }, horzLines: { color: "#eee" } },
      timeScale: { timeVisible: false, secondsVisible: false },
      rightPriceScale: { borderColor: "#ccc" },
    });
    chartRef.current = chart;

    const handleResize = () =>
      chart.applyOptions({ width: containerRef.current!.clientWidth });
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
      chartRef.current = null;
      seriesRef.current = { candle: null, lines: [] };
    };
  }, [height]);

  // --- Push OHLC data ---
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !ohlc) return;

    // Remove old candle series if it exists
    if (seriesRef.current.candle) {
      chart.removeSeries(seriesRef.current.candle);
      seriesRef.current.candle = null;
    }

    if (ohlc.length === 0) return;

    const candle = chart.addCandlestickSeries({
      upColor: "#16a34a", downColor: "#dc2626",
      borderUpColor: "#16a34a", borderDownColor: "#dc2626",
      wickUpColor: "#16a34a", wickDownColor: "#dc2626",
    });
    candle.setData(
      ohlc
        .filter((r) => r.open != null && r.close != null)
        .map((r) => ({
          time: r.date as any,
          open: r.open!, high: r.high!, low: r.low!, close: r.close!,
        }))
    );
    seriesRef.current.candle = candle;
    chart.timeScale().fitContent();
  }, [ohlc]);

  // --- Push line data ---
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    // Remove old line series
    for (const s of seriesRef.current.lines) {
      chart.removeSeries(s);
    }
    seriesRef.current.lines = [];

    if (!lines) return;

    for (const l of lines) {
      const series = chart.addLineSeries({
        color: l.color, lineWidth: 2, priceLineVisible: false, lastValueVisible: false,
      });
      series.setData(
        l.data
          .filter((d) => d.close != null)
          .map((d) => ({ time: d.date as any, value: d.close! }))
      );
      seriesRef.current.lines.push(series);
    }
    chart.timeScale().fitContent();
  }, [lines]);

  return <div ref={containerRef} className="w-full" />;
}
