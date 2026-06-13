# Docker 部署指南

## 前置条件

- Docker Engine >= 24.0
- Docker Compose >= 2.20

## 国内网络加速配置

Docker Hub 在国内访问不稳定，**必须先配置镜像加速**，否则构建会反复超时重试。

### 步骤 1：配置 Docker daemon 镜像加速

编辑 `/etc/docker/daemon.json`（Linux/Mac）或 Docker Desktop → Settings → Docker Engine（Windows）：

```json
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://dockerproxy.com",
    "https://docker.nju.edu.cn",
    "https://mirror.ccs.tencentyun.com"
  ]
}
```

保存后重启 Docker：

```bash
# Linux
sudo systemctl restart docker

# Mac/Windows：Docker Desktop → 重启
```

验证是否生效：

```bash
docker info | grep -A 5 "Registry Mirrors"
# 应该看到刚才配置的镜像地址列表
```

### 步骤 2：配置 PyPI 镜像（可选，默认已使用清华源）

后端 Dockerfile 已内置 `pip install -i https://pypi.tuna.tsinghua.edu.cn/simple`。

## 环境变量

```bash
# 复制环境变量模板（至少需要填写 OPENAI_API_KEY）
cp .env.example .env
```

**最少配置**：只需要填写 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL`。其他都使用默认值。

## 构建与启动

```bash
# 从项目根目录执行
docker compose -f docker/docker-compose.yaml --env-file .env up -d
```

首次构建约 10-15 分钟（主要为 torch 编译），之后有层缓存。

首次拉取基础镜像约 1-3 分钟（配置镜像加速后）。

## 访问

| 服务 | 地址 | 说明 |
|---|---|---|
| 前端界面 | http://localhost:5173 | 金箔研搜，对话式论文调研 |
| 后端 API | http://localhost:8000 | FastAPI 接口 |
| API 文档 | http://localhost:8000/docs | Swagger UI |
| SearXNG | http://localhost:8888 | 自托管搜索引擎（零额度） |
| MySQL | localhost:3307 | 教学数据库 |

## 验证

```bash
# 查看服务状态
docker compose -f docker/docker-compose.yaml ps

# 查看后端日志
docker compose -f docker/docker-compose.yaml logs backend

# 测试 API
curl http://localhost:8000/docs
```

## 常见问题

### Q：构建卡在 `FROM node:22-alpine` 或 `FROM python:3.12-slim`

→ **未配置镜像加速**。见上方的 daemon.json 配置。

### Q：后端启动后报 `ModuleNotFoundError: No module named 'sentence_transformers'`

→ 用 `uv sync` 重新安装依赖。在容器内执行：

```bash
docker exec deepsearch-backend .venv/bin/pip install sentence-transformers
```

### Q：前端访问白屏 / API 返回 502

→ 确保 backend 先启动完成。前端 nginx 依赖 backend，但 Docker Compose 只保证启动顺序，不保证 backend 就绪。等 10 秒后刷新。

### Q：搜索返回 "无法连接到 SearXNG 实例"

→ SearXNG 容器可能需要几秒初始化。检查：

```bash
docker compose -f docker/docker-compose.yaml logs searxng
```

如果显示 `listen tcp :8080` 则表示已就绪。首次搜索会略慢（初始化缓存）。

### Q：如何上传自己的 PDF 到知识库？

→ 两种方式：

1. **通过前端侧边栏**：在侧边栏「知识库管理」区域选择 PDF 并上传，自动重建索引
2. **直接放入目录**：将 PDF 复制到 `docs/papers/`，然后重启后端容器：

```bash
docker compose -f docker/docker-compose.yaml restart backend
```

## 架构

```
localhost:5173 ──→ nginx (frontend)
                    ├─ /api/*  → http://backend:8000/api/*
                    ├─ /ws/*   → http://backend:8000/ws/* (WebSocket)
                    └─ /*      → /usr/share/nginx/html (静态文件)
                                    │
                             backend 容器 (FastAPI + DeepAgents)
                              ├──→ mysql:3306  (教学数据)
                              └──→ searxng:8080 (自托管搜索引擎)
```

四个服务通过 `deepsearch-net` 桥接网络通信。`MYSQL_HOST=mysql` 和 `SEARXNG_BASE_URL=http://searxng:8080` 在 docker-compose 中已配置，无需在 `.env` 中修改。
