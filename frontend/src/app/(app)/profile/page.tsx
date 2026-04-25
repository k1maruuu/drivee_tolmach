"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { cn } from "@/lib/cn";
import { useAuth } from "@/context/AuthContext";
import { clearAllLocalSessions, listLocalSessions } from "@/lib/localAnalystSessions";

function initials(raw: string) {
  const p = raw.trim().split(/\s+/g).filter(Boolean);
  if (p.length >= 2) return (p[0][0] + p[1][0]).toUpperCase();
  return raw.slice(0, 2).toUpperCase();
}

export default function ProfilePage() {
  const { user, logout } = useAuth();
  const name = user?.full_name || "Пользователь";
  const email = user?.email || "";
  const ini = initials(user?.full_name || user?.email || "??");
  const userId = user?.id ?? null;

  const [localCount, setLocalCount] = useState(0);

  const refreshLocal = useCallback(() => {
    if (userId == null) {
      setLocalCount(0);
      return;
    }
    setLocalCount(listLocalSessions(userId).length);
  }, [userId]);

  useEffect(() => {
    refreshLocal();
    const on = () => refreshLocal();
    window.addEventListener("tolmach:sessions", on);
    return () => window.removeEventListener("tolmach:sessions", on);
  }, [refreshLocal]);

  const canClearLocal = userId != null && localCount > 0;

  function handleClearLocalHistory() {
    if (userId == null) return;
    if (!window.confirm("Удалить все локальные диалоги аналитики в этом браузере? Это нельзя отменить.")) return;
    clearAllLocalSessions(userId);
    refreshLocal();
  }

  const quickLinks = useMemo(
    () => [
      { href: "/", label: "Новый запрос", sub: "Главная аналитика" },
      { href: "/templates", label: "Шаблоны", sub: "Готовые SQL-запросы" },
      { href: "/reports", label: "Отчёты и история", sub: "Сохранённые отчёты на сервере" },
    ],
    []
  );

  return (
    <div className="flex flex-1 flex-col overflow-y-auto">
      <div className="border-b border-border bg-panel px-8 py-8 md:px-10">
        <div className="flex flex-wrap items-start justify-between gap-6">
          <div className="flex items-center gap-6">
            <div className="grid h-[72px] w-[72px] place-items-center rounded-full bg-accent text-2xl font-semibold text-[#0a1a0c] ring-2 ring-[rgba(108,255,114,0.3)]">
              {ini}
            </div>
            <div>
              <div className="text-xl font-medium">{name}</div>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted">
                <span>{email}</span>
                {user?.is_superuser ? (
                  <span className="rounded-full border border-[rgba(108,255,114,0.4)] bg-accentbg px-3 py-1 text-xs font-medium text-accent">
                    Администратор
                  </span>
                ) : (
                  <span className="rounded-full border border-border2 bg-card2 px-3 py-1 text-xs">Пользователь</span>
                )}
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={logout}
              className="rounded-lg border border-[rgba(255,107,107,0.35)] bg-dangerbg px-4 py-2 text-sm text-danger hover:opacity-90"
            >
              Выйти
            </button>
          </div>
        </div>
      </div>

      <div className="mx-auto flex w-full max-w-3xl flex-col gap-10 px-8 py-10">
        <section>
          <h2 className="text-sm font-semibold uppercase tracking-[0.14em] text-muted2">Быстрые ссылки</h2>
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            {quickLinks.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                className="rounded-xl border border-border bg-card px-4 py-4 transition-colors hover:border-[rgba(108,255,114,0.25)]"
              >
                <div className="text-sm font-medium text-foreground">{l.label}</div>
                <div className="mt-1 text-xs text-muted2">{l.sub}</div>
              </Link>
            ))}
          </div>
        </section>

        <section>
          <h2 className="text-sm font-semibold uppercase tracking-[0.14em] text-muted2">Сессии в браузере</h2>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            Список диалогов слева хранится на этом устройстве. Сохранённые отчёты, расписания и серверная история запросов — в разделах «Отчёты» и
            «Расписание».
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-4 rounded-xl border border-border bg-card2/40 px-4 py-4">
            <div className="text-sm text-muted">
              Локальных диалогов: <span className="font-mono text-accent2">{localCount}</span>
            </div>
            <button
              type="button"
              disabled={!canClearLocal}
              onClick={handleClearLocalHistory}
              className={cn(
                "rounded-lg border border-border2 px-4 py-2 text-sm text-muted hover:text-foreground",
                !canClearLocal && "cursor-not-allowed opacity-40"
              )}
            >
              Очистить локальную историю
            </button>
          </div>
        </section>

        <section>
          <h2 className="text-sm font-semibold uppercase tracking-[0.14em] text-muted2">Безопасность</h2>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-relaxed text-muted">
            <li>Все SQL-запросы к данным проходят проверку и выполняются в режиме только чтения.</li>
            <li>Пароль и учётная запись задаются при регистрации или администратором; смена пароля через API при необходимости добавится позже.</li>
          </ul>
        </section>
      </div>
    </div>
  );
}
