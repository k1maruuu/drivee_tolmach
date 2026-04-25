import type { QueryResult, QueryVisualization } from "@/lib/api/types";

export type VisualizationModel =
  | {
      type: "metric";
      title?: string;
      valueKey: string;
      data: Record<string, unknown>[];
    }
  | {
      type: "bar";
      title?: string;
      xKey: string;
      yKey: string;
      data: Record<string, unknown>[];
    }
  | {
      type: "line";
      title?: string;
      xKey: string;
      yKey: string;
      data: Record<string, unknown>[];
    }
  | {
      type: "pie";
      title?: string;
      nameKey: string;
      valueKey: string;
      data: Record<string, unknown>[];
    }
  | { type: "table"; title?: string; data: Record<string, unknown>[]; columns: string[] };

const CATEGORICAL_NAMES = new Set([
  "city_id",
  "status_order",
  "status_tender",
  "tariff_id",
  "hour",
  "offset_hours",
]);

const Y_NUMERIC_PRIORITY = [
  "count",
  "total",
  "orders",
  "sum",
  "avg",
  "revenue",
  "amount",
  "declined",
  "cancel",
];

function isNumericValue(v: unknown) {
  if (typeof v === "number" && Number.isFinite(v)) return true;
  if (typeof v === "string") {
    const s = v.trim().replace(/\s+/g, "").replace(",", ".");
    if (!s) return false;
    const n = Number(s);
    return Number.isFinite(n);
  }
  return false;
}

function looksLikeDate(v: unknown) {
  if (typeof v !== "string") return false;
  const s = v.trim();
  if (!s) return false;
  const t = Date.parse(s);
  if (!Number.isFinite(t)) return false;
  return s.length >= 8;
}

function pickPreferredNumericY(numericCols: string[]): string {
  const lower = (c: string) => c.toLowerCase();
  let best = numericCols[0];
  let bestScore = -1;
  for (const c of numericCols) {
    const l = lower(c);
    let score = 0;
    for (let i = 0; i < Y_NUMERIC_PRIORITY.length; i++) {
      if (l.includes(Y_NUMERIC_PRIORITY[i])) {
        score = Y_NUMERIC_PRIORITY.length - i;
        break;
      }
    }
    if (score > bestScore) {
      bestScore = score;
      best = c;
    }
  }
  return best;
}

export function tryVisualizationFromHint(
  result: QueryResult,
  hint: QueryVisualization | null | undefined
): VisualizationModel | null {
  if (!hint?.type) return null;
  const cols = result.columns || [];
  const rows = result.rows || [];
  const t = (hint.type || "table").toLowerCase();
  const lx = hint.label_column || hint.x_axis || undefined;
  const vy = hint.value_column || hint.y_axis || undefined;

  if (t === "metric" && vy && cols.includes(vy) && rows.length >= 1) {
    return { type: "metric", valueKey: vy, data: rows, title: hint.title ?? undefined };
  }
  if (t === "bar" && lx && vy && cols.includes(lx) && cols.includes(vy)) {
    return { type: "bar", xKey: lx, yKey: vy, data: rows, title: hint.title ?? undefined };
  }
  if (t === "line" && lx && vy && cols.includes(lx) && cols.includes(vy)) {
    return { type: "line", xKey: lx, yKey: vy, data: rows, title: hint.title ?? undefined };
  }
  if (t === "pie" && lx && vy && cols.includes(lx) && cols.includes(vy)) {
    return { type: "pie", nameKey: lx, valueKey: vy, data: rows, title: hint.title ?? undefined };
  }
  if (t === "table") {
    return { type: "table", columns: cols, data: rows, title: hint.title ?? undefined };
  }
  return null;
}

export function resolveVisualization(
  result: QueryResult,
  hint: QueryVisualization | null | undefined
): VisualizationModel {
  const fromHint = tryVisualizationFromHint(result, hint);
  if (fromHint) return fromHint;
  return inferVisualization(result);
}

export function inferVisualization(result: QueryResult): VisualizationModel {
  const columns = result.columns || [];
  const rows = result.rows || [];

  if (!columns.length) return { type: "table", columns: [], data: rows };

  const numericCols: string[] = [];
  const dateCols: string[] = [];
  const otherCols: string[] = [];

  for (const c of columns) {
    const nameKey = c.toLowerCase();
    let sample: unknown = undefined;
    for (const r of rows) {
      const v = (r as Record<string, unknown>)[c];
      if (v !== null && v !== undefined && String(v).trim() !== "") {
        sample = v;
        break;
      }
    }
    if (CATEGORICAL_NAMES.has(nameKey)) {
      otherCols.push(c);
    } else if (looksLikeDate(sample)) {
      dateCols.push(c);
    } else if (isNumericValue(sample)) {
      numericCols.push(c);
    } else {
      otherCols.push(c);
    }
  }

  if (rows.length === 1 && numericCols.length === 1) {
    return { type: "metric", valueKey: numericCols[0], data: rows };
  }

  if (dateCols.length >= 1 && numericCols.length >= 1) {
    const yKey = pickPreferredNumericY(numericCols);
    return { type: "line", xKey: dateCols[0], yKey, data: rows };
  }

  if (otherCols.length >= 1 && numericCols.length >= 1) {
    const yKey = pickPreferredNumericY(numericCols);
    const xKey = otherCols[0];
    if (rows.length <= 15 && rows.length >= 2) {
      return { type: "pie", nameKey: xKey, valueKey: yKey, data: rows };
    }
    return { type: "bar", xKey, yKey, data: rows };
  }

  if (numericCols.length >= 2 && rows.length >= 2) {
    const yKey = pickPreferredNumericY(numericCols);
    const xKey = numericCols.find((c) => c !== yKey) || numericCols[0];
    if (xKey !== yKey) {
      return { type: "bar", xKey, yKey, data: rows };
    }
  }

  return { type: "table", columns, data: rows };
}
