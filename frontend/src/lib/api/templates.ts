import { fetchJson, getApiBaseUrl } from "@/lib/api/client";
import type { QueryTemplateRead, TemplateExecuteResponse } from "@/lib/api/types";

export async function apiTemplatesList(token: string): Promise<QueryTemplateRead[]> {
  return await fetchJson<QueryTemplateRead[]>("/api/templates", { token });
}

export async function apiTemplateExecute(
  token: string,
  templateId: string,
  data: { params?: Record<string, unknown>; max_rows?: number }
): Promise<TemplateExecuteResponse> {
  return await fetchJson<TemplateExecuteResponse>(`/api/templates/${encodeURIComponent(templateId)}/execute`, {
    method: "POST",
    token,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ params: data.params || {}, max_rows: data.max_rows }),
  });
}

export async function apiTemplateExportExcel(
  token: string,
  templateId: string,
  data: { params?: Record<string, unknown>; max_rows?: number }
): Promise<{ blob: Blob; filename: string }> {
  const base = getApiBaseUrl();
  const path = `/api/templates/${encodeURIComponent(templateId)}/export.xlsx`;
  const url = base ? `${base}${path}` : path;

  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ params: data.params || {}, max_rows: data.max_rows }),
  });

  if (!res.ok) {
    const msg = res.statusText || "Request failed";
    throw { status: res.status, message: msg, detail: await res.text().catch(() => "") };
  }

  const cd = res.headers.get("content-disposition") || "";
  const m = cd.match(/filename="([^"]+)"/i);
  const filename = m?.[1] || `tolmach_template_${templateId}.xlsx`;
  const blob = await res.blob();
  return { blob, filename };
}

