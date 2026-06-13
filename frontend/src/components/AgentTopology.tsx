import { CloudServerOutlined, DatabaseOutlined, FileSearchOutlined } from "@ant-design/icons";

const agents = [
  {
    icon: <CloudServerOutlined aria-hidden />,
    name: "公开学术资料搜索",
    detail: "检索论文主页、arXiv、GitHub、作者主页和最新研究动态"
  },
  {
    icon: <DatabaseOutlined aria-hidden />,
    name: "论文元数据查询",
    detail: "MySQL 论文标题、作者、年份、主题、会议和引用关系查询"
  },
  {
    icon: <FileSearchOutlined aria-hidden />,
    name: "LlamaIndex 论文库",
    detail: "本地论文 PDF、阅读笔记和综述材料的正文证据检索"
  }
];

export function AgentTopology() {
  return (
    <section className="console-panel topology-panel" aria-labelledby="topology-title">
      <div className="panel-heading">
        <div>
          <span className="panel-kicker">ROUTING MAP</span>
          <h2 id="topology-title">多智能体路由</h2>
        </div>
      </div>
      <div className="agent-hub">
        <div className="main-agent-node">
          <span>MAIN</span>
          <strong>论文调研主智能体</strong>
        </div>
        <div className="agent-links" aria-hidden>
          <span />
          <span />
          <span />
        </div>
        <div className="agent-node-list">
          {agents.map((agent) => (
            <div className="agent-node" key={agent.name}>
              <div className="agent-node-icon">{agent.icon}</div>
              <div>
                <strong>{agent.name}</strong>
                <p>{agent.detail}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
