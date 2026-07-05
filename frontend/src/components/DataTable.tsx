import type { ReactNode } from "react";

type Props = {
  headers: ReactNode[];
  rows: ReactNode[][];
  emptyLabel?: string;
};

export default function DataTable({ headers, rows, emptyLabel = "No data" }: Props) {
  if (!rows.length) {
    return <div className="text-slate-500 italic py-4">{emptyLabel}</div>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead className="bg-slate-100 text-slate-600 uppercase text-xs">
          <tr>
            {headers.map((h, i) => (
              <th key={i} className="px-3 py-2 text-left font-medium">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r, i) => (
            <tr key={i} className="hover:bg-slate-50">
              {r.map((c, j) => (
                <td key={j} className="px-3 py-2 whitespace-nowrap">{c}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
