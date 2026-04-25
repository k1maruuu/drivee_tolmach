"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { cn } from "@/lib/cn";
import { useAuth } from "@/context/AuthContext";
import { apiHistoryList, apiReportsList, apiReportSave } from "@/lib/api/reports";
import { apiSchedulesList, apiScheduleRunNow, apiSchedulePatch, apiScheduleDelete } from "@/lib/api/schedules";
import type { QueryHistoryRead, ReportScheduleRead, SavedReportRead } from "@/lib/api/types";

function fmtDate(iso: string | null | undefined) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("ru-RU", { year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export default function ReportsPage() {
  const { token } = useAuth();
  const [tab, setTab] = useState<"reports" | "history" | "schedules">("reports");
  const [reports, setReports] = useState<SavedReportRead[] | null>(null);
  const [history, setHistory] = useState<QueryHistoryRead[] | null>(null);
  const [schedules, setSchedules] = useState<ReportScheduleRead[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [schedBusy, setSchedBusy] = useState(false);

  useEffect(() => {
    if (!token) return;
    setError(null);
    setReports(null);
    setHistory(null);
    setSchedules(null);
    void apiReportsList(token)
      .then(setReports)
      .catch((e: { message?: string }) => setError(typeof e?.message === "string" ? e.message : "Не удалось загрузить отчёты"));
    void apiHistoryList(token, { limit: 50, offset: 0 })
      .then(setHistory)
      .catch(() => null);
    void apiSchedulesList(token, { limit: 100 })
      .then(setSchedules)
      .catch(() => setSchedules([]));
  }, [token]);

  const hasReports = (reports?.length || 0) > 0;
  const hasHistory = (history?.length || 0) > 0;

  const tabs = useMemo(
    () => [
      { id: "reports" as const, label: `Сохранённые (${reports?.length ?? "…" })` },
      { id: "history" as const, label: `История (${history?.length ?? "…" })` },
      { id: "schedules" as const, label: `Расписания (${schedules?.length ?? "…" })` },
    ],
    [reports, history, schedules]
  );

  async function refreshSchedules() {
    if (!token) return;
    const list = await apiSchedulesList(token, { limit: 100 });
    setSchedules(list);
  }

  async function saveFromHistory(item: QueryHistoryRead) {
    if (!token) return;
    setSavingId(item.id);
    setError(null);
    try {
      const title = item.question.slice(0, 80);
      await apiReportSave(token, {
        title,
        description: "Сохранено из истории",
        history_id: item.id,
        default_max_rows: 100,
      });
      const updated = await apiReportsList(token);
      setReports(updated);
      setTab("reports");
    } catch (e: any) {
      setError(typeof e?.message === "string" ? e.message : "Не удалось сохранить отчёт");
    } finally {
      setSavingId(null);
    }
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="border-b border-border bg-panel px-8 py-6">
        <div className="text-lg font-medium">Отчёты</div>
        <div className="mt-1 text-sm text-muted">
          Сохранённые отчёты и результаты запусков
        </div>
      </div>

      <div className="border-b border-border bg-panel px-8 py-4">
        <div className="flex flex-wrap gap-2">
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={cn(
                "rounded-full border px-4 py-1.5 text-sm transition-colors",
                tab === t.id
                  ? "border-[rgba(108,255,114,0.3)] bg-accentbg text-accent"
                  : "border-border2 text-muted hover:text-foreground"
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-1 flex-col gap-4 overflow-y-auto px-8 py-8">
        {error ? (
          <div className="rounded-2xl border border-[rgba(255,107,107,0.35)] bg-dangerbg px-6 py-4 text-sm text-danger">
            {error}
          </div>
        ) : null}

        {tab === "reports" ? (
          reports === null ? (
            <div className="rounded-2xl border border-border bg-card px-6 py-8 text-sm text-muted">
              Загрузка отчётов…
            </div>
          ) : hasReports ? (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              {reports.map((r) => (
                <Link
                  key={r.id}
                  href={`/reports/${r.id}`}
                  className="rounded-2xl border border-border bg-card p-6 hover:border-[rgba(108,255,114,0.25)]"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium">{r.title}</div>
                      <div className="mt-2 text-sm text-muted line-clamp-2">{r.description || r.question}</div>
                    </div>
                    <span className="rounded-full bg-card2 px-3 py-1 text-xs text-muted2">#{r.id}</span>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-3 text-xs text-muted2">
                    <span>обновлён: {fmtDate(r.updated_at)}</span>
                    {r.last_row_count != null ? (
                      <span>
                        строк: <span className="font-mono text-accent2">{r.last_row_count}</span>
                      </span>
                    ) : null}
                    {r.last_run_at ? <span>последний запуск: {fmtDate(r.last_run_at)}</span> : null}
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <div className="rounded-2xl border border-border bg-card px-6 py-10 text-center text-sm text-muted">
              Пока нет сохранённых отчётов. Откройте вкладку «История» и сохраните удачный запрос.
            </div>
          )
        ) : tab === "history" ? (
          history === null ? (
            <div className="rounded-2xl border border-border bg-card px-6 py-8 text-sm text-muted">
              Загрузка истории…
            </div>
          ) : hasHistory ? (
            <div className="space-y-3">
              {history.map((h) => (
                <div key={h.id} className="rounded-2xl border border-border bg-card px-6 py-5">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm font-medium">{h.question}</div>
                      <div className="mt-2 text-xs text-muted2">
                        {fmtDate(h.created_at)} · source: {h.source} · status:{" "}
                        <span className={cn(h.status === "ok" ? "text-accent2" : "text-danger")}>{h.status}</span>
                        {h.row_count != null ? (
                          <>
                            {" "}
                            · строк: <span className="font-mono text-accent2">{h.row_count}</span>
                          </>
                        ) : null}
                      </div>
                    </div>

                    {h.status === "ok" ? (
                      <button
                        type="button"
                        onClick={() => void saveFromHistory(h)}
                        disabled={savingId === h.id}
                        className={cn(
                          "rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-[#0a1a0c]",
                          "transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
                        )}
                      >
                        {savingId === h.id ? "Сохранение…" : "Сохранить как отчёт"}
                      </button>
                    ) : (
                      <span className="rounded-lg border border-[rgba(255,107,107,0.35)] bg-dangerbg px-3 py-2 text-xs text-danger">
                        {h.error_message || "Заблокирован"}
                      </span>
                    )}
                  </div>

                  <div className="mt-4 rounded-xl border border-border bg-[#0b1410] px-4 py-3">
                    <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-accent2">SQL</div>
                    <div className="mt-2 overflow-auto font-mono text-xs leading-6 text-[rgb(126,216,160)]">
                      {h.generated_sql}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-2xl border border-border bg-card px-6 py-10 text-center text-sm text-muted">
              История пока пустая.
            </div>
          )
        ) : tab === "schedules" ? (
          schedules === null ? (
            <div className="rounded-2xl border border-border bg-card px-6 py-8 text-sm text-muted">Загрузка…</div>
          ) : schedules.length ? (
            <div className="space-y-3">
              {schedules.map((s) => (
                <div key={s.id} className="rounded-2xl border border-border bg-card px-6 py-5">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium">
                        Расписание #{s.id} → отчёт #{s.report_id}
                        {s.report?.title ? ` — ${s.report.title}` : ""}
                      </div>
                      <div className="mt-2 text-xs text-muted2">
                        {s.frequency} · {s.timezone} · {s.hour}:{String(s.minute).padStart(2, "0")} · следующий:{" "}
                        {fmtDate(s.next_run_at)}
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Link
                        href={`/reports/${s.report_id}`}
                        className="rounded-lg border border-border2 px-3 py-1.5 text-xs hover:text-foreground"
                      >
                        К отчёту
                      </Link>
                      <button
                        type="button"
                        disabled={schedBusy}
                        onClick={async () => {
                          if (!token) return;
                          setSchedBusy(true);
                          try {
                            await apiScheduleRunNow(token, s.id);
                            await refreshSchedules();
                          } finally {
                            setSchedBusy(false);
                          }
                        }}
                        className="rounded-lg border border-border2 px-3 py-1.5 text-xs"
                      >
                        Запустить
                      </button>
                      <button
                        type="button"
                        disabled={schedBusy}
                        onClick={async () => {
                          if (!token) return;
                          setSchedBusy(true);
                          try {
                            await apiSchedulePatch(token, s.id, { is_enabled: !s.is_enabled });
                            await refreshSchedules();
                          } finally {
                            setSchedBusy(false);
                          }
                        }}
                        className="rounded-lg border border-border2 px-3 py-1.5 text-xs"
                      >
                        {s.is_enabled ? "Выкл" : "Вкл"}
                      </button>
                      <button
                        type="button"
                        disabled={schedBusy}
                        onClick={async () => {
                          if (!token || !window.confirm("Удалить расписание?")) return;
                          setSchedBusy(true);
                          try {
                            await apiScheduleDelete(token, s.id);
                            await refreshSchedules();
                          } finally {
                            setSchedBusy(false);
                          }
                        }}
                        className="rounded-lg border border-[rgba(255,107,107,0.35)] px-3 py-1.5 text-xs text-danger"
                      >
                        Удалить
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-2xl border border-border bg-card px-6 py-10 text-center text-sm text-muted">
              Нет расписаний. Создайте их на странице сохранённого отчёта.
            </div>
          )
        ) : null}
      </div>
    </div>
  );
}

