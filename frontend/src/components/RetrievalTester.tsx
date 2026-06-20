import { CheckCircleOutlined, CloseCircleOutlined, SearchOutlined } from "@ant-design/icons";
import { Button, Input, InputNumber, message } from "antd";
import { useState } from "react";
import { testPaperRetrieval, verifyReportCitations, getReportVerification } from "../lib/api";
import type { PaperEvidence } from "../types";

export function RetrievalTester() {
  const [query, setQuery] = useState("ReAct 如何结合 reasoning 和 acting");
  const [topK, setTopK] = useState(5);
  const [loading, setLoading] = useState(false);
  const [elapsedMs, setElapsedMs] = useState<number | null>(null);
  const [savedCount, setSavedCount] = useState<number | null>(null);
  const [result, setResult] = useState("");
  const [evidence, setEvidence] = useState<PaperEvidence[]>([]);
  const [verifyStats, setVerifyStats] = useState<{
    total_claims: number;
    verified: number;
    low_confidence: number;
    unfounded: number;
    coverage_rate: number;
  } | null>(null);
  const [verifyLoading, setVerifyLoading] = useState(false);

  async function handleTest() {
    const cleanQuery = query.trim();
    if (!cleanQuery) {
      message.warning("请输入检索问题");
      return;
    }

    setLoading(true);
    setResult("");
    setEvidence([]);
    setSavedCount(null);
    setElapsedMs(null);
    try {
      const response = await testPaperRetrieval(cleanQuery, topK);
      setResult(response.result);
      setEvidence(response.evidence || []);
      setSavedCount(response.saved_count);
      setElapsedMs(response.elapsed_ms);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "检索测试失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="console-panel" style={{ marginTop: 12 }}>
      <div className="panel-heading">
        <div>
          <span className="panel-kicker">RETRIEVAL TEST</span>
          <h2 style={{ fontSize: 15, margin: "2px 0 0" }}>论文库召回测试</h2>
        </div>
      </div>

      <Input.TextArea
        autoSize={{ minRows: 2, maxRows: 4 }}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="输入检索问题"
        value={query}
      />

      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
        <InputNumber
          max={10}
          min={1}
          onChange={(value) => setTopK(Number(value || 5))}
          size="small"
          value={topK}
        />
        <Button
          block
          icon={<SearchOutlined />}
          loading={loading}
          onClick={handleTest}
          size="small"
          type="primary"
        >
          测试召回
        </Button>
      </div>

      {elapsedMs !== null ? (
        <div className="retrieval-meta">
          耗时 {elapsedMs.toFixed(0)} ms
          {savedCount !== null ? ` · 已沉淀 ${savedCount} 条证据` : ""}
        </div>
      ) : null}

      {evidence.length > 0 ? (
        <div className="evidence-list">
          {evidence.map((item) => (
            <article className="evidence-card" key={item.evidence_id}>
              <div className="evidence-card-header">
                <strong>{item.source}</strong>
                <span>
                  {item.page ? `p.${item.page}` : "no page"}
                  {item.score !== null ? ` · ${item.score.toFixed(3)}` : ""}
                </span>
              </div>
              <p>{item.quote}</p>
            </article>
          ))}
        </div>
      ) : result ? (
        <pre className="retrieval-result">{result}</pre>
      ) : null}

      {result && result.length > 50 && (
        <div style={{ marginTop: 8 }}>
          <Button
            block
            icon={<CheckCircleOutlined />}
            loading={verifyLoading}
            onClick={async () => {
              setVerifyLoading(true);
              setVerifyStats(null);
              try {
                const rid = `report_${Date.now()}`;
                const vr = await verifyReportCitations("test", rid, result);
                setVerifyStats({
                  total_claims: vr.total_claims,
                  verified: vr.verified,
                  low_confidence: vr.low_confidence,
                  unfounded: vr.unfounded,
                  coverage_rate: vr.coverage_rate,
                });
              } catch {
                message.error("引用检验失败");
              } finally {
                setVerifyLoading(false);
              }
            }}
            size="small"
          >
            检验引用真伪
          </Button>
          {verifyStats ? (
            <div className="verification-stats" style={{ marginTop: 4, fontSize: 12 }}>
              <span>声明: {verifyStats.total_claims}</span>
              <span style={{ color: "#52c41a" }}>
                <CheckCircleOutlined /> {verifyStats.verified}
              </span>
              <span style={{ color: "#faad14" }}>⚠ {verifyStats.low_confidence}</span>
              <span style={{ color: "#ff4d4f" }}>
                <CloseCircleOutlined /> {verifyStats.unfounded}
              </span>
              <span>
                覆盖率: {(verifyStats.coverage_rate * 100).toFixed(0)}%
              </span>
            </div>
          ) : null}
        </div>
      )}
    </section>
  );
}
