// Thin fetch wrapper around the mdata backend. All endpoints return JSON.
const BASE = "/api";

export async function api<T = any>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// Typed shapes (kept loose — the API is the source of truth).
export type SourceInfo = {
  source: string;
  table: string;
  rows: number;
  last_scraped: string | null;
};

export type PriceRow = {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  adj_close?: number | null;
  volume?: number | null;
  [k: string]: any;
};

export type CompareResponse = {
  ticker: string;
  series: Record<string, { date: string; close: number | null }[]>;
};
