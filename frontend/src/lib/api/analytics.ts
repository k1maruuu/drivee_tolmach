import { fetchJson } from "@/lib/api/client";
import type { AskResponse } from "@/lib/api/types";

export async function apiAsk(
  token: string,
  data: {
    question: string;
    template_params?: Record<string, unknown>;
  }
): Promise<AskResponse> {
  return await fetchJson<AskResponse>("/api/analytics/ask", {
    method: "POST",
    token,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question: data.question,
      template_params: data.template_params || {},
    }),
  });
}
