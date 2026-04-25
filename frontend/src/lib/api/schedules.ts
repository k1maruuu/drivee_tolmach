import { fetchJson } from "@/lib/api/client";
import type {
  ReportScheduleCreateRequest,
  ReportScheduleExecuteResponse,
  ReportScheduleRead,
  ReportScheduleUpdateRequest,
} from "@/lib/api/types";

export async function apiSchedulesList(
  token: string,
  params?: { limit?: number; offset?: number; is_enabled?: boolean; report_id?: number }
): Promise<ReportScheduleRead[]> {
  const qs = new URLSearchParams();
  if (params?.limit != null) qs.set("limit", String(params.limit));
  if (params?.offset != null) qs.set("offset", String(params.offset));
  if (params?.is_enabled !== undefined) qs.set("is_enabled", String(params.is_enabled));
  if (params?.report_id != null) qs.set("report_id", String(params.report_id));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return await fetchJson<ReportScheduleRead[]>(`/api/report-schedules${suffix}`, { token });
}

export async function apiScheduleCreate(
  token: string,
  data: ReportScheduleCreateRequest
): Promise<ReportScheduleRead> {
  return await fetchJson<ReportScheduleRead>("/api/report-schedules", {
    method: "POST",
    token,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function apiScheduleGet(token: string, scheduleId: number): Promise<ReportScheduleRead> {
  return await fetchJson<ReportScheduleRead>(`/api/report-schedules/${scheduleId}`, { token });
}

export async function apiSchedulePatch(
  token: string,
  scheduleId: number,
  data: ReportScheduleUpdateRequest
): Promise<ReportScheduleRead> {
  return await fetchJson<ReportScheduleRead>(`/api/report-schedules/${scheduleId}`, {
    method: "PATCH",
    token,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function apiScheduleRunNow(
  token: string,
  scheduleId: number
): Promise<ReportScheduleExecuteResponse> {
  return await fetchJson<ReportScheduleExecuteResponse>(`/api/report-schedules/${scheduleId}/run-now`, {
    method: "POST",
    token,
  });
}

export async function apiScheduleDelete(token: string, scheduleId: number): Promise<void> {
  await fetchJson(`/api/report-schedules/${scheduleId}`, { method: "DELETE", token });
}
