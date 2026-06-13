import { MessageOutlined, DeleteOutlined, PlusOutlined } from "@ant-design/icons";
import { Button, Tooltip } from "antd";
import { useEffect, useState } from "react";
import { API_BASE_URL } from "../lib/config";

interface SessionItem {
  id: string;
  title: string;
  query_preview: string;
  created_at: string;
  updated_at: string;
  file_count: number;
  completed: boolean;
}

interface SessionListProps {
  currentSessionId: string;
  onSwitch: (sessionId: string) => void;
  onNewSession: () => void;
  refreshKey: number;
}

function formatRelativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes}分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}天前`;
  return new Date(iso).toLocaleDateString("zh-CN");
}

export function SessionList({
  currentSessionId,
  onSwitch,
  onNewSession,
  refreshKey,
}: SessionListProps) {
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(`${API_BASE_URL}/api/sessions`)
      .then((res) => res.json())
      .then((data) => {
        if (!cancelled) {
          setSessions(data.sessions || []);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  async function handleDelete(sessionId: string, event: React.MouseEvent) {
    event.stopPropagation();
    try {
      await fetch(`${API_BASE_URL}/api/sessions/${sessionId}`, {
        method: "DELETE",
      });
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
    } catch {
      // 静默失败
    }
  }

  return (
    <section className="console-panel" style={{ marginTop: 0 }}>
      <div className="panel-heading">
        <div>
          <span className="panel-kicker">HISTORY</span>
          <h2 style={{ fontSize: 15, margin: "2px 0 0" }}>会话列表</h2>
        </div>
        <Tooltip title="新建会话">
          <Button
            aria-label="新建会话"
            className="composer-icon-button"
            icon={<PlusOutlined />}
            onClick={onNewSession}
            shape="circle"
            size="small"
          />
        </Tooltip>
      </div>

      <div className="session-list" style={{ maxHeight: 360, overflowY: "auto" }}>
        {loading ? (
          <div className="compact-empty" style={{ minHeight: 60 }}>
            <span style={{ color: "var(--muted)", fontSize: 12 }}>加载中...</span>
          </div>
        ) : sessions.length === 0 ? (
          <div className="compact-empty" style={{ minHeight: 60 }}>
            <span style={{ color: "var(--muted)", fontSize: 12 }}>暂无历史会话</span>
          </div>
        ) : (
          sessions.map((session) => {
            const isActive = session.id === currentSessionId;
            return (
              <div
                key={session.id}
                className={`session-item ${isActive ? "session-item--active" : ""}`}
                onClick={() => onSwitch(session.id)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter") onSwitch(session.id);
                }}
              >
                <div className="session-item-icon">
                  <MessageOutlined aria-hidden />
                </div>
                <div className="session-item-body">
                  <strong className="session-item-title" title={session.query_preview}>
                    {session.title}
                  </strong>
                  <span className="session-item-meta">
                    {formatRelativeTime(session.updated_at)}
                    {session.file_count > 0 ? ` · ${session.file_count}个文件` : ""}
                    {session.completed ? " · ✅" : " · ⏳"}
                  </span>
                </div>
                {!isActive && (
                  <Tooltip title="删除">
                    <DeleteOutlined
                      className="session-item-delete"
                      onClick={(e) => handleDelete(session.id, e)}
                      style={{
                        color: "var(--muted)",
                        fontSize: 12,
                        cursor: "pointer",
                        opacity: 0.4,
                        transition: "opacity 0.15s",
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.opacity = "1")}
                      onMouseLeave={(e) => (e.currentTarget.style.opacity = "0.4")}
                    />
                  </Tooltip>
                )}
              </div>
            );
          })
        )}
      </div>
    </section>
  );
}
