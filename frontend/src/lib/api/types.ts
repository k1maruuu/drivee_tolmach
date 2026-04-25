export type UserRead = {
  id: number;
  email: string;
  full_name?: string | null;
  is_active: boolean;
  is_superuser: boolean;
  created_at: string;
};

export type TokenResponse = {
  access_token: string;
  token_type: "bearer" | string;
  user: UserRead;
};

export type RegisterRequest = {
  email: string;
  password: string;
  full_name?: string;
};

export type QueryResult = {
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
};

export type SqlValidationResponse = {
  is_valid: boolean;
  sql: string;
  normalized_sql?: string | null;
  errors: string[];
  warnings: string[];
};

export type QueryInterpretation = {
  metric?: string | null;
  date_filter?: string | null;
  filters?: string[];
  group_by?: string[];
  sort?: string | null;
  limit?: number | null;
  used_columns?: string[];
  selected_expressions?: string[];
  row_logic?: string | null;
  result_shape?: string | null;
  explanation_ru?: string[];
};

export type ClarificationOption = {
  label: string;
  question: string;
  template_params?: Record<string, unknown>;
};

export type ClarificationPayload = {
  message_ru: string;
  reason?: string | null;
  options: ClarificationOption[];
};

export type QueryVisualization = {
  recommended?: boolean;
  type?: string;
  title?: string | null;
  x_axis?: string | null;
  y_axis?: string | null;
  series?: string[];
  label_column?: string | null;
  value_column?: string | null;
  reason_ru?: string | null;
  frontend_config?: Record<string, unknown>;
};

export type AskResponse = {
  question: string;
  sql: string;
  confidence?: number | null;
  confidence_reason?: string | null;
  notes?: string | null;
  result: QueryResult;
  guardrails: SqlValidationResponse;
  interpretation?: QueryInterpretation | null;
  visualization?: QueryVisualization | null;
  needs_clarification?: boolean;
  clarification?: ClarificationPayload | null;
  source: string;
  template_id?: string | null;
  template_title?: string | null;
  template_match_score?: number | null;
  cache_hit: boolean;
  history_id?: number | null;
};

export type QueryTemplateRead = {
  id: string;
  title: string;
  question: string;
  sql: string;
  params: string[];
  category: string;
  description: string;
};

export type TemplateExecuteResponse = {
  template_id: string;
  title: string;
  sql: string;
  params: Record<string, unknown>;
  cache_hit: boolean;
  confidence?: number | null;
  confidence_reason?: string | null;
  result: QueryResult;
  guardrails: SqlValidationResponse;
  interpretation?: QueryInterpretation | null;
  visualization?: QueryVisualization | null;
};

export type QueryHistoryRead = {
  id: number;
  question: string;
  source: string;
  template_id?: string | null;
  template_title?: string | null;
  generated_sql: string;
  status: string;
  error_message?: string | null;
  confidence?: number | null;
  row_count?: number | null;
  execution_time_ms?: number | null;
  result_preview?: Record<string, unknown> | null;
  created_at: string;
};

export type SavedReportRead = {
  id: number;
  title: string;
  description?: string | null;
  question: string;
  source: string;
  template_id?: string | null;
  template_title?: string | null;
  sql: string;
  params: Record<string, unknown>;
  default_max_rows: number;
  last_result_preview?: Record<string, unknown> | null;
  last_interpretation?: Record<string, unknown> | null;
  last_visualization?: Record<string, unknown> | null;
  last_row_count?: number | null;
  last_run_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type SavedReportUpdateRequest = {
  title?: string | null;
  description?: string | null;
};

export type SaveReportRequest = {
  title: string;
  description?: string;
  history_id?: number | null;
  question?: string | null;
  sql?: string | null;
  source?: string;
  template_id?: string | null;
  template_title?: string | null;
  params?: Record<string, unknown>;
  default_max_rows?: number;
  /** Снимок результата при сохранении без history_id */
  result?: QueryResult;
  interpretation?: QueryInterpretation | null;
  visualization?: QueryVisualization | null;
};

export type ReportExecuteResponse = {
  report: SavedReportRead;
  sql: string;
  params: Record<string, unknown>;
  result: QueryResult;
  guardrails: SqlValidationResponse;
  interpretation?: QueryInterpretation | null;
  visualization?: QueryVisualization | null;
};

export type ReportScheduleRead = {
  id: number;
  report_id: number;
  frequency: string;
  timezone: string;
  hour: number;
  minute: number;
  day_of_week?: number | null;
  day_of_month?: number | null;
  params: Record<string, unknown>;
  default_max_rows?: number | null;
  is_enabled: boolean;
  next_run_at?: string | null;
  last_run_at?: string | null;
  last_status?: string | null;
  last_error_message?: string | null;
  last_row_count?: number | null;
  last_result_preview?: Record<string, unknown> | null;
  run_count: number;
  failure_count: number;
  created_at: string;
  updated_at: string;
  report?: SavedReportRead | null;
};

export type ReportScheduleCreateRequest = {
  report_id: number;
  frequency: "daily" | "weekly" | "monthly";
  timezone?: string;
  hour?: number;
  minute?: number;
  day_of_week?: number | null;
  day_of_month?: number | null;
  params?: Record<string, unknown>;
  default_max_rows?: number | null;
  is_enabled?: boolean;
};

export type ReportScheduleUpdateRequest = {
  frequency?: "daily" | "weekly" | "monthly";
  timezone?: string;
  hour?: number;
  minute?: number;
  day_of_week?: number | null;
  day_of_month?: number | null;
  params?: Record<string, unknown>;
  default_max_rows?: number | null;
  is_enabled?: boolean;
};

export type ReportScheduleExecuteResponse = {
  schedule: ReportScheduleRead;
  sql: string;
  params: Record<string, unknown>;
  result: QueryResult;
  guardrails: SqlValidationResponse;
  interpretation?: QueryInterpretation | null;
  visualization?: QueryVisualization | null;
};

