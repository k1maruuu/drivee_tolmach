"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import { cn } from "@/lib/cn";
import { useAuth } from "@/context/AuthContext";
import { apiReportDelete, apiReportExecute, apiReportExportExcel, apiReportGet, apiReportPatch } from "@/lib/api/reports";
import {
  apiScheduleCreate,
  apiScheduleDelete,
  apiSchedulePatch,
  apiScheduleRunNow,
  apiSchedulesList,
} from "@/lib/api/schedules";
import type {
  QueryInterpretation,
  QueryResult,
  QueryVisualization,
  ReportExecuteResponse,
  ReportScheduleRead,
  SavedReportRead,
} from "@/lib/api/types";
import { InterpretationPanel } from "@/components/InterpretationPanel";
import { VisualizationRenderer } from "@/components/VisualizationRenderer";

function fmtDate(iso: string | null | undefined) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("ru-RU", { year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function previewToResult(report: SavedReportRead): QueryResult | null {
  const p = report.last_result_preview;
  if (!p || typeof p !== "object") return null;
  const o = p as Record<string, unknown>;
  if (!Array.isArray(o.columns)) return null;
  return {
    columns: o.columns as string[],
    rows: (Array.isArray(o.rows) ? o.rows : []) as Record<string, unknown>[],
    row_count: typeof o.row_count === "number" ? o.row_count : Number(o.preview_row_count) || 0,
  };
}

function ResultBlock({ exec }: { exec: ReportExecuteResponse }) {
  const cols = exec.result.columns || [];
  const rows = exec.result.rows || [];
  const show = rows.slice(0, 50);
  return (
    <div className="rounded-2xl border border-border bg-card">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-6 py-5">
        <div>
          <div className="text-sm font-medium">Результат запуска</div>
          <div className="mt-1 text-xs text-muted2">
            строк: <span className="font-mono text-accent2">{exec.result.row_count}</span>
          </div>
        </div>
        <div className="rounded-xl border border-border bg-[#0b1410] px-4 py-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-accent2">SQL</div>
          <div className="mt-2 max-w-[620px] overflow-auto font-mono text-xs leading-6 text-[rgb(126,216,160)]">
            {exec.sql}
          </div>
        </div>
      </div>
      <div className="space-y-4 px-6 py-5">
        <InterpretationPanel interpretation={exec.interpretation} />
        <VisualizationRenderer result={exec.result} hint={exec.visualization ?? null} />
        <details className="rounded-xl border border-border bg-card2/40 px-4 py-3">
          <summary className="cursor-pointer text-xs font-semibold uppercase tracking-[0.18em] text-muted2">
            Таблица (до 50 строк)
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

function StoredResultBlock({ report }: { report: SavedReportRead }) {
  const res = previewToResult(report);
  if (!res) return null;
  const cols = res.columns || [];
  const rows = res.rows || [];
  const show = rows.slice(0, 50);
  const interp = report.last_interpretation as QueryInterpretation | null | undefined;
  const viz = report.last_visualization as QueryVisualization | null | undefined;
  return (
    <div className="rounded-2xl border border-border bg-card">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-6 py-5">
        <div>
          <div className="text-sm font-medium">Последний сохранённый результат</div>
          <div className="mt-1 text-xs text-muted2">
            {report.last_run_at ? (
              <>
                {fmtDate(report.last_run_at)} · строк:{" "}
                <span className="font-mono text-accent2">{report.last_row_count ?? res.row_count ?? show.length}</span>
              </>
            ) : (
              <>
                строк: <span className="font-mono text-accent2">{report.last_row_count ?? res.row_count ?? show.length}</span>
              </>
            )}
          </div>
        </div>
        <span className="rounded-xl border border-border bg-card2 px-4 py-2 text-xs text-muted2">
          до следующего запуска
        </span>
      </div>
      <div className="space-y-4 px-6 py-5">
        <InterpretationPanel interpretation={interp ?? null} />
        <VisualizationRenderer result={res} hint={viz ?? null} />
        <details className="rounded-xl border border-border bg-card2/40 px-4 py-3" open>
          <summary className="cursor-pointer text-xs font-semibold uppercase tracking-[0.18em] text-muted2">
            Таблица (до 50 строк)
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

export default function ReportDetailsPage() {
  const { token } = useAuth();
  const params = useParams<{ id: string }>();
  const router = useRouter();

  const reportId = useMemo(() => Number(params.id), [params.id]);
  const [report, setReport] = useState<SavedReportRead | null>(null);
  const [exec, setExec] = useState<ReportExecuteResponse | null>(null);
  const [schedules, setSchedules] = useState<ReportScheduleRead[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [schedForm, setSchedForm] = useState({
    frequency: "weekly" as "daily" | "weekly" | "monthly",
    timezone: "UTC",
    hour: 9,
    minute: 0,
    day_of_week: 0,
  });

  const loadSchedules = useCallback(() => {
    if (!token || !Number.isFinite(reportId)) return;
    void apiSchedulesList(token, { report_id: reportId, limit: 50 }).then(setSchedules).catch(() => setSchedules([]));
  }, [token, reportId]);

  useEffect(() => {
    if (!token || !Number.isFinite(reportId)) return;
    setError(null);
    setReport(null);
    void apiReportGet(token, reportId)
      .then((r) => {
        setReport(r);
        setEditTitle(r.title);
        setEditDescription(r.description || "");
      })
      .catch((e: unknown) =>
        setError(typeof (e as { message?: string })?.message === "string" ? (e as { message: string }).message : "Не удалось загрузить отчёт")
      );
  }, [token, reportId]);

  useEffect(() => {
    loadSchedules();
  }, [loadSchedules]);

  async function run() {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      const r = await apiReportExecute(token, reportId, {});
      setExec(r);
      setReport(r.report);
      setEditTitle(r.report.title);
      setEditDescription(r.report.description || "");
    } catch (e: unknown) {
      setError(typeof (e as { message?: string })?.message === "string" ? (e as { message: string }).message : "Не удалось выполнить отчёт");
    } finally {
      setBusy(false);
    }
  }

  async function saveMeta() {
    if (!token || !report) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await apiReportPatch(token, reportId, {
        title: editTitle.trim() || report.title,
        description: editDescription.trim() ? editDescription.trim() : null,
      });
      setReport(updated);
      setEditing(false);
    } catch (e: unknown) {
      setError(typeof (e as { message?: string })?.message === "string" ? (e as { message: string }).message : "Не удалось сохранить изменения");
    } finally {
      setBusy(false);
    }
  }

  async function del() {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      await apiReportDelete(token, reportId);
      router.replace("/reports");
    } catch (e: unknown) {
      setError(typeof (e as { message?: string })?.message === "string" ? (e as { message: string }).message : "Не удалось удалить отчёт");
    } finally {
      setBusy(false);
    }
  }

  async function createSchedule() {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      await apiScheduleCreate(token, {
        report_id: reportId,
        frequency: schedForm.frequency,
        timezone: schedForm.timezone,
        hour: schedForm.hour,
        minute: schedForm.minute,
        day_of_week: schedForm.frequency === "weekly" ? schedForm.day_of_week : undefined,
        default_max_rows: 100,
        is_enabled: true,
      });
      loadSchedules();
    } catch (e: unknown) {
      setError(typeof (e as { message?: string })?.message === "string" ? (e as { message: string }).message : "Не удалось создать расписание");
    } finally {
      setBusy(false);
    }
  }

  async function toggleSchedule(s: ReportScheduleRead) {
    if (!token) return;
    setBusy(true);
    try {
      await apiSchedulePatch(token, s.id, { is_enabled: !s.is_enabled });
      loadSchedules();
    } finally {
      setBusy(false);
    }
  }

  async function runScheduleNow(id: number) {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      await apiScheduleRunNow(token, id);
      loadSchedules();
    } catch (e: unknown) {
      setError(typeof (e as { message?: string })?.message === "string" ? (e as { message: string }).message : "Не удалось выполнить по расписанию");
    } finally {
      setBusy(false);
    }
  }

  async function downloadExcel() {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      const out = await apiReportExportExcel(token, reportId, { max_rows: 1000 });
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
    } finally {
      setBusy(false);
    }
  }

  async function removeSchedule(id: number) {
    if (!token) return;
    if (!window.confirm("Удалить расписание?")) return;
    setBusy(true);
    try {
      await apiScheduleDelete(token, id);
      loadSchedules();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-1 flex-col overflow-y-auto px-8 py-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          {editing ? (
            <div className="space-y-2">
              <input
                className="h-10 w-[520px] max-w-full rounded-xl border border-border2 bg-card px-4 text-base font-medium outline-none focus:border-[rgba(108,255,114,0.3)]"
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
                placeholder="Название отчёта"
              />
              <textarea
                className="min-h-[74px] w-[520px] max-w-full rounded-xl border border-border2 bg-card px-4 py-3 text-sm text-muted outline-none focus:border-[rgba(108,255,114,0.3)]"
                value={editDescription}
                onChange={(e) => setEditDescription(e.target.value)}
                placeholder="Описание (необязательно)"
              />
            </div>
          ) : (
            <>
              <div className="text-lg font-medium">{report ? report.title : "Отчёт"}</div>
              <div className="mt-1 text-sm text-muted">{report ? report.description || report.question : "Загрузка…"}</div>
              {report?.last_run_at ? (
                <div className="mt-2 text-xs text-muted2">
                  последний запуск: <span className="font-mono text-foreground/90">{fmtDate(report.last_run_at)}</span>
                  {report.last_row_count != null ? (
                    <>
                      {" "}
                      · строк: <span className="font-mono text-accent2">{report.last_row_count}</span>
                    </>
                  ) : null}
                </div>
              ) : null}
            </>
          )}
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => {
              if (!report) return;
              if (!editing) {
                setEditTitle(report.title);
                setEditDescription(report.description || "");
              }
              setEditing((v) => !v);
            }}
            disabled={busy || !report}
            className={cn(
              "rounded-xl border border-border2 bg-card px-5 py-2.5 text-sm font-medium text-muted",
              "transition-colors hover:border-[rgba(108,255,114,0.25)] hover:text-foreground",
              "disabled:cursor-not-allowed disabled:opacity-50"
            )}
          >
            {editing ? "Закрыть" : "Редактировать"}
          </button>
          {editing ? (
            <button
              type="button"
              onClick={() => void saveMeta()}
              disabled={busy || !report}
              className={cn(
                "rounded-xl bg-accent px-5 py-2.5 text-sm font-semibold text-[#0a1a0c]",
                "transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              )}
            >
              {busy ? "Сохраняем…" : "Сохранить"}
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => void run()}
            disabled={busy}
            className={cn(
              "rounded-xl bg-accent px-5 py-2.5 text-sm font-semibold text-[#0a1a0c]",
              "transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            )}
          >
            {busy ? "Подождите…" : "Запустить сейчас"}
          </button>
          <button
            type="button"
            onClick={() => void downloadExcel()}
            disabled={busy}
            className={cn(
              "rounded-xl border border-border2 bg-card px-5 py-2.5 text-sm font-medium text-muted",
              "transition-colors hover:border-[rgba(108,255,114,0.25)] hover:text-foreground",
              "disabled:cursor-not-allowed disabled:opacity-50"
            )}
            title="Перезапуск SQL и выгрузка до 1000 строк"
          >
            Скачать Excel
          </button>
          <button
            type="button"
            onClick={() => void del()}
            disabled={busy}
            className={cn(
              "rounded-xl border border-[rgba(255,107,107,0.35)] bg-dangerbg px-5 py-2.5 text-sm font-medium text-danger",
              "transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            )}
          >
            Удалить
          </button>
        </div>
      </div>

      {error ? (
        <div className="mt-6 rounded-2xl border border-[rgba(255,107,107,0.35)] bg-dangerbg px-6 py-4 text-sm text-danger">
          {error}
        </div>
      ) : null}

      <div className="mt-6 rounded-2xl border border-border bg-card px-6 py-5">
        <div className="text-xs font-semibold uppercase tracking-[0.18em] text-muted2">SQL</div>
        <div className="mt-3 overflow-auto font-mono text-xs leading-6 text-[rgb(126,216,160)]">{report?.sql || "…"}</div>
      </div>

      {!exec && report && previewToResult(report) ? (
        <div className="mt-6">
          <StoredResultBlock report={report} />
        </div>
      ) : null}

      <div className="mt-8">
        <div className="text-sm font-medium">Расписания</div>
        <p className="mt-1 text-xs text-muted">
          Автозапуск сохранённого SQL по cron-подобным правилам (проверка на бэкенде каждые N секунд, см. REPORT_SCHEDULER_*).
        </p>
        <div className="mt-4 flex flex-wrap items-end gap-3 rounded-xl border border-border bg-card2/30 p-4">
          <label className="text-xs text-muted2">
            Частота
            <select
              className="mt-1 block h-9 rounded-lg border border-border2 bg-card px-2 text-sm"
              value={schedForm.frequency}
              onChange={(e) =>
                setSchedForm((f) => ({ ...f, frequency: e.target.value as "daily" | "weekly" | "monthly" }))
              }
            >
              <option value="daily">Ежедневно</option>
              <option value="weekly">Еженедельно</option>
              <option value="monthly">Ежемесячно</option>
            </select>
          </label>
          <label className="text-xs text-muted2">
            Часовой пояс
            <input
              className="mt-1 block h-9 w-40 rounded-lg border border-border2 bg-card px-2 text-sm"
              value={schedForm.timezone}
              onChange={(e) => setSchedForm((f) => ({ ...f, timezone: e.target.value }))}
            />
          </label>
          <label className="text-xs text-muted2">
            Час
            <input
              type="number"
              min={0}
              max={23}
              className="mt-1 block h-9 w-16 rounded-lg border border-border2 bg-card px-2 text-sm"
              value={schedForm.hour}
              onChange={(e) => setSchedForm((f) => ({ ...f, hour: Number(e.target.value) }))}
            />
          </label>
          <label className="text-xs text-muted2">
            Минута
            <input
              type="number"
              min={0}
              max={59}
              className="mt-1 block h-9 w-16 rounded-lg border border-border2 bg-card px-2 text-sm"
              value={schedForm.minute}
              onChange={(e) => setSchedForm((f) => ({ ...f, minute: Number(e.target.value) }))}
            />
          </label>
          {schedForm.frequency === "weekly" ? (
            <label className="text-xs text-muted2">
              День недели (0=пн … 6=вс)
              <input
                type="number"
                min={0}
                max={6}
                className="mt-1 block h-9 w-16 rounded-lg border border-border2 bg-card px-2 text-sm"
                value={schedForm.day_of_week}
                onChange={(e) => setSchedForm((f) => ({ ...f, day_of_week: Number(e.target.value) }))}
              />
            </label>
          ) : null}
          <button
            type="button"
            disabled={busy || !report}
            onClick={() => void createSchedule()}
            className="h-9 rounded-lg bg-accent px-4 text-sm font-semibold text-[#0a1a0c] disabled:opacity-50"
          >
            Добавить расписание
          </button>
        </div>

        {schedules === null ? (
          <div className="mt-4 text-sm text-muted">Загрузка расписаний…</div>
        ) : schedules.length === 0 ? (
          <div className="mt-4 text-sm text-muted">Нет расписаний для этого отчёта.</div>
        ) : (
          <ul className="mt-4 space-y-3">
            {schedules.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3">
                <div className="text-sm">
                  <span className="font-mono text-accent2">#{s.id}</span> · {s.frequency} · {s.timezone} · {s.hour}:
                  {String(s.minute).padStart(2, "0")}
                  {s.day_of_week != null ? ` · день недели ${s.day_of_week}` : ""}
                  <div className="mt-1 text-xs text-muted2">
                    следующий: {fmtDate(s.next_run_at)} · последний: {fmtDate(s.last_run_at)} ·{" "}
                    {s.is_enabled ? <span className="text-accent2">вкл</span> : <span className="text-muted">выкл</span>}
                    {s.last_status ? ` · ${s.last_status}` : ""}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void runScheduleNow(s.id)}
                    className="rounded-lg border border-border2 px-3 py-1.5 text-xs hover:border-[rgba(108,255,114,0.35)]"
                  >
                    Запустить сейчас
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void toggleSchedule(s)}
                    className="rounded-lg border border-border2 px-3 py-1.5 text-xs"
                  >
                    {s.is_enabled ? "Выключить" : "Включить"}
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void removeSchedule(s.id)}
                    className="rounded-lg border border-[rgba(255,107,107,0.35)] px-3 py-1.5 text-xs text-danger"
                  >
                    Удалить
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {exec ? (
        <div className="mt-6">
          <ResultBlock exec={exec} />
        </div>
      ) : report && previewToResult(report) ? null : (
        <div className="mt-6 rounded-2xl border border-border bg-card px-6 py-10 text-center text-sm text-muted">
          Запустите отчёт, чтобы увидеть актуальный результат. После сохранения отчёта последний удачный результат остаётся на странице выше.
        </div>
      )}
    </div>
  );
}
