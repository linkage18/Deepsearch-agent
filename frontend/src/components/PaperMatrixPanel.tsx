import { ReloadOutlined, TableOutlined } from "@ant-design/icons";
import { Button, Empty, message, Spin } from "antd";
import { useEffect, useState } from "react";
import { getPaperMatrix } from "../lib/api";
import type { PaperMatrixRow } from "../types";

function shortText(value: string, max = 120): string {
  const cleaned = value.replace(/\s+/g, " ").trim();
  if (cleaned.length <= max) {
    return cleaned;
  }
  return `${cleaned.slice(0, max)}...`;
}

export function PaperMatrixPanel() {
  const [rows, setRows] = useState<PaperMatrixRow[]>([]);
  const [loading, setLoading] = useState(false);

  async function loadMatrix() {
    setLoading(true);
    try {
      const response = await getPaperMatrix(12);
      setRows(response.rows || []);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "论文对比矩阵加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadMatrix();
  }, []);

  return (
    <section className="console-panel" style={{ marginTop: 12 }}>
      <div className="panel-heading">
        <div>
          <span className="panel-kicker">PAPER MATRIX</span>
          <h2 style={{ fontSize: 15, margin: "2px 0 0" }}>论文对比矩阵</h2>
        </div>
        <Button
          aria-label="刷新论文对比矩阵"
          icon={<ReloadOutlined />}
          loading={loading}
          onClick={loadMatrix}
          size="small"
        />
      </div>

      <div className="retrieval-meta">
        最近 {rows.length} 篇论文卡片
      </div>

      {loading && rows.length === 0 ? (
        <div className="archive-empty">
          <Spin size="small" />
        </div>
      ) : rows.length > 0 ? (
        <div className="matrix-list">
          {rows.map((row) => (
            <article className="matrix-row-card" key={`${row.created_at}-${row.card_id}`}>
              <div className="matrix-row-title">
                <TableOutlined aria-hidden />
                <strong>{row.title}</strong>
                <span>{row.evidence_count} 条证据</span>
              </div>
              <div className="matrix-row-grid">
                <span>方法</span>
                <p>{shortText(row.method)}</p>
                <span>实验</span>
                <p>{shortText(row.experiment)}</p>
                <span>结论</span>
                <p>{shortText(row.conclusion)}</p>
                <span>局限</span>
                <p>{shortText(row.limitation)}</p>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <Empty
          className="archive-empty"
          description="暂无可对比的论文卡片"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      )}
    </section>
  );
}
