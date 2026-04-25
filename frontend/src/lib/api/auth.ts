import { fetchJson, getApiBaseUrl } from "@/lib/api/client";
import type { RegisterRequest, TokenResponse, UserRead } from "@/lib/api/types";

export async function apiLogin(args: { email: string; password: string }): Promise<TokenResponse> {
  const base = getApiBaseUrl();
  const url = `${base}/api/auth/login`;
  const body = new URLSearchParams();
  body.set("username", args.email);
  body.set("password", args.password);
  return await fetchJson<TokenResponse>(url, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
}

export async function apiRegister(data: RegisterRequest): Promise<UserRead> {
  return await fetchJson<UserRead>("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function apiMe(token: string): Promise<UserRead> {
  return await fetchJson<UserRead>("/api/auth/me", { token });
}

