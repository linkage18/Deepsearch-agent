import { API_BASE_URL } from "./config";
import type {
  CancelTaskResponse,
  EvidenceListResponse,
  FileListResponse,
  PaperCardBuildResponse,
  PaperCardListResponse,
  PaperMatrixResponse,
  RetrievalTestResponse,
  ReviewReportResponse,
  TaskEventsResponse,
  TaskResponse,
  UploadResponse
} from "../types";

function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}

async function requestJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const message =
      typeof payload === "object" && payload && "detail" in payload
        ? String(payload.detail)
        : `HTTP ${response.status}`;
    throw new Error(message);
  }

  return payload as T;
}

export async function startTask(query: string, threadId: string): Promise<TaskResponse> {
  return requestJson<TaskResponse>(apiUrl("/api/task"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      query,
      thread_id: threadId
    })
  });
}

export async function cancelTask(threadId: string): Promise<CancelTaskResponse> {
  return requestJson<CancelTaskResponse>(apiUrl(`/api/task/${encodeURIComponent(threadId)}/cancel`), {
    method: "POST"
  });
}

export async function listTaskEvents(threadId: string): Promise<TaskEventsResponse> {
  return requestJson<TaskEventsResponse>(
    apiUrl(`/api/task/${encodeURIComponent(threadId)}/events`)
  );
}

export async function uploadSessionFiles(
  files: File[],
  threadId: string
): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("thread_id", threadId);
  files.forEach((file) => formData.append("files", file));

  return requestJson<UploadResponse>(apiUrl("/api/upload"), {
    method: "POST",
    body: formData
  });
}

export async function listSessionFiles(path: string): Promise<FileListResponse> {
  const url = new URL(apiUrl("/api/files"));
  url.searchParams.set("path", path);
  return requestJson<FileListResponse>(url);
}

export function getDownloadUrl(path: string): string {
  const url = new URL(apiUrl("/api/download"));
  url.searchParams.set("path", path);
  return url.toString();
}

export async function testPaperRetrieval(
  query: string,
  topK = 5
): Promise<RetrievalTestResponse> {
  return requestJson<RetrievalTestResponse>(apiUrl("/api/retrieval/test"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      query,
      top_k: topK
    })
  });
}

export async function listEvidenceRecords(limit = 20): Promise<EvidenceListResponse> {
  const url = new URL(apiUrl("/api/evidence"));
  url.searchParams.set("limit", String(limit));
  return requestJson<EvidenceListResponse>(url);
}

export async function buildPaperCard(
  title: string,
  query = "",
  topK = 8,
  threadId?: string
): Promise<PaperCardBuildResponse> {
  return requestJson<PaperCardBuildResponse>(apiUrl("/api/paper-cards/build"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      title,
      query,
      top_k: topK,
      thread_id: threadId
    })
  });
}

export async function listPaperCards(limit = 10): Promise<PaperCardListResponse> {
  const url = new URL(apiUrl("/api/paper-cards"));
  url.searchParams.set("limit", String(limit));
  return requestJson<PaperCardListResponse>(url);
}

export async function getPaperMatrix(limit = 12): Promise<PaperMatrixResponse> {
  const url = new URL(apiUrl("/api/paper-matrix"));
  url.searchParams.set("limit", String(limit));
  return requestJson<PaperMatrixResponse>(url);
}

export async function verifyReportCitations(
  threadId: string,
  reportId: string,
  reportText: string
): Promise<any> {
  return requestJson<any>(apiUrl(`/api/report/${encodeURIComponent(threadId)}/verify`), {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      report_id: reportId,
      report_text: reportText
    })
  });
}

export async function getReportVerification(
  threadId: string,
  reportId?: string
): Promise<any> {
  const url = new URL(apiUrl(`/api/report/${encodeURIComponent(threadId)}/verification`));
  if (reportId) {
    url.searchParams.set("report_id", reportId);
  }
  return requestJson<any>(url);
}

export async function generateReviewReport(
  topic: string,
  threadId?: string,
  limit = 20
): Promise<ReviewReportResponse> {
  return requestJson<ReviewReportResponse>(apiUrl("/api/review-report"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      topic,
      thread_id: threadId,
      limit
    })
  });
}
