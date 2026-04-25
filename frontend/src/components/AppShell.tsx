"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { cn } from "@/lib/cn";
import { useAuth } from "@/context/AuthContext";
import {
  createEmptyLocalSession,
  deleteLocalSession,
  listLocalSessions,
  type LocalAnalystSession,
} from "@/lib/localAnalystSessions";

function initials(nameOrEmail: string | null | undefined) {
  const raw = (nameOrEmail || "").trim();
  if (!raw) return "??";
  const parts = raw.split(/\s+/g).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return raw.slice(0, 2).toUpperCase();
}

function NavButton({ href, label }: { href: string; label: string }) {
  const pathname = usePathname();
  const active = pathname === href || (href !== "/" && pathname?.startsWith(href));
  return (
    <Link
      href={href}
      className={cn(
        "rounded-lg px-3 py-1.5 text-sm transition-colors",
        active ? "bg-accentbg text-accent" : "text-muted hover:text-foreground"
      )}
    >
      {label}
    </Link>
  );
}

function fmtShort(iso: number) {
  return new Date(iso).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Одна строка: заголовок · дата */
function sessionRowLabel(title: string, updatedAt: number) {
  return `${title} · ${fmtShort(updatedAt)}`;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, logout, token } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const activeSessionId = pathname === "/" ? searchParams.get("session") : null;

  const userId = user?.id;
  const [sessions, setSessions] = useState<LocalAnalystSession[]>([]);

  const loadSessions = useCallback(() => {
    if (userId == null) {
      setSessions([]);
      return;
    }
    setSessions(listLocalSessions(userId));
  }, [userId]);

  useEffect(() => {
    loadSessions();
  }, [loadSessions, token]);

  useEffect(() => {
    const onRefresh = () => loadSessions();
    window.addEventListener("tolmach:sessions", onRefresh);
    window.addEventListener("storage", onRefresh);
    return () => {
      window.removeEventListener("tolmach:sessions", onRefresh);
      window.removeEventListener("storage", onRefresh);
    };
  }, [loadSessions]);

  const userInitials = initials(user?.full_name || user?.email || null);

  const [creating, setCreating] = useState(false);

  function handleNewChat() {
    if (userId == null || creating) return;
    setCreating(true);
    try {
      const s = createEmptyLocalSession(userId);
      router.push(`/?session=${s.id}`);
    } finally {
      setCreating(false);
    }
  }

  function handleDeleteSession(e: React.MouseEvent, id: string) {
    e.preventDefault();
    e.stopPropagation();
    if (userId == null) return;
    deleteLocalSession(userId, id);
    if (activeSessionId === id) {
      router.push("/");
    }
    loadSessions();
  }

  return (
    <div className="flex min-h-dvh flex-col bg-background text-foreground">
      <header className="flex h-14 shrink-0 items-center gap-6 border-b border-border bg-panel px-6">
        <div className="flex items-center gap-2">
          <div className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-[#0a1a0c]">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path
                d="M3 8h10M8 3l5 5-5 5"
                stroke="#0a1a0c"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <div className="text-base font-semibold">
            Толмач <span className="ml-1 text-xs font-normal text-muted">by Drivee</span>
          </div>
        </div>

        <nav className="flex flex-1 flex-wrap items-center gap-2">
          <NavButton href="/" label="Аналитика" />
          <NavButton href="/reports" label="Отчёты" />
          <NavButton href="/schedules" label="Расписание" />
          <NavButton href="/templates" label="Шаблоны" />
          <NavButton href="/profile" label="Профиль" />
        </nav>

        <div className="flex items-center gap-3">
          <div className="hidden items-center gap-2 sm:flex">
            <div className="grid h-8 w-8 place-items-center rounded-full bg-accent text-[10px] font-semibold text-[#0a1a0c]">
              {userInitials}
            </div>
            <div className="max-w-[140px] truncate text-xs text-muted2">{user?.email}</div>
          </div>
          <button
            type="button"
            onClick={logout}
            className="rounded-lg border border-border2 px-3 py-1.5 text-sm text-muted hover:text-foreground"
            title="Выйти"
          >
            Выйти
          </button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <aside className="flex w-72 shrink-0 flex-col border-r border-border bg-panel">
          <div className="border-b border-border p-3">
            <button
              type="button"
              onClick={handleNewChat}
              disabled={userId == null || creating}
              className="flex w-full items-center justify-center gap-2 rounded-xl border border-[rgba(108,255,114,0.25)] bg-accentbg px-3 py-2.5 text-sm font-medium text-accent hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
                <path d="M7 1v12M1 7h12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              </svg>
              {creating ? "Создаём…" : "Новый запрос"}
            </button>
          </div>

          <div className="border-b border-border px-3 py-2">
            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted2">Быстрый доступ</div>
            <div className="mt-2 flex flex-col gap-1">
              <Link
                href="/templates"
                className="rounded-lg px-2 py-1.5 text-sm text-muted hover:bg-card2 hover:text-foreground"
              >
                Шаблоны запросов
              </Link>
              <Link
                href="/reports"
                className="rounded-lg px-2 py-1.5 text-sm text-muted hover:bg-card2 hover:text-foreground"
              >
                Сохранённые отчёты
              </Link>
            </div>
          </div>

          <div className="px-4 pb-2 pt-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted2">
            История запросов
          </div>
          <div className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto px-2 pb-2">
            {userId == null ? (
              <div className="rounded-lg border border-border bg-card px-2 py-2 text-xs text-muted">Войдите, чтобы сохранять историю.</div>
            ) : sessions.length ? (
              sessions.map((s) => {
                const active = pathname === "/" && activeSessionId === s.id;
                return (
                  <div key={s.id} className="group relative">
                    <Link
                      href={`/?session=${s.id}`}
                      className={cn(
                        "block rounded-lg border bg-card py-1.5 pl-2 pr-7 text-left transition-colors",
                        active
                          ? "border-[rgba(108,255,114,0.45)] bg-card2"
                          : "border-border hover:border-[rgba(108,255,114,0.25)]"
                      )}
                      title={sessionRowLabel(s.title, s.updatedAt)}
                    >
                      <div className="line-clamp-1 text-xs text-muted">{s.title}</div>
                      <div className="text-[10px] leading-tight text-muted2">{fmtShort(s.updatedAt)}</div>
                    </Link>
                    <button
                      type="button"
                      onClick={(e) => handleDeleteSession(e, s.id)}
                      className="absolute right-1 top-1 rounded p-0.5 text-muted2 opacity-0 transition-opacity hover:bg-dangerbg hover:text-danger group-hover:opacity-100"
                      title="Удалить из истории"
                      aria-label="Удалить из истории"
                    >
                      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                        <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
                      </svg>
                    </button>
                  </div>
                );
              })
            ) : (
              <div className="rounded-lg border border-border bg-card px-2 py-2 text-xs text-muted">
                Пока нет диалогов — «Новый запрос» или вопрос в чат.
              </div>
            )}
          </div>

          <div className="mt-auto border-t border-border p-3">
            <div className="flex items-center gap-3">
              <div className="grid h-9 w-9 place-items-center rounded-full bg-accent text-[11px] font-semibold text-[#0a1a0c]">
                {userInitials}
              </div>
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-foreground">{user?.full_name || "Пользователь"}</div>
                <div className="truncate text-xs text-muted2">{user?.email || ""}</div>
              </div>
              <Link
                href="/profile"
                className="ml-auto rounded-lg px-2 py-1 text-muted2 hover:text-foreground"
                title="Профиль"
              >
                <svg width="18" height="18" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                  <circle cx="8" cy="8" r="2.5" stroke="currentColor" strokeWidth="1.3" />
                  <path
                    d="M8 1v2M8 13v2M1 8h2M13 8h2M3.05 3.05l1.42 1.42M11.53 11.53l1.42 1.42M11.53 4.47l1.42-1.42M3.05 12.95l1.42-1.42"
                    stroke="currentColor"
                    strokeWidth="1.2"
                    strokeLinecap="round"
                  />
                </svg>
              </Link>
            </div>
            <div className="mt-3 text-[11px] leading-5 text-muted2">
              <span className="text-accent2">●</span> Сессии в списке слева — в этом браузере; отчёты и расписания — на сервере.
            </div>
          </div>
        </aside>

        <main className="flex min-w-0 flex-1 flex-col overflow-hidden">{children}</main>
      </div>
    </div>
  );
}
