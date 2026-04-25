"use client";

import { useEffect, useMemo, useState } from "react";

import { cn } from "@/lib/cn";
import { useAuth } from "@/context/AuthContext";
import { apiTemplateExecute, apiTemplateExportExcel, apiTemplatesList } from "@/lib/api/templates";
import type { QueryTemplateRead, TemplateExecuteResponse } from "@/lib/api/types";
import { InterpretationPanel } from "@/components/InterpretationPanel";
import { VisualizationRenderer } from "@/components/VisualizationRenderer";

function SkeletonCard() {
  return (
    <div className="animate-pulse rounded-2xl border border-border bg-card">
      <div className="h-28 border-b border-border bg-card2" />
      <div className="space-y-3 p-5">
        <div className="h-4 w-2/3 rounded bg-card2" />
        <div className="h-3 w-full rounded bg-card2" />
        <div className="h-3 w-5/6 rounded bg-card2" />
        <div className="flex items-center justify-between pt-2">
          <div className="h-6 w-20 rounded-full bg-card2" />
          <div className="h-8 w-24 rounded-lg bg-card2" />
        </div>
      </div>
    </div>
  );
}

function ResultTable({
  resp,
  token,
  setError,
}: {
  resp: TemplateExecuteResponse;
  token: string | null;
  setError: (s: string | null) => void;
}) {
  const cols = resp.result.columns || [];
  const rows = resp.result.rows || [];
  const show = rows.slice(0, 20);

  async function downloadExcel() {
    if (!token) return;
    setError(null);
    try {
      const out = await apiTemplateExportExcel(token, resp.template_id, {
        params: resp.params || {},
        max_rows: 1000,
      });
      const url = window.URL.createObjectURL(out.blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = out.filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e: unknown) {
      setError(typeof (e as { message?: string })?.message === "string" ? (e as { message: string }).message : "Не удалось скачать Excel");
    }
  }

  return (
    <div className="rounded-2xl border border-border bg-card">
      <div className="border-b border-border px-6 py-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-sm font-medium">{resp.title}</div>
            <div className="mt-1 text-xs text-muted2">
              cache:{" "}
              <span className={cn(resp.cache_hit ? "text-accent2" : "text-muted")}>
                {resp.cache_hit ? "hit" : "miss"}
              </span>{" "}
              · строк: <span className="font-mono text-accent2">{resp.result.row_count}</span>
              {typeof resp.confidence === "number" ? (
                <span className="ml-2 font-mono text-accent2">· уверенность: {resp.confidence.toFixed(2)}</span>
              ) : null}
            </div>
          </div>
          <button
            type="button"
            disabled={!token}
            onClick={() => void downloadExcel()}
            className="rounded-lg border border-border2 bg-card px-4 py-2 text-xs font-medium text-muted hover:border-[rgba(108,255,114,0.25)] hover:text-foreground disabled:opacity-40"
          >
            Скачать Excel
          </button>
        </div>
        <div className="mt-4 rounded-xl border border-border bg-[#0b1410] px-4 py-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-accent2">SQL</div>
          <div className="mt-2 max-w-full overflow-auto font-mono text-xs leading-6 text-[rgb(126,216,160)]">
            {resp.sql}
          </div>
        </div>
      </div>
      <div className="space-y-4 px-6 py-5">
        <InterpretationPanel interpretation={resp.interpretation} />
        <VisualizationRenderer result={resp.result} hint={resp.visualization ?? null} />
        <details className="rounded-xl border border-border bg-card2/40 px-4 py-3">
          <summary className="cursor-pointer text-xs font-semibold uppercase tracking-[0.18em] text-muted2">
            Таблица (первые 20 строк)
          </summary>
          <div className="mt-3 overflow-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="sticky top-0 bg-card">
                <tr className="border-b border-border">
                  {cols.map((c) => (
                    <th key={c} className="px-4 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-muted2">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {show.map((r, i) => (
                  <tr key={i} className="border-b border-border last:border-b-0">
                    {cols.map((c) => (
                      <td key={c} className="px-4 py-2 text-sm text-muted">
                        {String((r as Record<string, unknown>)[c] ?? "")}
                      </td>
                    ))}
                  </tr>
                ))}
                {!show.length ? (
                  <tr>
                    <td colSpan={Math.max(1, cols.length)} className="px-4 py-4 text-sm text-muted">
                      Нет данных.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </details>
      </div>
    </div>
  );
}

export default function TemplatesPage() {
  const { token } = useAuth();
  const [templates, setTemplates] = useState<QueryTemplateRead[] | null>(null);
  const [query, setQuery] = useState("");
  const [activeCategory, setActiveCategory] = useState<string>("Все");
  const [error, setError] = useState<string | null>(null);

  const [runningId, setRunningId] = useState<string | null>(null);
  const [result, setResult] = useState<TemplateExecuteResponse | null>(null);
  const [paramsModal, setParamsModal] = useState<{
    tpl: QueryTemplateRead;
    values: Record<string, string>;
  } | null>(null);

  useEffect(() => {
    if (!token) return;
    setError(null);
    setTemplates(null);
    void apiTemplatesList(token)
      .then((list) => setTemplates(list))
      .catch((e: any) => setError(typeof e?.message === "string" ? e.message : "Не удалось загрузить шаблоны"));
  }, [token]);

  const categories = useMemo(() => {
    const set = new Set<string>();
    (templates || []).forEach((t) => set.add(t.category));
    return ["Все", ...Array.from(set).sort((a, b) => a.localeCompare(b, "ru"))];
  }, [templates]);

  const filtered = useMemo(() => {
    const list = templates || [];
    const q = query.trim().toLowerCase();
    return list.filter((t) => {
      if (activeCategory !== "Все" && t.category !== activeCategory) return false;
      if (!q) return true;
      return (
        t.title.toLowerCase().includes(q) ||
        t.description.toLowerCase().includes(q) ||
        t.question.toLowerCase().includes(q)
      );
    });
  }, [templates, query, activeCategory]);

  async function runTemplate(tpl: QueryTemplateRead, params?: Record<string, unknown>) {
    if (!token) return;
    setError(null);
    setResult(null);
    setRunningId(tpl.id);
    try {
      const resp = await apiTemplateExecute(token, tpl.id, { params, max_rows: 100 });
      setResult(resp);
    } catch (e: any) {
      const detail = e?.detail;
      if (detail && typeof detail === "object" && Array.isArray(detail.missing_params)) {
        const values: Record<string, string> = {};
        detail.missing_params.forEach((k: string) => (values[k] = ""));
        setParamsModal({ tpl, values });
      } else {
        setError(typeof e?.message === "string" ? e.message : "Не удалось выполнить шаблон");
      }
    } finally {
      setRunningId(null);
    }
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="border-b border-border bg-panel px-8 py-6">
        <div className="text-lg font-medium">Библиотека шаблонов</div>
        <div className="mt-1 text-sm text-muted">
          Готовые запросы — выберите и запустите в один клик
        </div>
      </div>

      <div className="border-b border-border bg-panel px-8 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap gap-2">
            {categories.map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => setActiveCategory(c)}
                className={cn(
                  "rounded-full border px-4 py-1.5 text-sm transition-colors",
                  c === activeCategory
                    ? "border-[rgba(108,255,114,0.3)] bg-accentbg text-accent"
                    : "border-border2 text-muted hover:text-foreground"
                )}
              >
                {c}
              </button>
            ))}
          </div>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Поиск шаблона…"
            className="h-10 w-full max-w-xs rounded-lg border border-border2 bg-card2 px-4 text-sm text-foreground outline-none placeholder:text-muted2 focus:border-[rgba(108,255,114,0.5)]"
          />
        </div>
      </div>

      <div className="flex flex-1 flex-col gap-6 overflow-y-auto px-8 py-8">
        {error ? (
          <div className="rounded-2xl border border-[rgba(255,107,107,0.35)] bg-dangerbg px-6 py-4 text-sm text-danger">
            {error}
          </div>
        ) : null}

        {result ? <ResultTable resp={result} token={token} setError={setError} /> : null}

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          {templates === null ? (
            Array.from({ length: 8 }).map((_, i) => <SkeletonCard key={i} />)
          ) : filtered.length ? (
            filtered.map((tpl) => (
              <div key={tpl.id} className="group overflow-hidden rounded-2xl border border-border bg-card">
                <div className="h-28 border-b border-border bg-card2 p-4">
                  <div className="flex h-full items-end gap-2 opacity-80">
                    <div className="h-[42%] flex-1 rounded-t bg-[rgba(108,255,114,0.22)]" />
                    <div className="h-[84%] flex-1 rounded-t bg-accent" />
                    <div className="h-[62%] flex-1 rounded-t bg-[rgba(108,255,114,0.22)]" />
                    <div className="h-[48%] flex-1 rounded-t bg-[rgba(108,255,114,0.22)]" />
                    <div className="h-[71%] flex-1 rounded-t bg-[rgba(108,255,114,0.22)]" />
                  </div>
                </div>
                <div className="p-5">
                  <div className="text-sm font-medium">{tpl.title}</div>
                  <div className="mt-2 line-clamp-2 text-sm text-muted">{tpl.description}</div>
                  <div className="mt-4 flex items-center justify-between gap-3">
                    <span className="rounded-full bg-card2 px-3 py-1 text-xs text-muted2">{tpl.category}</span>
                    <button
                      type="button"
                      onClick={() => void runTemplate(tpl)}
                      disabled={runningId === tpl.id}
                      className={cn(
                        "rounded-lg border border-[rgba(108,255,114,0.3)] bg-accentbg px-4 py-2 text-sm font-medium text-accent",
                        "transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
                      )}
                    >
                      {runningId === tpl.id ? "Запуск…" : "Использовать"}
                    </button>
                  </div>
                  {tpl.params?.length ? (
                    <div className="mt-3 text-xs text-muted2">Параметры: {tpl.params.join(", ")}</div>
                  ) : null}
                </div>
              </div>
            ))
          ) : (
            <div className="col-span-full rounded-2xl border border-border bg-card px-6 py-10 text-center text-sm text-muted">
              Ничего не найдено.
            </div>
          )}
        </div>
      </div>

      {paramsModal ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
          <div className="w-full max-w-lg rounded-2xl border border-border bg-card p-6">
            <div className="text-sm font-medium">Параметры шаблона</div>
            <div className="mt-1 text-sm text-muted">{paramsModal.tpl.title}</div>
            <div className="mt-5 space-y-3">
              {Object.keys(paramsModal.values).map((k) => (
                <label key={k} className="block">
                  <div className="mb-2 text-xs text-muted">{k}</div>
                  <input
                    value={paramsModal.values[k]}
                    onChange={(e) =>
                      setParamsModal((p) =>
                        p ? { ...p, values: { ...p.values, [k]: e.target.value } } : p
                      )
                    }
                    className="h-10 w-full rounded-lg border border-border2 bg-card2 px-4 text-sm text-foreground outline-none placeholder:text-muted2 focus:border-[rgba(108,255,114,0.5)]"
                    placeholder="Введите значение"
                  />
                </label>
              ))}
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setParamsModal(null)}
                className="rounded-lg border border-border2 px-4 py-2 text-sm text-muted hover:text-foreground"
              >
                Отмена
              </button>
              <button
                type="button"
                onClick={() => {
                  const { tpl, values } = paramsModal;
                  setParamsModal(null);
                  void runTemplate(tpl, values);
                }}
                className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-[#0a1a0c] hover:opacity-90"
              >
                Запустить
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

