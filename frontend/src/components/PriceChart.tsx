import { useEffect, useRef } from "react";
import { createChart, ColorType } from "lightweight-charts";

type Props = {
  ohlc?: { date: string; open: number; high: number; low: number; close: number }[];
  lines?: { label: string; color: string; data: { date: string; close: number | null }[] }[];
  height?: number;
};

export default function PriceChart({ ohlc, lines, height = 420 }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = createChart(ref.current, {
      height,
      layout: { background: { type: ColorType.Solid, color: "#ffffff" }, textColor: "#333" },
      grid: { vertLines: { color: "#eee" }, horzLines: { color: "#eee" } },
      timeScale: { timeVisible: false, secondsVisible: false },
      rightPriceScale: { borderColor: "#ccc" },
    });

    if (ohlc && ohlc.length) {
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
    }

    if (lines) {
      for (const l of lines) {
        const series = chart.addLineSeries({
          color: l.color, lineWidth: 2, priceLineVisible: false, lastValueVisible: false,
        });
        series.setData(
          l.data
            .filter((d) => d.close != null)
            .map((d) => ({ time: d.date as any, value: d.close! }))
        );
      }
    }

    chart.timeScale().fitContent();
    const handleResize = () => chart.applyOptions({ width: ref.current!.clientWidth });
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, [ohlc, lines, height]);

  return <div ref={ref} className="w-full" />;
}
