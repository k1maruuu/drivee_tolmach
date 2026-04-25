"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { QueryResult, QueryVisualization } from "@/lib/api/types";
import { resolveVisualization } from "@/lib/visualization/infer";

const PIE_COLORS = [
  "var(--accent)",
  "rgba(108,255,114,0.55)",
  "rgba(120,200,255,0.7)",
  "rgba(255,200,120,0.85)",
  "rgba(200,160,255,0.8)",
  "rgba(255,140,180,0.75)",
];

function MetricCard({
  title,
  value,
}: {
  title: string;
  value: string;
}) {
  return (
    <div className="rounded-2xl border border-border bg-gradient-to-b from-card to-card2 px-6 py-6">
      <div className="text-xs font-semibold uppercase tracking-[0.18em] text-muted2">{title}</div>
      <div className="mt-3 font-mono text-4xl font-medium tabular-nums text-foreground">{value}</div>
    </div>
  );
}

function Table({ result }: { result: QueryResult }) {
  const cols = result.columns || [];
  const rows = result.rows || [];
  const show = rows.slice(0, 50);
  return (
    <div className="rounded-2xl border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-6 py-5">
        <div>
          <div className="text-sm font-medium">Таблица</div>
          <div className="mt-1 text-xs text-muted2">
            строк: <span className="font-mono text-accent2">{result.row_count}</span>
          </div>
        </div>
      </div>
      <div className="overflow-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="sticky top-0 bg-card">
            <tr className="border-b border-border">
              {cols.map((c) => (
                <th
                  key={c}
                  className="px-6 py-3 text-xs font-semibold uppercase tracking-[0.16em] text-muted2"
                >
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {show.map((r, i) => (
              <tr key={i} className="border-b border-border last:border-b-0">
                {cols.map((c) => (
                  <td key={c} className="px-6 py-3 text-sm text-muted">
                    {String((r as Record<string, unknown>)[c] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
            {!show.length ? (
              <tr>
                <td colSpan={Math.max(1, cols.length)} className="px-6 py-6 text-sm text-muted">
                  Нет данных.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ChartFrame({
  title,
  subtitle,
  children,
  tall,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  tall?: boolean;
}) {
  return (
    <div className="rounded-2xl border border-border bg-card px-5 py-5">
      <div className="text-sm font-medium">{title}</div>
      {subtitle ? <div className="mt-1 text-xs text-muted2">{subtitle}</div> : null}
      <div className={tall ? "mt-4 h-[360px]" : "mt-4 h-[320px]"}>{children}</div>
    </div>
  );
}

export function VisualizationRenderer({
  result,
  hint,
}: {
  result: QueryResult;
  hint?: QueryVisualization | null;
}) {
  const model = resolveVisualization(result, hint ?? null);

  if (model.type === "metric") {
    const row = model.data[0] || {};
    return (
      <MetricCard
        title={model.title || model.valueKey}
        value={String((row as Record<string, unknown>)[model.valueKey] ?? "")}
      />
    );
  }

  if (model.type === "pie") {
    const data = model.data.map((row) => ({
      ...row,
      [model.valueKey]: Number((row as Record<string, unknown>)[model.valueKey]) || 0,
    }));
    return (
      <ChartFrame
        title={model.title || "Распределение"}
        subtitle={`${model.nameKey} · ${model.valueKey}`}
        tall
      >
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              dataKey={model.valueKey}
              nameKey={model.nameKey}
              cx="50%"
              cy="50%"
              innerRadius={52}
              outerRadius={110}
              paddingAngle={2}
            >
              {data.map((_, i) => (
                <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} stroke="rgba(0,0,0,0.2)" />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{
                background: "var(--card)",
                border: "1px solid rgba(108,255,114,0.25)",
                borderRadius: 10,
              }}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
          </PieChart>
        </ResponsiveContainer>
      </ChartFrame>
    );
  }

  if (model.type === "bar") {
    const many = model.data.length > 6;
    return (
      <ChartFrame title={model.title || "Столбчатая диаграмма"} subtitle={`${model.xKey} → ${model.yKey}`}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={model.data} margin={{ left: 4, right: 8, top: 8, bottom: many ? 48 : 12 }}>
            <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
            <XAxis
              dataKey={model.xKey}
              tick={{ fill: "var(--muted2)", fontSize: 11 }}
              interval={0}
              angle={many ? -32 : 0}
              textAnchor={many ? "end" : "middle"}
              height={many ? 70 : 36}
            />
            <YAxis tick={{ fill: "var(--muted2)", fontSize: 12 }} width={48} />
            <Tooltip
              contentStyle={{
                background: "var(--card)",
                border: "1px solid rgba(108,255,114,0.25)",
                borderRadius: 10,
              }}
              labelStyle={{ color: "var(--foreground)" }}
              itemStyle={{ color: "var(--muted)" }}
            />
            <Bar dataKey={model.yKey} fill="var(--accent)" radius={[6, 6, 0, 0]} maxBarSize={56} />
          </BarChart>
        </ResponsiveContainer>
      </ChartFrame>
    );
  }

  if (model.type === "line") {
    const many = model.data.length > 8;
    return (
      <ChartFrame title={model.title || "Динамика"} subtitle={`${model.xKey} → ${model.yKey}`}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={model.data} margin={{ left: 4, right: 8, top: 8, bottom: many ? 48 : 12 }}>
            <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
            <XAxis
              dataKey={model.xKey}
              tick={{ fill: "var(--muted2)", fontSize: 11 }}
              interval={many ? "preserveStartEnd" : 0}
              angle={many ? -28 : 0}
              textAnchor={many ? "end" : "middle"}
              height={many ? 68 : 36}
            />
            <YAxis tick={{ fill: "var(--muted2)", fontSize: 12 }} width={48} />
            <Tooltip
              contentStyle={{
                background: "var(--card)",
                border: "1px solid rgba(108,255,114,0.25)",
                borderRadius: 10,
              }}
              labelStyle={{ color: "var(--foreground)" }}
              itemStyle={{ color: "var(--muted)" }}
            />
            <Line
              type="monotone"
              dataKey={model.yKey}
              stroke="var(--accent)"
              strokeWidth={2}
              dot={model.data.length <= 24}
              activeDot={{ r: 4 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </ChartFrame>
    );
  }

  return <Table result={result} />;
}
