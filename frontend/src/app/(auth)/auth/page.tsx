"use client";

import { Suspense, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useSearchParams } from "next/navigation";

import { cn } from "@/lib/cn";
import { useAuth } from "@/context/AuthContext";

type Mode = "login" | "register";

function Field({
  label,
  hint,
  type = "text",
  value,
  onChange,
  placeholder,
  autoComplete,
}: {
  label: string;
  hint?: string;
  type?: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  autoComplete?: string;
}) {
  return (
    <label className="block">
      <div className="mb-2 flex items-center gap-2 text-xs text-muted">
        <span>{label}</span>
        {hint ? (
          <span className="rounded bg-card2 px-2 py-0.5 text-[10px] text-muted2">{hint}</span>
        ) : null}
      </div>
      <input
        className={cn(
          "h-11 w-full rounded-lg border border-border2 bg-card2 px-4 text-sm text-foreground outline-none",
          "placeholder:text-muted2 focus:border-[rgba(108,255,114,0.5)]"
        )}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete={autoComplete}
      />
    </label>
  );
}

function AuthPageInner() {
  const router = useRouter();
  const search = useSearchParams();
  const { login, register } = useAuth();
  const [mode, setMode] = useState<Mode>("login");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [fullName, setFullName] = useState("");
  const [password2, setPassword2] = useState("");

  const canSubmit = useMemo(() => {
    if (!email || !password) return false;
    if (mode === "register") {
      if (password.length < 6) return false;
      if (password !== password2) return false;
    }
    return true;
  }, [email, password, password2, mode]);

  async function onSubmit() {
    setError(null);
    setBusy(true);
    try {
      if (mode === "login") {
        await login({ email, password });
      } else {
        await register({ email, password, fullName: fullName || undefined });
      }
      const next = search.get("next");
      router.replace(next && next.startsWith("/") ? next : "/");
    } catch (e: any) {
      const msg =
        typeof e?.message === "string"
          ? e.message
          : typeof e === "string"
            ? e
            : "Не удалось выполнить запрос. Проверьте данные и попробуйте снова.";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative flex min-h-dvh items-center justify-center bg-background px-4 py-10">
      <div className="pointer-events-none absolute inset-0 opacity-[0.04] [background-image:linear-gradient(var(--text)_1px,transparent_1px),linear-gradient(90deg,var(--text)_1px,transparent_1px)] [background-size:48px_48px]" />
      <div className="pointer-events-none absolute left-1/2 top-1/2 h-[520px] w-[520px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[rgba(108,255,114,0.04)] blur-[1px]" />

      <div className="relative w-full max-w-[480px]">
        <div className="mb-8 flex items-center justify-center gap-3 text-foreground">
          <div className="grid h-11 w-11 place-items-center rounded-xl bg-accent text-[#0a1a0c]">
            <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
              <path
                d="M3 11h16M11 3l8 8-8 8"
                stroke="#0a1a0c"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <div className="text-lg font-semibold">
            Толмач <span className="ml-1 text-sm font-normal text-muted">by Drivee</span>
          </div>
        </div>

        <div className="mb-6 grid grid-cols-2 gap-1 rounded-xl bg-card2 p-1">
          <button
            type="button"
            onClick={() => setMode("login")}
            className={cn(
              "h-9 rounded-lg text-sm transition-colors",
              mode === "login" ? "bg-panel text-foreground" : "text-muted hover:text-foreground"
            )}
          >
            Войти
          </button>
          <button
            type="button"
            onClick={() => setMode("register")}
            className={cn(
              "h-9 rounded-lg text-sm transition-colors",
              mode === "register" ? "bg-panel text-foreground" : "text-muted hover:text-foreground"
            )}
          >
            Регистрация
          </button>
        </div>

        <div className="rounded-2xl border border-border2 bg-card p-10">
          <div className="text-xl font-medium text-foreground">
            {mode === "login" ? "Добро пожаловать" : "Создание аккаунта"}
          </div>
          <div className="mt-1 text-sm leading-6 text-muted">
            {mode === "login" ? "Войдите в свой аккаунт Толмача" : "Заполните данные для доступа"}
          </div>

          <div className="mt-8 space-y-4">
            {mode === "register" ? (
              <Field
                label="Имя"
                value={fullName}
                onChange={setFullName}
                placeholder="Например: Максим Королёв"
                autoComplete="name"
              />
            ) : null}

            <Field
              label="Email"
              value={email}
              onChange={setEmail}
              placeholder="name@company.ru"
              autoComplete="email"
            />

            <Field
              label="Пароль"
              type="password"
              value={password}
              onChange={setPassword}
              placeholder="••••••••"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
            />

            {mode === "register" ? (
              <Field
                label="Повторите пароль"
                type="password"
                value={password2}
                onChange={setPassword2}
                placeholder="••••••••"
                autoComplete="new-password"
              />
            ) : null}
          </div>

          {error ? (
            <div className="mt-5 rounded-xl border border-[rgba(255,107,107,0.35)] bg-dangerbg px-4 py-3 text-sm text-danger">
              {error}
            </div>
          ) : null}

          <button
            type="button"
            disabled={!canSubmit || busy}
            onClick={onSubmit}
            className={cn(
              "mt-6 flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-accent text-sm font-semibold text-[#0a1a0c]",
              "transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            )}
          >
            {busy ? (
              <span className="inline-flex items-center gap-2">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-[#0a1a0c]/30 border-t-[#0a1a0c]" />
                Подождите…
              </span>
            ) : (
              <>
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                  <path
                    d="M3 8h10M9 4l4 4-4 4"
                    stroke="#0a1a0c"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                {mode === "login" ? "Войти" : "Создать аккаунт"}
              </>
            )}
          </button>

          <div className="mt-5 text-center text-sm text-muted">
            {mode === "login" ? (
              <>
                Нет аккаунта?{" "}
                <button type="button" className="font-medium text-accent" onClick={() => setMode("register")}>
                  Зарегистрироваться
                </button>
              </>
            ) : (
              <>
                Уже есть аккаунт?{" "}
                <button type="button" className="font-medium text-accent" onClick={() => setMode("login")}>
                  Войти
                </button>
              </>
            )}
          </div>
        </div>

        <div className="mt-6 text-center text-xs text-muted2">
          Режим MVP · только READ-ONLY запросы к базе
        </div>
      </div>
    </div>
  );
}

export default function AuthPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-dvh items-center justify-center bg-background">
          <div className="flex items-center gap-3 text-muted">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-border2 border-t-accent" />
            Загрузка…
          </div>
        </div>
      }
    >
      <AuthPageInner />
    </Suspense>
  );
}

