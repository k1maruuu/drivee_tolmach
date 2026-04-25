import type { AskResponse } from "@/lib/api/types";

export type LocalAnalystMessage =
  | { id: string; role: "user"; text: string; createdAt: number }
  | {
      id: string;
      role: "assistant";
      createdAt: number;
      response?: AskResponse;
      blocked?: { title: string; reasons: string[]; debugSql?: string };
    };

export type LocalAnalystSession = {
  id: string;
  title: string;
  updatedAt: number;
  messages: LocalAnalystMessage[];
};

const STORAGE_PREFIX = "tolmach_analyst_sessions_v1";

function storageKey(userId: number) {
  return `${STORAGE_PREFIX}_${userId}`;
}

function safeParse(raw: string | null): LocalAnalystSession[] {
  if (!raw) return [];
  try {
    const v = JSON.parse(raw) as unknown;
    return Array.isArray(v) ? (v as LocalAnalystSession[]) : [];
  } catch {
    return [];
  }
}

export function listLocalSessions(userId: number): LocalAnalystSession[] {
  if (typeof window === "undefined") return [];
  const all = safeParse(window.localStorage.getItem(storageKey(userId)));
  return [...all].sort((a, b) => b.updatedAt - a.updatedAt);
}

export function getLocalSession(userId: number, sessionId: string): LocalAnalystSession | null {
  return listLocalSessions(userId).find((s) => s.id === sessionId) ?? null;
}

export function sessionTitleFromMessages(messages: LocalAnalystMessage[]): string {
  const first = messages.find((m) => m.role === "user");
  if (first && first.role === "user") {
    const t = first.text.trim().slice(0, 72);
    return t || "Новый запрос";
  }
  return "Новый запрос";
}

export function upsertLocalSession(userId: number, session: LocalAnalystSession) {
  if (typeof window === "undefined") return;
  const key = storageKey(userId);
  const all = safeParse(window.localStorage.getItem(key)).filter((s) => s.id !== session.id);
  all.unshift({
    ...session,
    title: session.title || sessionTitleFromMessages(session.messages),
    updatedAt: Date.now(),
  });
  window.localStorage.setItem(key, JSON.stringify(all));
  window.dispatchEvent(new Event("tolmach:sessions"));
}

export function deleteLocalSession(userId: number, sessionId: string) {
  if (typeof window === "undefined") return;
  const key = storageKey(userId);
  const next = safeParse(window.localStorage.getItem(key)).filter((s) => s.id !== sessionId);
  window.localStorage.setItem(key, JSON.stringify(next));
  window.dispatchEvent(new Event("tolmach:sessions"));
}

export function clearAllLocalSessions(userId: number) {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(storageKey(userId));
  window.dispatchEvent(new Event("tolmach:sessions"));
}

export function newLocalSessionId(): string {
  return `loc_${Date.now().toString(36)}_${Math.random().toString(16).slice(2, 10)}`;
}

export function createEmptyLocalSession(userId: number): LocalAnalystSession {
  const id = newLocalSessionId();
  const session: LocalAnalystSession = {
    id,
    title: "Новый запрос",
    updatedAt: Date.now(),
    messages: [],
  };
  upsertLocalSession(userId, session);
  return session;
}
