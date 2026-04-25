"use client";

import type { QueryInterpretation } from "@/lib/api/types";

export function InterpretationPanel({ interpretation }: { interpretation: QueryInterpretation | null | undefined }) {
  if (!interpretation) return null;
  const bullets = interpretation.explanation_ru?.filter(Boolean) ?? [];
  const hasDetail =
    interpretation.metric ||
    interpretation.date_filter ||
    (interpretation.filters && interpretation.filters.length) ||
    (interpretation.group_by && interpretation.group_by.length) ||
    interpretation.sort ||
    interpretation.limit != null;

  if (!bullets.length && !hasDetail) return null;

  return (
    <div className="rounded-xl border border-border bg-card2/50 px-4 py-3">
      <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted2">Как система поняла запрос</div>
      {bullets.length ? (
        <ul className="mt-2 list-disc space-y-1.5 pl-4 text-sm leading-relaxed text-muted">
          {bullets.map((line, i) => (
            <li key={i}>{line}</li>
          ))}
        </ul>
      ) : (
        <dl className="mt-2 space-y-1 text-sm text-muted">
          {interpretation.metric ? (
            <div>
              <dt className="inline text-muted2">Метрика: </dt>
              <dd className="inline">{interpretation.metric}</dd>
            </div>
          ) : null}
          {interpretation.date_filter ? (
            <div>
              <dt className="inline text-muted2">Период: </dt>
              <dd className="inline">{interpretation.date_filter}</dd>
            </div>
          ) : null}
          {interpretation.sort ? (
            <div>
              <dt className="inline text-muted2">Сортировка: </dt>
              <dd className="inline font-mono text-xs">{interpretation.sort}</dd>
            </div>
          ) : null}
        </dl>
      )}
    </div>
  );
}
