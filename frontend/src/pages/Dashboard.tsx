import { useQuery } from "@tanstack/react-query";
import { api, type SourceInfo } from "../api/client";
import DataTable from "../components/DataTable";

export default function Dashboard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["sources"],
    queryFn: () => api<SourceInfo[]>("/sources"),
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Data Sources</h1>
      {isLoading && <div className="text-slate-500">Loading…</div>}
      {error && <div className="text-red-600">Error: {(error as Error).message}</div>}
      {data && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Stat label="Sources" value={data.length} />
            <Stat label="With data" value={data.filter((s) => s.rows > 0).length} />
            <Stat label="Total rows" value={data.reduce((a, s) => a + s.rows, 0)} />
            <Stat
              label="Most recent"
              value={
                data
                  .map((s) => s.last_scraped)
                  .filter(Boolean)
                  .sort()
                  .slice(-1)[0] ?? "—"
              }
            />
          </div>
          <div className="bg-white rounded-lg shadow p-4">
            <DataTable
              headers={["Source", "Table", "Rows", "Last scraped"]}
              rows={data.map((s) => [
                s.source,
                <code className="text-xs">{s.table}</code>,
                s.rows.toLocaleString(),
                s.last_scraped ?? <span className="text-slate-400">never</span>,
              ])}
            />
          </div>
        </>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: any }) {
  return (
    <div className="bg-white rounded-lg shadow p-4">
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className="text-2xl font-semibold mt-1 truncate">{value}</div>
    </div>
  );
}
