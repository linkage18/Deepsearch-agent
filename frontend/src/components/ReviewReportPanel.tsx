import { DownloadOutlined, FileMarkdownOutlined } from "@ant-design/icons";
import { Button, Input, message } from "antd";
import { useState } from "react";
import { generateReviewReport, getDownloadUrl } from "../lib/api";
import type { OutputFile } from "../types";

interface ReviewReportPanelProps {
  threadId: string;
}

export function ReviewReportPanel({ threadId }: ReviewReportPanelProps) {
  const [topic, setTopic] = useState("多智能体论文研读与综述生成");
  const [loading, setLoading] = useState(false);
  const [file, setFile] = useState<OutputFile | null>(null);
  const [cardCount, setCardCount] = useState<number | null>(null);

  async function handleGenerate() {
    const cleanTopic = topic.trim();
    if (!cleanTopic) {
      message.warning("请输入综述主题");
      return;
    }

    setLoading(true);
    try {
      const response = await generateReviewReport(cleanTopic, threadId, 20);
      setFile(response.file);
      setCardCount(response.card_count);
      message.success(`已生成 Markdown 综述，纳入 ${response.card_count} 张论文卡片`);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "综述报告生成失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="console-panel" style={{ marginTop: 12 }}>
      <div className="panel-heading">
        <div>
          <span className="panel-kicker">REVIEW REPORT</span>
          <h2 style={{ fontSize: 15, margin: "2px 0 0" }}>综述报告</h2>
        </div>
      </div>

      <Input
        onChange={(event) => setTopic(event.target.value)}
        onPressEnter={handleGenerate}
        placeholder="输入综述主题"
        value={topic}
      />
      <Button
        block
        icon={<FileMarkdownOutlined />}
        loading={loading}
        onClick={handleGenerate}
        size="small"
        style={{ marginTop: 8 }}
        type="primary"
      >
        生成 Markdown 综述
      </Button>

      {file ? (
        <div className="report-file-card">
          <div>
            <strong>{file.name}</strong>
            <span>纳入 {cardCount ?? 0} 张论文卡片</span>
          </div>
          <Button
            href={getDownloadUrl(file.path)}
            icon={<DownloadOutlined />}
            size="small"
            target="_blank"
          >
            下载
          </Button>
        </div>
      ) : (
        <div className="retrieval-meta">
          基于论文卡片和对比矩阵生成可下载 Markdown
        </div>
      )}
    </section>
  );
}
