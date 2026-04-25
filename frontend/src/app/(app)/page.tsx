"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { cn } from "@/lib/cn";
import { useAuth } from "@/context/AuthContext";
import { apiAsk } from "@/lib/api/analytics";
import { apiReportSave } from "@/lib/api/reports";
import type { AskResponse, ClarificationOption } from "@/lib/api/types";
import { InterpretationPanel } from "@/components/InterpretationPanel";
import { VisualizationRenderer } from "@/components/VisualizationRenderer";
import {
  getLocalSession,
  newLocalSessionId,
  sessionTitleFromMessages,
  upsertLocalSession,
  type LocalAnalystMessage,
} from "@/lib/localAnalystSessions";

type ChatMessage = LocalAnalystMessage;

type ChatState =
  | { kind: "welcome" }
  | { kind: "loading"; question: string; startedAt: number }
  | { kind: "result" }
  | { kind: "blocked" };

function uid() {
  return Math.random().toString(16).slice(2) + Date.now().toString(16);
}

function isRecord(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null;
}

function unwrapFastApiDetail(err: unknown): unknown {
  if (!isRecord(err)) return undefined;
  const body = err.detail;
  if (body === undefined || body === null) return undefined;
  if (isRecord(body) && "detail" in body) return body.detail;
  return body;
}

function extractBlockedReasons(err: unknown): { title: string; reasons: string[]; debugSql?: string } {
  const fallback = { title: "Запрос не выполнен", reasons: ["Политика безопасности не позволила выполнить запрос."] };
  if (!isRecord(err)) return fallback;

  const raw = unwrapFastApiDetail(err);
  if (raw === undefined || raw === null) {
    const msg = typeof err.message === "string" ? err.message.trim() : "";
    if (msg && msg !== "Request failed" && !msg.startsWith("[object ")) {
      return { title: "Запрос не выполнен", reasons: [msg] };
    }
    return fallback;
  }

  if (typeof raw === "string" && raw.trim()) {
    return { title: "Запрос не выполнен", reasons: [raw.trim()] };
  }

  if (Array.isArray(raw)) {
    const reasons = raw.map(String).filter(Boolean);
    return {
      title: "Запрос не выполнен",
      reasons: reasons.length ? reasons : fallback.reasons,
    };
  }

  if (isRecord(raw)) {
    const reasons: string[] = [];
    const br = raw.blocked_reason;
    if (typeof br === "string" && br.trim()) reasons.push(br.trim());
    const errors = raw.errors;
    if (Array.isArray(errors)) reasons.push(...errors.map(String).filter(Boolean));
    if (typeof raw.message === "string" && raw.message.trim()) reasons.push(raw.message.trim());
    const cr = raw.confidence_reason;
    if (typeof cr === "string" && cr.trim()) reasons.push(`Оценка: ${cr.trim()}`);
    const debugSql = typeof raw.sql === "string" && raw.sql.trim() ? raw.sql.trim() : undefined;
    const uniq = [...new Set(reasons.map((s) => s.trim()).filter(Boolean))];
    return {
      title: "Запрос не выполнен",
      reasons: uniq.length ? uniq : fallback.reasons,
      debugSql,
    };
  }

  return fallback;
}

