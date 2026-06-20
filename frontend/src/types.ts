export type ConnectionState = "connecting" | "connected" | "reconnecting" | "closed";

export type MonitorEventName =
  | "session_created"
  | "tool_start"
  | "assistant_call"
  | "task_result"
  | "task_cancelled"
  | "error"
  | string;

export interface MonitorMessage {
  type: "monitor_event";
  event: MonitorEventName;
  message: string;
  data: Record<string, unknown>;
  timestamp: string;
}

export interface PongMessage {
  type: "pong";
  message: string;
}

export type SocketMessage = MonitorMessage | PongMessage;

export interface TaskResponse {
  status: "started" | string;
  thread_id: string;
}

export interface CancelTaskResponse {
  status: "cancelled" | "cancelling" | string;
  thread_id: string;
  message?: string;
}

export interface TaskEventsResponse {
  thread_id: string;
  events: MonitorMessage[];
}

export interface PaperEvidence {
  evidence_id: string;
  source_type: string;
  source: string;
  page: string;
  score: number | null;
  quote: string;
  metadata: Record<string, string>;
}

export interface RetrievalTestResponse {
  query: string;
  top_k: number;
  result: string;
  evidence: PaperEvidence[];
  saved_count: number;
  elapsed_ms: number;
}

export interface EvidenceRecord extends PaperEvidence {
  thread_id: string | null;
  query: string;
  created_at: string;
}

export interface EvidenceListResponse {
  evidence: EvidenceRecord[];
}

export interface PaperCard {
  card_id: string;
  thread_id: string | null;
  title: string;
  source: string;
  query: string;
  fields: {
    problem?: string[];
    method?: string[];
    experiment?: string[];
    conclusion?: string[];
    limitation?: string[];
    summary?: string[];
    status?: string;
  };
  evidence: PaperEvidence[];
  created_at: string;
}

export interface PaperCardBuildResponse {
  card: PaperCard;
  evidence: PaperEvidence[];
  saved_evidence_count: number;
  elapsed_ms: number;
}

export interface PaperCardListResponse {
  cards: PaperCard[];
}

export interface PaperMatrixColumn {
  key: string;
  label: string;
}

export interface PaperMatrixRow {
  card_id: string;
  title: string;
  source: string;
  problem: string;
  method: string;
  experiment: string;
  conclusion: string;
  limitation: string;
  evidence_count: number;
  created_at: string;
}

export interface PaperMatrixResponse {
  columns: PaperMatrixColumn[];
  rows: PaperMatrixRow[];
  card_count: number;
}

export interface ReviewReportResponse {
  topic: string;
  file: OutputFile;
  card_count: number;
}

export interface UploadResponse {
  status: "uploaded" | string;
  files: string[];
}

export interface OutputFile {
  name: string;
  type: "file" | string;
  path: string;
  size: number;
  mtime: number;
}

export interface FileListResponse {
  files?: OutputFile[];
  error?: string;
}

export interface UploadedItem {
  uid: string;
  name: string;
  size: number;
  raw: File;
}
