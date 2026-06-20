import { FileTextOutlined, ReloadOutlined } from "@ant-design/icons";
import { Button, Empty, Input, message, Spin } from "antd";
import { useEffect, useState } from "react";
import { buildPaperCard, listPaperCards } from "../lib/api";
import type { PaperCard } from "../types";

interface PaperCardPanelProps {
  threadId: string;
}

function firstField(card: PaperCard, name: keyof PaperCard["fields"]): string {
  const values = card.fields[name];
  return Array.isArray(values) && values.length > 0 ? values[0] : "待补充";
}

export function PaperCardPanel({ threadId }: PaperCardPanelProps) {
  const [title, setTitle] = useState("");
  const [cards, setCards] = useState<PaperCard[]>([]);
  const [loading, setLoading] = useState(false);
  const [building, setBuilding] = useState(false);

  async function loadCards() {
    setLoading(true);
    try {
      const response = await listPaperCards(8);
      setCards(response.cards || []);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "论文卡片加载失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleBuild() {
    const cleanTitle = title.trim();
    if (!cleanTitle) {
      message.warning("请输入论文标题或关键词");
      return;
    }

    setBuilding(true);
    try {
      const response = await buildPaperCard(cleanTitle, "", 8, threadId);
      setCards((previous) => [response.card, ...previous].slice(0, 8));
      setTitle("");
      message.success(`已生成论文卡片，证据 ${response.evidence.length} 条`);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "论文卡片生成失败");
    } finally {
      setBuilding(false);
    }
  }

  useEffect(() => {
    loadCards();
  }, []);

  return (
    <section className="console-panel" style={{ marginTop: 12 }}>
      <div className="panel-heading">
        <div>
          <span className="panel-kicker">PAPER CARDS</span>
          <h2 style={{ fontSize: 15, margin: "2px 0 0" }}>论文卡片</h2>
        </div>
        <Button
          aria-label="刷新论文卡片"
          icon={<ReloadOutlined />}
          loading={loading}
          onClick={loadCards}
          size="small"
        />
      </div>

      <Input
        onChange={(event) => setTitle(event.target.value)}
        onPressEnter={handleBuild}
        placeholder="论文标题或关键词"
        value={title}
      />
      <Button
        block
        icon={<FileTextOutlined />}
        loading={building}
        onClick={handleBuild}
        size="small"
        style={{ marginTop: 8 }}
        type="primary"
      >
        生成论文卡片
      </Button>

      <div className="retrieval-meta">
        最近 {cards.length} 张结构化卡片
      </div>

      {loading && cards.length === 0 ? (
        <div className="archive-empty">
          <Spin size="small" />
        </div>
      ) : cards.length > 0 ? (
        <div className="paper-card-list">
          {cards.map((card) => (
            <article className="paper-card" key={`${card.created_at}-${card.card_id}`}>
              <div className="paper-card-title">
                <strong>{card.title}</strong>
                <span>{card.source || card.fields.status || "auto_extracted"}</span>
              </div>
              <dl>
                <dt>方法</dt>
                <dd>{firstField(card, "method")}</dd>
                <dt>实验</dt>
                <dd>{firstField(card, "experiment")}</dd>
                <dt>结论</dt>
                <dd>{firstField(card, "conclusion")}</dd>
              </dl>
            </article>
          ))}
        </div>
      ) : (
        <Empty
          className="archive-empty"
          description="暂无论文卡片"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      )}
    </section>
  );
}