function LoadingStages({ startedAt }: { startedAt: number }) {
  const [t, setT] = useState(0);
  useEffect(() => {
    const id = window.setInterval(() => setT(Date.now() - startedAt), 250);
    return () => window.clearInterval(id);
  }, [startedAt]);

  const steps = [
    { title: "Разбор запроса", sub: "Определяем сущности и период" },
    { title: "Проверка безопасности", sub: "Только READ-ONLY операции" },
    { title: "Формирование SQL", sub: "Подбор таблицы incity и связанных датасетов" },
    { title: "Выполнение", sub: "Запрос к базе данных" },
    { title: "Подготовка результата", sub: "Форматируем ответ и таблицу" },
  ];
  const activeIdx = Math.min(Math.floor(t / 900), steps.length - 1);

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto border-r border-border px-8 py-8">
      <div>
        <div className="text-xs font-semibold uppercase tracking-[0.18em] text-muted2">Выполняется</div>
        <div className="mt-2 h-1 rounded bg-card2">
          <div
            className="h-full rounded bg-accent transition-[width]"
            style={{ width: `${Math.min(100, 20 + activeIdx * 20)}%` }}
          />
        </div>
      </div>

      <div className="mt-2 space-y-3">
        {steps.map((s, idx) => {
          const done = idx < activeIdx;
          const active = idx === activeIdx;
          return (
            <div key={s.title} className="flex gap-4 py-2">
              <div
                className={cn(
                  "mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-full border",
                  done && "border-[rgba(108,255,114,0.4)] bg-accentbg",
                  active && "border-accent bg-card",
                  !done && !active && "border-border2 bg-card opacity-50"
                )}
              >
                {done ? (
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                    <path
                      d="M3 8l3 3 7-7"
                      stroke="var(--accent)"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                ) : (
                  <span className={cn("h-2 w-2 rounded-full", active ? "bg-accent" : "bg-muted2")} />
                )}
              </div>
              <div className="min-w-0 pt-1">
                <div className={cn("text-sm font-medium", done ? "text-accent2" : active ? "text-foreground" : "text-muted2")}>
                  {s.title}
                </div>
                <div className={cn("mt-1 text-xs leading-5", active ? "text-muted" : "text-muted2")}>{s.sub}</div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function ChatPage() {
  const { token, user } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const sessionFromUrl = searchParams.get("session");

  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [state, setState] = useState<ChatState>({ kind: "welcome" });
  const [pendingClarification, setPendingClarification] = useState<AskResponse | null>(null);
  const [savingReportId, setSavingReportId] = useState<string | null>(null);
  const skipNextHydrate = useRef(false);
  /** Пока URL ещё не обновился после первого сообщения — для сохранения в localStorage */
  const persistSessionIdRef = useRef<string | null>(null);

  const userId = user?.id ?? null;

  const placeholder = useMemo(
    () => "Например: покажи выручку по городам за последние 30 дней",
    []
  );

  useEffect(() => {
    if (userId == null) {
      setMessages([]);
      return;
    }
    if (!sessionFromUrl) {
      persistSessionIdRef.current = null;
      setMessages([]);
      return;
    }
    if (skipNextHydrate.current) {
      skipNextHydrate.current = false;
      persistSessionIdRef.current = sessionFromUrl;
      return;
    }
    persistSessionIdRef.current = sessionFromUrl;
    const doc = getLocalSession(userId, sessionFromUrl);
    setMessages(doc?.messages ?? []);
    setPendingClarification(null);
  }, [userId, sessionFromUrl]);

  useEffect(() => {
    const sid = sessionFromUrl ?? persistSessionIdRef.current;
    if (userId == null || !sid) return;
    if (messages.length === 0 && !pendingClarification) return;
    const t = window.setTimeout(() => {
      upsertLocalSession(userId, {
        id: sid,
        title: sessionTitleFromMessages(messages),
        updatedAt: Date.now(),
        messages,
      });
    }, 280);
    return () => window.clearTimeout(t);
  }, [messages, userId, sessionFromUrl, pendingClarification]);

  function autosize(el: HTMLTextAreaElement) {
    el.style.height = "0px";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }

  function scrollToBottom(smooth = true) {
    const el = listRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: smooth ? "smooth" : "auto" });
  }

  async function askQuestion(question: string, templateParams: Record<string, unknown> = {}) {
    if (!token) return;
    const q = question.trim();
    if (!q) return;

    const startedAt = Date.now();
    setState({ kind: "loading", question: q, startedAt });
    setTimeout(() => scrollToBottom(false), 0);

    try {
      const resp = await apiAsk(token, {
        question: q,
        template_params: templateParams,
      });
      if (resp.needs_clarification && resp.clarification) {
        setPendingClarification(resp);
      } else {
        setPendingClarification(null);
        setMessages((prev) => [...prev, { id: uid(), role: "assistant", createdAt: Date.now(), response: resp }]);
      }
      setState({ kind: "result" });
      setTimeout(() => scrollToBottom(true), 50);
    } catch (e) {
      setPendingClarification(null);
      const b = extractBlockedReasons(e);
      setMessages((prev) => [
        ...prev,
        {
          id: uid(),
          role: "assistant",
          createdAt: Date.now(),
          blocked: { title: b.title, reasons: b.reasons, debugSql: b.debugSql },
        },
      ]);
      setState({ kind: "blocked" });
      setTimeout(() => scrollToBottom(true), 50);
    }
  }

  function sendUserTurn(
    userBubbleText: string,
    apiQuestion: string,
    templateParams: Record<string, unknown> = {}
  ) {
    if (!token) return;
    const display = userBubbleText.trim();
    const q = apiQuestion.trim();
    if (!display || !q) return;

    setPendingClarification(null);
    const startedAt = Date.now();
    const userMsg: ChatMessage = { id: uid(), role: "user", text: display, createdAt: startedAt };

    let sid = sessionFromUrl;
    if (!sid && userId != null) {
      sid = newLocalSessionId();
      persistSessionIdRef.current = sid;
      const nextMessages: ChatMessage[] = [...messages, userMsg];
      upsertLocalSession(userId, {
        id: sid,
        title: sessionTitleFromMessages(nextMessages),
        updatedAt: Date.now(),
        messages: nextMessages,
      });
      skipNextHydrate.current = true;
      router.replace(`/?session=${sid}`);
      setMessages(nextMessages);
    } else {
      setMessages((prev) => [...prev, userMsg]);
    }

    setValue("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "46px";
    }
    setTimeout(() => scrollToBottom(false), 0);
    void askQuestion(q, templateParams);
  }

  function runQuestionFromInput(raw: string) {
    const q = raw.trim();
    if (!q) return;
    sendUserTurn(q, q, {});
  }

  function runClarificationPick(option: ClarificationOption) {
    setPendingClarification(null);
    sendUserTurn(option.label, option.question, option.template_params ?? {});
  }

  async function handleSaveAskResponse(messageId: string, r: AskResponse) {
    if (!token) return;
    const title = window.prompt("Название отчёта", "Мой отчёт");
    if (!title?.trim()) return;
    setSavingReportId(messageId);
    try {
      if (typeof r.history_id === "number" && r.history_id > 0) {
        await apiReportSave(token, { title: title.trim(), history_id: r.history_id });
      } else {
        await apiReportSave(token, {
          title: title.trim(),
          question: r.question,
          sql: r.sql,
          source: r.source || "llm",
          template_id: r.template_id ?? undefined,
          template_title: r.template_title ?? undefined,
          default_max_rows: 100,
          result: r.result,
          interpretation: r.interpretation ?? undefined,
          visualization: r.visualization ?? undefined,
        });
      }
    } catch {
      window.alert("Не удалось сохранить отчёт");
    } finally {
      setSavingReportId(null);
    }
  }

  useLayoutEffect(() => {
    scrollToBottom(false);
    // scrollToBottom читает listRef; зависимость — факт перерисовки списка / смены сессии
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages, sessionFromUrl]);

  const urlBootDone = useRef(false);
  useEffect(() => {
    if (!token || urlBootDone.current) return;
    if (typeof window === "undefined") return;
    const url = new URL(window.location.href);
    const q = url.searchParams.get("q");
    if (!q) return;
    urlBootDone.current = true;
    url.searchParams.delete("q");
    window.history.replaceState({}, "", url.toString());
    sendUserTurn(q, q, {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const clar = pendingClarification?.clarification;

  return (
    <div className="relative flex flex-1 flex-col overflow-hidden">
      <div className="flex flex-1 overflow-hidden">
        <div ref={listRef} className="flex flex-1 flex-col gap-4 overflow-y-auto px-8 py-8 pb-40">
          {messages.length === 0 && state.kind !== "loading" ? (
            <div className="flex flex-1 items-center justify-center px-2">
              <div className="w-full max-w-2xl">
                <div className="rounded-2xl border border-border bg-card p-8">
                  <div className="text-lg font-medium">Аналитика</div>
                  <div className="mt-2 text-sm leading-6 text-muted">
                    Задайте вопрос на русском — Толмач вернёт SQL, пояснение и результат (только безопасные SELECT). Сессии в боковой
                    панели удобно переключать; отчёты и история запросов на сервере — в разделе «Отчёты».
                  </div>
                </div>
              </div>
            </div>
          ) : null}

          {messages.map((m) => {
            if (m.role === "user") {
              return (
                <div key={m.id} className="tolmach-fade-up flex justify-end">
                  <div className="max-w-[820px] rounded-2xl bg-accentbg px-5 py-4 text-sm text-foreground">{m.text}</div>
                </div>
              );
            }
            if (m.blocked) {
              return (
                <div key={m.id} className="tolmach-fade-up flex justify-start">
                  <div className="w-full max-w-[920px] rounded-2xl border border-[rgba(255,107,107,0.35)] bg-dangerbg px-6 py-5">
                    <div className="flex items-center gap-2 text-sm font-medium text-danger">
                      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                        <path
                          d="M8 2l6 10H2L8 2z"
                          stroke="currentColor"
                          strokeWidth="1.4"
                          strokeLinejoin="round"
                        />
                        <path d="M8 7v3M8 12v.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
                      </svg>
                      {m.blocked.title}
                    </div>
                    <div className="mt-2 space-y-1 text-sm text-[rgba(204,136,136,1)]">
                      {m.blocked.reasons.map((r, idx) => (
                        <div key={idx}>{r}</div>
                      ))}
                    </div>
                    {m.blocked.debugSql ? (
                      <details className="mt-3 rounded-lg border border-border bg-[#0b1410] px-3 py-2">
                        <summary className="cursor-pointer text-[10px] font-semibold uppercase tracking-[0.14em] text-muted2">
                          SQL из ответа сервера
                        </summary>
                        <pre className="mt-2 max-h-40 overflow-auto font-mono text-[11px] leading-relaxed text-[rgb(126,216,160)] whitespace-pre-wrap">
                          {m.blocked.debugSql}
                        </pre>
                      </details>
                    ) : null}
                  </div>
                </div>
              );
            }
            if (m.response && !m.response.needs_clarification) {
              const r = m.response;
              const canSave = r.guardrails?.is_valid === true && Boolean(r.sql?.trim());
              return (
                <div key={m.id} className="tolmach-fade-up flex justify-start">
                  <div className={cn("w-full max-w-[1020px]", state.kind === "loading" && "opacity-40 blur-[0.2px]")}>
                    <div className="overflow-hidden rounded-2xl border border-border bg-card shadow-sm">
                      <div className="border-b border-border bg-card2/40 px-6 py-4">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div>
                            <div className="text-sm font-medium text-foreground">Ответ</div>
                            <div className="mt-1 text-xs text-muted">
                              SQL выполнен в режиме только чтения.
                              {typeof r.confidence === "number" ? (
                                <span className="ml-2 font-mono text-accent2">
                                  уверенность: {r.confidence.toFixed(2)}
                                </span>
                              ) : null}
                              {r.confidence_reason ? (
                                <span className="ml-2 text-muted2">({r.confidence_reason})</span>
                              ) : null}
                            </div>
                          </div>
                          {canSave ? (
                            <button
                              type="button"
                              disabled={savingReportId === m.id}
                              onClick={() => void handleSaveAskResponse(m.id, r)}
                              className="rounded-lg border border-[rgba(108,255,114,0.35)] bg-accentbg px-3 py-1.5 text-xs font-medium text-accent hover:opacity-90 disabled:opacity-50"
                            >
                              {savingReportId === m.id ? "Сохранение…" : "Сохранить отчёт"}
                            </button>
                          ) : null}
                        </div>
                      </div>
                      <div className="space-y-4 px-6 py-5">
                        <InterpretationPanel interpretation={r.interpretation} />
                        <details className="group rounded-xl border border-border bg-[#0b1410] px-4 py-3">
                          <summary className="cursor-pointer text-xs font-semibold uppercase tracking-[0.18em] text-accent2">
                            SQL <span className="text-muted2 group-open:hidden"> — показать</span>
                          </summary>
                          <pre className="mt-3 overflow-auto font-mono text-xs leading-6 text-[rgb(126,216,160)] whitespace-pre-wrap">
                            {r.sql}
                          </pre>
                        </details>
                        <VisualizationRenderer result={r.result} hint={r.visualization ?? null} />
                      </div>
                    </div>
                  </div>
                </div>
              );
            }
            return null;
          })}
          <div />
        </div>

        {state.kind === "loading" ? (
          <div className="hidden w-[620px] shrink-0 grid-cols-2 overflow-hidden border-l border-border bg-background lg:grid">
            <LoadingStages startedAt={state.startedAt} />
            <div className="flex h-full flex-col gap-4 overflow-y-auto px-8 py-8">
              <div className="text-xs font-semibold uppercase tracking-[0.18em] text-muted2">Проверка</div>
              <div className="rounded-xl border border-border bg-card px-5 py-4">
                <div className="text-sm font-medium">Запрос обрабатывается</div>
                <div className="mt-2 text-sm leading-6 text-muted">Проверка безопасности и выполнение в PostgreSQL.</div>
              </div>
            </div>
          </div>
        ) : null}
      </div>

      {clar && pendingClarification ? (
        <div className="pointer-events-auto fixed inset-x-0 bottom-[88px] z-20 mx-auto w-full max-w-3xl px-4 md:bottom-[100px]">
          <div className="rounded-2xl border border-[rgba(108,255,114,0.35)] bg-panel/95 px-5 py-4 shadow-lg backdrop-blur-md">
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-muted2">Нужно уточнение</div>
            <p className="mt-2 text-sm leading-6 text-foreground">{clar.message_ru}</p>
            {pendingClarification.notes ? (
              <p className="mt-1 text-xs text-muted">{pendingClarification.notes}</p>
            ) : null}
            <div className="mt-3 flex flex-wrap gap-2">
              {clar.options.map((option, idx) => (
                <button
                  key={`${option.label}-${idx}`}
                  type="button"
                  disabled={state.kind === "loading"}
                  onClick={() => runClarificationPick(option)}
                  className={cn(
                    "rounded-xl border border-border2 bg-card px-4 py-2 text-left text-sm text-foreground transition-colors",
                    "hover:border-[rgba(108,255,114,0.45)] disabled:cursor-not-allowed disabled:opacity-50"
                  )}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      ) : null}

      <div className="sticky bottom-0 z-10 border-t border-border bg-panel px-6 py-4">
        <div className="mx-auto flex w-full max-w-5xl items-end gap-3">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => {
              setValue(e.target.value);
              autosize(e.target);
            }}
            placeholder={placeholder}
            className={cn(
              "min-h-[46px] w-full resize-none rounded-xl border border-border2 bg-card px-4 py-3 text-sm text-foreground outline-none",
              "placeholder:text-muted2 focus:border-[rgba(108,255,114,0.5)] disabled:opacity-60"
            )}
            rows={1}
          />
          <button
            type="button"
            disabled={!value.trim() || state.kind === "loading"}
            onClick={() => runQuestionFromInput(value)}
            className={cn(
              "h-[46px] shrink-0 rounded-xl bg-accent px-5 text-sm font-semibold text-[#0a1a0c]",
              "transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            )}
          >
            {state.kind === "loading" ? "Ждём…" : "Выполнить"}
          </button>
          <button
            type="button"
            onClick={() => scrollToBottom(true)}
            className="hidden h-[46px] shrink-0 rounded-xl border border-border2 bg-transparent px-4 text-sm text-muted hover:text-foreground md:block"
            title="Вниз"
          >
            ↓
          </button>
        </div>
      </div>
    </div>
  );
}
