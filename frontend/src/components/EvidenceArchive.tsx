import { ReloadOutlined } from "@ant-design/icons";
import { Button, Empty, message, Spin } from "antd";
import { useEffect, useState } from "react";
import { listEvidenceRecords } from "../lib/api";
import type { EvidenceRecord } from "../types";

function formatScore(score: number | null): string {
  return score === null ? "no score" : score.toFixed(3);
}

export function EvidenceArchive() {
  const [records, setRecords] = useState<EvidenceRecord[]>([]);
  const [loading, setLoading] = useState(false);

  async function loadEvidence() {
    setLoading(true);
    try {
      const response = await listEvidenceRecords(20);
      setRecords(response.evidence || []);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "证据归档加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadEvidence();
  }, []);

  return (
    <section className="console-panel" style={{ marginTop: 12 }}>
      <div className="panel-heading">
        <div>
          <span className="panel-kicker">EVIDENCE ARCHIVE</span>
          <h2 style={{ fontSize: 15, margin: "2px 0 0" }}>证据归档</h2>
        </div>
        <Button
          aria-label="刷新证据归档"
          icon={<ReloadOutlined />}
          loading={loading}
          onClick={loadEvidence}
          size="small"
        />
      </div>

      <div className="retrieval-meta">
        最近 {records.length} 条结构化证据
      </div>

      {loading && records.length === 0 ? (
        <div className="archive-empty">
          <Spin size="small" />
        </div>
      ) : records.length > 0 ? (
        <div className="evidence-list evidence-list--compact">
          {records.map((item) => (
            <article className="evidence-card" key={`${item.created_at}-${item.evidence_id}`}>
              <div className="evidence-card-header">
                <strong>{item.query}</strong>
                <span>
                  {item.source || "unknown source"}
                  {item.page ? ` · p.${item.page}` : ""}
                  {` · ${formatScore(item.score)}`}
                </span>
              </div>
              <p>{item.quote}</p>
            </article>
          ))}
        </div>
      ) : (
        <Empty
          className="archive-empty"
          description="暂无证据记录"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      )}
    </section>
  );
}
