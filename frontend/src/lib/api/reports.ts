import { fetchJson, getApiBaseUrl } from "@/lib/api/client";
import type {
  QueryHistoryRead,
  ReportExecuteResponse,
  SaveReportRequest,
  SavedReportUpdateRequest,
  SavedReportRead,
} from "@/lib/api/types";

export async function apiHistoryList(
  token: string,
  params?: { limit?: number; offset?: number; status?: string; source?: string }
): Promise<QueryHistoryRead[]> {
  const qs = new URLSearchParams();
  if (params?.limit) qs.set("limit", String(params.limit));
  if (params?.offset) qs.set("offset", String(params.offset));
  if (params?.status) qs.set("status", params.status);
  if (params?.source) qs.set("source", params.source);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return await fetchJson<QueryHistoryRead[]>(`/api/reports/history${suffix}`, { token });
}

export async function apiReportsList(
  token: string,
  params?: { limit?: number; offset?: number }
): Promise<SavedReportRead[]> {
  const qs = new URLSearchParams();
  if (params?.limit) qs.set("limit", String(params.limit));
  if (params?.offset) qs.set("offset", String(params.offset));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return await fetchJson<SavedReportRead[]>(`/api/reports${suffix}`, { token });
}

export async function apiReportGet(token: string, reportId: number): Promise<SavedReportRead> {
  return await fetchJson<SavedReportRead>(`/api/reports/${reportId}`, { token });
}

export async function apiReportExecute(
  token: string,
  reportId: number,
  data?: { params?: Record<string, unknown>; max_rows?: number }
): Promise<ReportExecuteResponse> {
  return await fetchJson<ReportExecuteResponse>(`/api/reports/${reportId}/execute`, {
    method: "POST",
    token,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ params: data?.params || {}, max_rows: data?.max_rows }),
  });
}

export async function apiReportDelete(token: string, reportId: number): Promise<void> {
  await fetchJson(`/api/reports/${reportId}`, { method: "DELETE", token });
}

export async function apiReportPatch(
  token: string,
  reportId: number,
  data: SavedReportUpdateRequest
): Promise<SavedReportRead> {
  return await fetchJson<SavedReportRead>(`/api/reports/${reportId}`, {
    method: "PATCH",
    token,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function apiReportSave(token: string, data: SaveReportRequest): Promise<SavedReportRead> {
  return await fetchJson<SavedReportRead>("/api/reports/save", {
    method: "POST",
    token,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function apiReportExportExcel(
  token: string,
  reportId: number,
  params?: { max_rows?: number }
): Promise<{ blob: Blob; filename: string }> {
  const base = getApiBaseUrl();
  const qs = new URLSearchParams();
  if (params?.max_rows != null) qs.set("max_rows", String(params.max_rows));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  const path = `/api/reports/${reportId}/export.xlsx${suffix}`;
  const url = base ? `${base}${path}` : path;

  const res = await fetch(url, {
    method: "GET",
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!res.ok) {
    const msg = res.statusText || "Request failed";
    throw { status: res.status, message: msg, detail: await res.text().catch(() => "") };
  }

  const cd = res.headers.get("content-disposition") || "";
  const m = cd.match(/filename="([^"]+)"/i);
  const filename = m?.[1] || `tolmach_report_${reportId}.xlsx`;
  const blob = await res.blob();
  return { blob, filename };
}
