export function getApiBaseUrl() {
  const raw =
    process.env.NEXT_PUBLIC_API_URL?.trim() ||
    process.env.NEXT_PUBLIC_API_BASE_URL?.trim() ||
    "";

  // When NEXT_PUBLIC_API_URL is empty, we intentionally use same-origin API.
  // In docker-compose this is proxied by Next rewrites: /api/* -> backend.
  return raw ? raw.replace(/\/$/, "") : "";
}

export type ApiError = {
  status: number;
  message: string;
  detail?: unknown;
};

export async function fetchJson<T>(
  input: string,
  init?: RequestInit & { token?: string | null }
): Promise<T> {
  const base = getApiBaseUrl();
  const url = input.startsWith("http")
    ? input
    : base
      ? `${base}${input.startsWith("/") ? "" : "/"}${input}`
      : input.startsWith("/")
        ? input
        : `/${input}`;

  const headers = new Headers(init?.headers);
  if (init?.token) headers.set("Authorization", `Bearer ${init.token}`);

  const res = await fetch(url, {
    ...init,
    headers,
  });

  const contentType = res.headers.get("content-type") || "";
  const isJson = contentType.includes("application/json");
  const body = isJson ? await res.json().catch(() => null) : await res.text().catch(() => "");

  if (!res.ok) {
    const msg =
      (typeof body === "object" && body && "detail" in (body as any) && typeof (body as any).detail === "string"
        ? ((body as any).detail as string)
        : res.statusText) || "Request failed";
    const err: ApiError = { status: res.status, message: msg, detail: body };
    throw err;
  }

  return body as T;
}

