"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { cn } from "@/lib/cn";
import { useAuth } from "@/context/AuthContext";
import { apiScheduleDelete, apiSchedulePatch, apiScheduleRunNow, apiSchedulesList } from "@/lib/api/schedules";
import type { ReportScheduleRead, ReportScheduleUpdateRequest } from "@/lib/api/types";

type Filter = "all" | "active" | "paused";

function pad2(n: number) {
  return String(n).padStart(2, "0");
}

function fmtNext(iso: string | null | undefined) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("ru-RU", { month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function fmtLast(iso: string | null | undefined) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("ru-RU", { month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function freqLabel(f: string) {
  if (f === "daily") return "Ежедневно";
  if (f === "weekly") return "Еженедельно";
  if (f === "monthly") return "Ежемесячно";
  return f;
}

function statusTone(s: ReportScheduleRead) {
  const st = (s.last_status || "").toLowerCase();
  if (!st) return "muted";
  if (st === "ok" || st === "success") return "ok";
  if (st.includes("warn") || st.includes("slow")) return "warn";
  return "err";
}

function shortReportTag(s: ReportScheduleRead) {
  const title = s.report?.title?.trim();
  if (title) return title;
  return `Отчёт #${s.report_id}`;
}

const RU_WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"] as const;

function deepEq(a: unknown, b: unknown) {
  try {
    return JSON.stringify(a) === JSON.stringify(b);
  } catch {
    return false;
  }
}

export default function SchedulesPage() {
  const { token } = useAuth();

  const [items, setItems] = useState<ReportScheduleRead[] | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [busyId, setBusyId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState<ReportScheduleUpdateRequest>({});

  async function load() {
    if (!token) return;
    setError(null);
    const list = await apiSchedulesList(token, { limit: 200 });
    setItems(list);
    if (selectedId != null) {
      const still = list.find((x) => x.id === selectedId);
      if (!still) setSelectedId(null);
    }
  }

  useEffect(() => {
    if (!token) return;
    setItems(null);
    void load().catch((e: any) => {
      setItems([]);
      setError(typeof e?.message === "string" ? e.message : "Не удалось загрузить расписания");
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const filtered = useMemo(() => {
    const all = items ?? [];
    if (filter === "active") return all.filter((s) => s.is_enabled);
    if (filter === "paused") return all.filter((s) => !s.is_enabled);
    return all;
  }, [items, filter]);

  const selected = useMemo(
    () => (items ?? []).find((s) => s.id === selectedId) ?? null,
    [items, selectedId]
  );

  useEffect(() => {
    if (!selected) {
      setDraft({});
      return;
    }
    setDraft({
      frequency: selected.frequency as any,
      timezone: selected.timezone,
      hour: selected.hour,
      minute: selected.minute,
      day_of_week: selected.day_of_week ?? null,
      day_of_month: selected.day_of_month ?? null,
      params: selected.params ?? {},
      default_max_rows: selected.default_max_rows ?? null,
      is_enabled: selected.is_enabled,
    });
  }, [selectedId]); // намеренно: только при смене выбранного

  const stats = useMemo(() => {
    const all = items ?? [];
    const active = all.filter((s) => s.is_enabled).length;
    const paused = all.filter((s) => !s.is_enabled).length;
    const warn = all.filter((s) => statusTone(s) === "warn" || statusTone(s) === "err").length;
    const next = all
      .filter((s) => s.is_enabled && s.next_run_at)
      .map((s) => new Date(s.next_run_at as string).getTime())
      .filter((t) => Number.isFinite(t))
      .sort((a, b) => a - b)[0];
    return { active, paused, warn, next: next ? new Date(next) : null };
  }, [items]);

  const dirty = useMemo(() => {
    if (!selected) return false;
    const base: ReportScheduleUpdateRequest = {
      frequency: selected.frequency as any,
      timezone: selected.timezone,
      hour: selected.hour,
      minute: selected.minute,
      day_of_week: selected.day_of_week ?? null,
      day_of_month: selected.day_of_month ?? null,
      params: selected.params ?? {},
      default_max_rows: selected.default_max_rows ?? null,
      is_enabled: selected.is_enabled,
    };
    return !deepEq(base, draft);
  }, [selected, draft]);

  async function toggleEnabled(s: ReportScheduleRead) {
    if (!token) return;
    setBusyId(s.id);
    setError(null);
    try {
      const updated = await apiSchedulePatch(token, s.id, { is_enabled: !s.is_enabled });
      setItems((prev) => (prev ?? []).map((x) => (x.id === s.id ? updated : x)));
      if (selectedId === s.id) {
        setDraft((d) => ({ ...d, is_enabled: updated.is_enabled }));
      }
    } catch (e: any) {
      setError(typeof e?.message === "string" ? e.message : "Не удалось обновить расписание");
    } finally {
      setBusyId(null);
    }
  }

  async function runNow(s: ReportScheduleRead) {
    if (!token) return;
    setBusyId(s.id);
    setError(null);
    try {
      await apiScheduleRunNow(token, s.id);
      await load();
    } catch (e: any) {
      setError(typeof e?.message === "string" ? e.message : "Не удалось запустить расписание");
    } finally {
      setBusyId(null);
    }
  }

  async function saveChanges() {
    if (!token || !selected) return;
    setSaving(true);
    setError(null);
    try {
      const payload: ReportScheduleUpdateRequest = { ...draft };
      if (payload.frequency !== "weekly") payload.day_of_week = null;
      if (payload.frequency !== "monthly") payload.day_of_month = null;
      const updated = await apiSchedulePatch(token, selected.id, payload);
      setItems((prev) => (prev ?? []).map((x) => (x.id === selected.id ? updated : x)));
      setSelectedId(updated.id);
      // re-init draft to server truth
      setDraft({
        frequency: updated.frequency as any,
        timezone: updated.timezone,
        hour: updated.hour,
        minute: updated.minute,
        day_of_week: updated.day_of_week ?? null,
        day_of_month: updated.day_of_month ?? null,
        params: updated.params ?? {},
        default_max_rows: updated.default_max_rows ?? null,
        is_enabled: updated.is_enabled,
      });
    } catch (e: any) {
      setError(typeof e?.message === "string" ? e.message : "Не удалось сохранить изменения");
    } finally {
      setSaving(false);
    }
  }

  async function deleteSchedule(s: ReportScheduleRead) {
    if (!token) return;
    if (!window.confirm(`Удалить расписание #${s.id}?`)) return;
    setBusyId(s.id);
    setError(null);
    try {
      await apiScheduleDelete(token, s.id);
      setItems((prev) => (prev ?? []).filter((x) => x.id !== s.id));
      if (selectedId === s.id) setSelectedId(null);
    } catch (e: any) {
      setError(typeof e?.message === "string" ? e.message : "Не удалось удалить расписание");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="border-b border-border bg-panel px-8 py-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-lg font-medium">Расписание автозапусков</div>
            <div className="mt-1 text-sm text-muted">Управление автоматическими отчётами и уведомлениями</div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <div className="rounded-full border border-border bg-card2 px-4 py-1.5 text-sm text-muted">
              активных: <span className="font-mono text-accent2">{items ? stats.active : "…"}</span>
            </div>
            <div className="rounded-full border border-border bg-card2 px-4 py-1.5 text-sm text-muted">
              на паузе: <span className="font-mono text-foreground/90">{items ? stats.paused : "…"}</span>
            </div>
            <div className="rounded-full border border-border bg-card2 px-4 py-1.5 text-sm text-muted">
              проблем:{" "}
              <span className={cn("font-mono", stats.warn ? "text-warn" : "text-accent2")}>
                {items ? stats.warn : "…"}
              </span>
            </div>
            <div className="rounded-full border border-border bg-card2 px-4 py-1.5 text-sm text-muted">
              след. запуск:{" "}
              <span className="font-mono text-foreground/90">{stats.next ? fmtNext(stats.next.toISOString()) : "—"}</span>
            </div>
          </div>
        </div>
      </div>

      <div className="border-b border-border bg-panel px-8 py-4">
        <div className="flex flex-wrap gap-2">
          {(
            [
              { id: "all" as const, label: `Все (${items?.length ?? "…"})` },
              { id: "active" as const, label: `Активные (${items ? stats.active : "…"})` },
              { id: "paused" as const, label: `На паузе (${items ? stats.paused : "…"})` },
            ] as const
          ).map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setFilter(t.id)}
              className={cn(
                "rounded-full border px-4 py-1.5 text-sm transition-colors",
                filter === t.id
                  ? "border-[rgba(108,255,114,0.3)] bg-accentbg text-accent"
                  : "border-border2 text-muted hover:text-foreground"
              )}
            >
              {t.label}
            </button>
          ))}

          <button
            type="button"
            onClick={() => void load().catch(() => null)}
            className="ml-auto rounded-full border border-border2 px-4 py-1.5 text-sm text-muted hover:text-foreground"
          >
            Обновить
          </button>
        </div>
      </div>

      {error ? (
        <div className="mx-8 mt-6 rounded-2xl border border-[rgba(255,107,107,0.35)] bg-dangerbg px-6 py-4 text-sm text-danger">
          {error}
        </div>
      ) : null}

      <div className="flex flex-1 overflow-hidden">
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <div className="grid grid-cols-[2fr_1fr_1.1fr_1.1fr_0.9fr_120px] gap-4 border-b border-border bg-panel px-8 py-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted2">
            <div>Отчёт</div>
            <div>Частота</div>
            <div>Следующий</div>
            <div>Последний</div>
            <div>Статус</div>
            <div />
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto">
            {items === null ? (
              <div className="px-8 py-8 text-sm text-muted">Загрузка расписаний…</div>
            ) : filtered.length ? (
              filtered.map((s) => {
                const selectedRow = s.id === selectedId;
                const tone = statusTone(s);
                const busy = busyId === s.id;
                return (
                  <div
                    key={s.id}
                    className={cn(
                      "grid grid-cols-[2fr_1fr_1.1fr_1.1fr_0.9fr_120px] gap-4 border-b border-border px-8 py-4 transition-colors",
                      "cursor-pointer hover:bg-card/40",
                      selectedRow && "bg-card2/40"
                    )}
                    onClick={() => setSelectedId(s.id)}
                    role="button"
                    tabIndex={0}
                  >
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium text-foreground">{shortReportTag(s)}</div>
                      <div className="mt-1 truncate text-xs text-muted2">
                        #{s.id} · report #{s.report_id} · tz: <span className="font-mono">{s.timezone}</span>
                      </div>
                    </div>

                    <div className="text-sm text-muted">
                      <span className="inline-flex rounded-full bg-card2 px-3 py-1 text-xs text-muted2">{freqLabel(s.frequency)}</span>
                      {s.frequency === "weekly" && s.day_of_week != null ? (
                        <div className="mt-1 text-xs text-muted2">{RU_WEEKDAYS[s.day_of_week]}</div>
                      ) : null}
                      {s.frequency === "monthly" && s.day_of_month != null ? (
                        <div className="mt-1 text-xs text-muted2">{s.day_of_month}-е</div>
                      ) : null}
                    </div>

                    <div className="text-sm text-foreground/90">
                      <div className="font-mono text-xs">{fmtNext(s.next_run_at)}</div>
                      <div className="mt-1 text-xs text-muted2">
                        {pad2(s.hour)}:{pad2(s.minute)}
                      </div>
                    </div>

                    <div className="text-sm text-foreground/90">
                      <div className="font-mono text-xs">{fmtLast(s.last_run_at)}</div>
                      <div className="mt-1 text-xs text-muted2">
                        {s.last_row_count != null ? (
                          <>
                            строк: <span className="font-mono">{s.last_row_count}</span>
                          </>
                        ) : (
                          "—"
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-3">
                      <button
                        type="button"
                        disabled={busy}
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          void toggleEnabled(s);
                        }}
                        className={cn(
                          "rounded-full border px-3 py-1.5 text-xs transition-colors",
                          s.is_enabled
                            ? "border-[rgba(108,255,114,0.3)] bg-accentbg text-accent"
                            : "border-border2 bg-card2 text-muted hover:text-foreground",
                          busy && "opacity-60"
                        )}
                        title={s.is_enabled ? "Поставить на паузу" : "Включить"}
                      >
                        {s.is_enabled ? "Активен" : "Пауза"}
                      </button>

                      <span
                        className={cn(
                          "rounded-full px-2.5 py-1 text-[11px]",
                          tone === "ok"
                            ? "bg-accentbg text-accent2"
                            : tone === "warn"
                              ? "bg-warnbg text-warn"
                              : tone === "err"
                                ? "bg-dangerbg text-danger"
                                : "bg-card2 text-muted2"
                        )}
                        title={s.last_error_message || s.last_status || ""}
                      >
                        {s.last_status || "—"}
                      </span>
                    </div>

                    <div className="flex items-center justify-end gap-2">
                      <Link
                        href={`/reports/${s.report_id}`}
                        onClick={(e) => e.stopPropagation()}
                        className="rounded-lg border border-border2 px-3 py-1.5 text-xs text-muted hover:text-foreground"
                      >
                        К отчёту
                      </Link>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          void runNow(s);
                        }}
                        className={cn(
                          "rounded-lg border border-border2 px-3 py-1.5 text-xs text-muted hover:text-foreground",
                          busy && "opacity-60"
                        )}
                      >
                        Запуск
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          void deleteSchedule(s);
                        }}
                        className={cn(
                          "rounded-lg border border-border2 px-3 py-1.5 text-xs text-muted hover:border-[rgba(255,107,107,0.35)] hover:bg-dangerbg hover:text-danger",
                          busy && "opacity-60"
                        )}
                      >
                        Удалить
                      </button>
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="px-8 py-10 text-center text-sm text-muted">Расписаний нет.</div>
            )}
          </div>
        </div>

        <aside className="hidden w-[420px] shrink-0 flex-col border-l border-border bg-panel lg:flex">
          {selected ? (
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
              <div className="border-b border-border px-6 py-6">
                <div className="text-sm font-medium">{shortReportTag(selected)}</div>
                <div className="mt-2 text-xs text-muted2">
                  #{selected.id} ·{" "}
                  <Link href={`/reports/${selected.report_id}`} className="hover:text-foreground underline-offset-4 hover:underline">
                    отчёт #{selected.report_id}
                  </Link>{" "}
                  · tz: <span className="font-mono">{selected.timezone}</span>
                </div>
              </div>

              <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
                <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted2">Автозапуск</div>

                <div className="mt-3 flex flex-wrap gap-2">
                  {(
                    [
                      { id: "daily" as const, label: "Ежедневно" },
                      { id: "weekly" as const, label: "Еженедельно" },
                      { id: "monthly" as const, label: "Ежемесячно" },
                    ] as const
                  ).map((f) => (
                    <button
                      key={f.id}
                      type="button"
                      onClick={() => setDraft((d) => ({ ...d, frequency: f.id }))}
                      className={cn(
                        "rounded-lg border px-3 py-2 text-sm transition-colors",
                        draft.frequency === f.id
                          ? "border-[rgba(108,255,114,0.3)] bg-accentbg text-accent"
                          : "border-border2 bg-card2 text-muted hover:text-foreground"
                      )}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>

                <div className="mt-4 grid grid-cols-2 gap-3">
                  <label className="rounded-xl border border-border bg-card px-4 py-3">
                    <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted2">Время</div>
                    <div className="mt-2 flex items-center gap-2">
                      <input
                        value={`${pad2(Number(draft.hour ?? selected.hour))}:${pad2(Number(draft.minute ?? selected.minute))}`}
                        onChange={(e) => {
                          const v = e.target.value.trim();
                          const m = v.match(/^(\d{1,2}):(\d{1,2})$/);
                          if (!m) return;
                          const hh = Math.max(0, Math.min(23, Number(m[1])));
                          const mm = Math.max(0, Math.min(59, Number(m[2])));
                          setDraft((d) => ({ ...d, hour: hh, minute: mm }));
                        }}
                        className="w-full rounded-lg border border-border2 bg-panel px-3 py-2 font-mono text-sm text-foreground outline-none focus:border-[rgba(108,255,114,0.3)]"
                        placeholder="08:00"
                        inputMode="numeric"
                      />
                    </div>
                  </label>

                  <label className="rounded-xl border border-border bg-card px-4 py-3">
                    <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted2">Статус</div>
                    <div className="mt-2 flex items-center gap-2">
                      <button
                        type="button"
                        disabled={busyId === selected.id}
                        onClick={() => void toggleEnabled(selected)}
                        className={cn(
                          "w-full rounded-lg border px-3 py-2 text-sm transition-colors",
                          (draft.is_enabled ?? selected.is_enabled)
                            ? "border-[rgba(108,255,114,0.3)] bg-accentbg text-accent"
                            : "border-border2 bg-card2 text-muted hover:text-foreground"
                        )}
                      >
                        {(draft.is_enabled ?? selected.is_enabled) ? "Активен" : "Пауза"}
                      </button>
                    </div>
                  </label>
                </div>

                {draft.frequency === "weekly" ? (
                  <div className="mt-4 rounded-xl border border-border bg-card px-4 py-3">
                    <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted2">День недели</div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {RU_WEEKDAYS.map((d, idx) => (
                        <button
                          key={d}
                          type="button"
                          onClick={() => setDraft((x) => ({ ...x, day_of_week: idx }))}
                          className={cn(
                            "rounded-lg border px-3 py-2 text-sm transition-colors",
                            Number(draft.day_of_week ?? selected.day_of_week ?? 0) === idx
                              ? "border-[rgba(108,255,114,0.3)] bg-accentbg text-accent"
                              : "border-border2 bg-card2 text-muted hover:text-foreground"
                          )}
                        >
                          {d}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}

                {draft.frequency === "monthly" ? (
                  <div className="mt-4 rounded-xl border border-border bg-card px-4 py-3">
                    <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted2">День месяца</div>
                    <div className="mt-3 flex items-center gap-3">
                      <input
                        value={String(Number(draft.day_of_month ?? selected.day_of_month ?? 1))}
                        onChange={(e) => {
                          const v = Number(e.target.value);
                          if (!Number.isFinite(v)) return;
                          const day = Math.max(1, Math.min(31, Math.floor(v)));
                          setDraft((x) => ({ ...x, day_of_month: day }));
                        }}
                        className="w-24 rounded-lg border border-border2 bg-panel px-3 py-2 font-mono text-sm text-foreground outline-none focus:border-[rgba(108,255,114,0.3)]"
                        inputMode="numeric"
                      />
                      <div className="text-sm text-muted2">1–31</div>
                    </div>
                  </div>
                ) : null}

                <div className="mt-6 rounded-xl border border-border bg-card px-4 py-3">
                  <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted2">Последний запуск</div>
                  <div className="mt-2 text-sm text-muted">
                    {selected.last_run_at ? (
                      <>
                        <span className="font-mono text-foreground/90">{fmtLast(selected.last_run_at)}</span>
                        {selected.last_row_count != null ? (
                          <>
                            {" "}
                            · строк: <span className="font-mono text-foreground/90">{selected.last_row_count}</span>
                          </>
                        ) : null}
                        {selected.last_error_message ? (
                          <div className="mt-2 rounded-lg border border-[rgba(255,107,107,0.25)] bg-dangerbg px-3 py-2 text-xs text-danger">
                            {selected.last_error_message}
                          </div>
                        ) : null}
                      </>
                    ) : (
                      "—"
                    )}
                  </div>
                </div>
              </div>

              <div className="border-t border-border px-6 py-5">
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={busyId === selected.id}
                    onClick={() => void runNow(selected)}
                    className={cn(
                      "flex-1 rounded-lg border border-border2 px-4 py-2 text-sm text-muted hover:text-foreground",
                      busyId === selected.id && "opacity-60"
                    )}
                  >
                    Запустить сейчас
                  </button>
                  <button
                    type="button"
                    disabled={!dirty || saving}
                    onClick={() => void saveChanges()}
                    className={cn(
                      "flex-1 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-[#0a1a0c] transition-opacity hover:opacity-90",
                      (!dirty || saving) && "cursor-not-allowed opacity-50"
                    )}
                  >
                    {saving ? "Сохраняем…" : "Сохранить изменения"}
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="px-6 py-10 text-sm text-muted">Выберите расписание слева, чтобы редактировать параметры.</div>
          )}
        </aside>
      </div>
    </div>
  );
}

