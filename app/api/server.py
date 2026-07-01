"""
FastAPI 接口层与项目闭环入口

负责承接前端的任务提交、任务取消、文件上传/下载、输出文件列表查询和
WebSocket 长连接。HTTP 接口只做轻量调度，真正的 DeepAgents 执行放到后台
任务中；执行进度、工具调用和最终结果由 monitor 按 thread_id 推送给前端。
"""

import asyncio
import os
import secrets
import shutil
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List

import uvicorn
from fastapi import (
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.agent.main_agent import run_deep_agent
from app.api.monitor import manager
from app.config.paths import (
    DATA_ROOT,
    INDEX_DIR,
    MODEL_CACHE_DIR,
    PAPER_DIR,
    REPORT_DIR,
    SESSIONS_DB_PATH,
    UPLOAD_DIR,
    ensure_runtime_dirs,
)
from app.utils.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """服务生命周期入口：绑定事件循环到 WebSocket 管理器。"""
    loop = asyncio.get_running_loop()
    manager.set_loop(loop)
    logger.info("WebSocket Manager bound to loop", extra={"loop_id": id(loop)})
    yield


# ── 安全配置 ──────────────────────────────────────────

API_KEY = os.getenv("API_KEY", "").strip()
ALLOWED_API_KEYS: set[str] = set()
if API_KEY:
    ALLOWED_API_KEYS.add(API_KEY)

# 对本地开发环境放行无 key 访问
DISABLE_AUTH = os.getenv("DISABLE_API_AUTH", "false").lower() == "true"

# 速率限制
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
_request_counts: dict[str, list[float]] = {}


def _check_rate_limit(client_id: str) -> None:
    now = time.monotonic()
    window = 60.0
    recent = _request_counts.get(client_id, [])
    recent = [t for t in recent if now - t < window]
    if len(recent) >= RATE_LIMIT_PER_MINUTE:
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后重试")
    recent.append(now)
    _request_counts[client_id] = recent


async def verify_api_key(request: Request, call_next):
    """Middleware: API key authentication + rate limiting + request ID."""
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    client_ip = request.client.host if request.client else "unknown"

    logger.debug("Incoming request", extra={
        "method": request.method, "path": request.url.path,
        "client_ip": client_ip, "request_id": request_id,
    })

    try:
        if DISABLE_AUTH:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response

        # Health endpoints are public
        if request.url.path.startswith("/health"):
            _check_rate_limit(client_ip)
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response

        # WebSocket auth is handled by the endpoint
        if request.url.path.startswith("/ws"):
            response = await call_next(request)
            return response

        # Require API key for all other endpoints
        api_key = request.headers.get("X-API-Key", "")
        if api_key not in ALLOWED_API_KEYS:
            logger.warning("Unauthorized access attempt", extra={
                "path": request.url.path, "client_ip": client_ip, "request_id": request_id,
            })
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=401,
                content={"detail": "无效或缺失 API Key (请设置 X-API-Key 请求头)"},
            )

        _check_rate_limit(client_ip)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    except HTTPException as exc:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


# ── 应用初始化 ────────────────────────────────────────

current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent

app = FastAPI(title="DeepAgents API", lifespan=lifespan)

# 安全：仅在生产环境配置了具体域名时限制 CORS
cors_origins_str = os.getenv("CORS_ORIGINS", "")
if cors_origins_str:
    cors_origins = [o.strip() for o in cors_origins_str.split(",") if o.strip()]
else:
    cors_origins = ["*"]  # 开发环境全放开

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "X-API-Key", "X-Request-ID"],
)

# 认证中间件
app.middleware("http")(verify_api_key)

# 保存 thread_id -> 后台 Agent 任务
active_tasks: dict[str, asyncio.Task] = {}
_active_tasks_lock = asyncio.Lock()
agent_semaphore = asyncio.Semaphore(int(os.getenv("AGENT_MAX_CONCURRENCY", "4")))
AGENT_TASK_TIMEOUT_SECONDS = int(os.getenv("AGENT_TASK_TIMEOUT_SECONDS", "300"))

ensure_runtime_dirs()
output_dir = REPORT_DIR
updated_dir = UPLOAD_DIR

MAX_UPLOAD_FILES = 5
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_UPLOAD_SUFFIXES = {".pdf", ".md", ".txt", ".docx", ".xlsx", ".xls"}


def _safe_upload_name(
    filename: str | None,
    allowed_suffixes: set[str] = ALLOWED_UPLOAD_SUFFIXES,
) -> str:
    safe_name = Path(filename or "").name.strip()
    if not safe_name:
        raise HTTPException(status_code=400, detail="文件名不能为空")
    if Path(safe_name).suffix.lower() not in allowed_suffixes:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型：{safe_name}")
    return safe_name


class TaskRequest(BaseModel):
    query: str
    thread_id: str = None


class RetrievalTestRequest(BaseModel):
    query: str
    top_k: int = 5


class PaperCardBuildRequest(BaseModel):
    title: str
    query: str = ""
    top_k: int = 8
    thread_id: str | None = None


class ReviewReportRequest(BaseModel):
    topic: str
    thread_id: str | None = None
    limit: int = 20


class CitationVerifyRequest(BaseModel):
    report_id: str
    report_text: str


async def _run_agent_with_limits(query: str, thread_id: str) -> None:
    async with agent_semaphore:
        await asyncio.wait_for(
            run_deep_agent(query, thread_id),
            timeout=AGENT_TASK_TIMEOUT_SECONDS,
        )


async def _forget_task(thread_id: str, task: asyncio.Task) -> None:
    async with _active_tasks_lock:
        if active_tasks.get(thread_id) is task:
            active_tasks.pop(thread_id, None)


async def _get_task(thread_id: str) -> asyncio.Task | None:
    async with _active_tasks_lock:
        return active_tasks.get(thread_id)


async def _set_task(thread_id: str, task: asyncio.Task) -> None:
    async with _active_tasks_lock:
        active_tasks[thread_id] = task


@app.post("/api/task")
async def run_task(request: TaskRequest):
    if len(request.query) > 2000:
        raise HTTPException(status_code=400, detail="query 过长，最多 2000 字符")

    thread_id = request.thread_id or str(uuid.uuid4())

    old_task = await _get_task(thread_id)
    if old_task and not old_task.done():
        old_task.cancel()

    task = asyncio.create_task(_run_agent_with_limits(request.query, thread_id))
    await _set_task(thread_id, task)
    task.add_done_callback(lambda ft: asyncio.create_task(_forget_task(thread_id, ft)))

    logger.info("Task started", extra={"thread_id": thread_id, "query": request.query[:80]})
    return {"status": "started", "thread_id": thread_id}


# ── 健康检查 ──────────────────────────────────────────

@app.get("/health/live")
async def health_live():
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready():
    checks: dict[str, bool | str] = {
        "data_root": DATA_ROOT.exists(),
        "uploads": UPLOAD_DIR.exists(),
        "reports": REPORT_DIR.exists(),
        "papers": PAPER_DIR.exists(),
        "paper_index_parent": INDEX_DIR.parent.exists(),
        "model_cache": MODEL_CACHE_DIR.exists(),
        "session_db_parent": SESSIONS_DB_PATH.parent.exists(),
    }

    try:
        import sqlite3
        with sqlite3.connect(str(SESSIONS_DB_PATH), timeout=5) as conn:
            conn.execute("SELECT 1")
        checks["sqlite"] = True
    except Exception as exc:
        checks["sqlite"] = f"SQLite 不可用: {exc}"

    # 检查关键外部依赖
    searxng_url = os.getenv("SEARXNG_BASE_URL", os.getenv("SEARXNG_BASE_URL_DOCKER", ""))
    if searxng_url:
        try:
            import requests
            r = requests.get(f"{searxng_url}/search", params={"q": "health", "format": "json"}, timeout=3)
            checks["searxng"] = r.status_code == 200
        except Exception as exc:
            checks["searxng"] = f"SearXNG 不可达: {exc}"
    else:
        checks["searxng"] = "未配置 SEARXNG_BASE_URL"

    # 检查 MySQL
    try:
        from app.tools.db_tools import get_db_config
        from mysql.connector import connect
        config = get_db_config()
        with connect(**config) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
        checks["mysql"] = True
    except Exception as exc:
        checks["mysql"] = f"MySQL 不可用: {exc}"

    status_values = [v for v in checks.values() if isinstance(v, bool)]
    status = "ok" if all(status_values) else "degraded"

    return {
        "status": status,
        "checks": checks,
        "active_tasks": len(active_tasks),
        "max_concurrency": int(os.getenv("AGENT_MAX_CONCURRENCY", "4")),
    }


@app.post("/api/retrieval/test")
async def retrieval_test(request: RetrievalTestRequest):
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query 不能为空")

    top_k = max(1, min(int(request.top_k), 10))
    started_at = time.perf_counter()
    from app.tools.llamaindex_tools import search_paper_evidence_structured

    try:
        retrieval = search_paper_evidence_structured(query, top_k)
    except Exception as exc:
        logger.error("论文库检索失败", extra={"query": query, "error": str(exc)})
        retrieval = {"text": f"论文库检索失败：{exc}", "evidence": []}

    from app.models.session import save_evidence_records
    saved_count = save_evidence_records(query, retrieval["evidence"])
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    return {
        "query": query,
        "top_k": top_k,
        "result": retrieval["text"],
        "evidence": retrieval["evidence"],
        "saved_count": saved_count,
        "elapsed_ms": elapsed_ms,
    }


@app.get("/api/evidence")
async def list_recent_evidence(limit: int = 100):
    from app.models.session import list_evidence_records
    safe_limit = max(1, min(limit, 500))
    return {"evidence": list_evidence_records(safe_limit)}


@app.post("/api/paper-cards/build")
async def build_paper_card_api(request: PaperCardBuildRequest):
    title = request.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="title 不能为空")

    query = request.query.strip() or (
        f"{title} research problem method experiment dataset result limitation"
    )
    top_k = max(3, min(int(request.top_k), 12))
    started_at = time.perf_counter()

    from app.models.session import save_evidence_records, save_paper_card
    from app.services.paper_card_service import build_paper_card_from_evidence
    from app.tools.llamaindex_tools import search_paper_evidence_structured

    try:
        retrieval = search_paper_evidence_structured(query, top_k)
    except Exception as exc:
        logger.error("论文卡片证据召回失败", extra={"title": title, "error": str(exc)})
        retrieval = {"text": f"论文卡片证据召回失败：{exc}", "evidence": []}

    evidence = retrieval["evidence"]
    saved_evidence_count = save_evidence_records(query, evidence, request.thread_id)
    card = build_paper_card_from_evidence(title, query, evidence)
    stored_card = save_paper_card(card, request.thread_id)
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    return {
        "card": stored_card,
        "evidence": evidence,
        "saved_evidence_count": saved_evidence_count,
        "elapsed_ms": elapsed_ms,
    }


@app.get("/api/paper-cards")
async def list_recent_paper_cards(limit: int = 100):
    from app.models.session import list_paper_cards
    safe_limit = max(1, min(limit, 500))
    return {"cards": list_paper_cards(safe_limit)}


@app.get("/api/paper-matrix")
async def get_paper_matrix(limit: int = 20):
    from app.models.session import list_paper_cards
    from app.services.paper_matrix_service import build_paper_matrix
    safe_limit = max(1, min(limit, 100))
    cards = list_paper_cards(safe_limit)
    return build_paper_matrix(cards)


@app.post("/api/review-report")
async def generate_review_report(request: ReviewReportRequest):
    topic = request.topic.strip() or "论文综述报告"
    safe_limit = max(1, min(int(request.limit), 100))

    from app.models.session import list_paper_cards
    from app.services.review_report_service import write_review_report

    cards = list_paper_cards(safe_limit)
    report = write_review_report(topic, cards, request.thread_id)
    return {
        "topic": topic,
        "file": {
            "name": report["name"],
            "path": report["path"],
            "size": report["size"],
            "mtime": report["mtime"],
        },
        "card_count": report["card_count"],
    }


@app.post("/api/report/{thread_id}/verify")
async def verify_report_citations(thread_id: str, request: CitationVerifyRequest):
    from app.tools.citation_checker import verify_citations

    try:
        result = verify_citations(
            thread_id=thread_id,
            report_id=request.report_id,
            report_text=request.report_text,
        )
        return {"thread_id": thread_id, "report_id": request.report_id, **result}
    except Exception as exc:
        logger.error("引用校验失败", extra={"thread_id": thread_id, "error": str(exc)})
        return {
            "thread_id": thread_id,
            "report_id": request.report_id,
            "error": str(exc),
            "total_claims": 0,
            "verified": 0,
            "low_confidence": 0,
            "unfounded": 0,
            "no_claim": 0,
            "coverage_rate": 0.0,
            "unfounded_rate": 0.0,
            "details": [],
        }


@app.get("/api/report/{thread_id}/verification")
async def get_report_verification(thread_id: str, report_id: str | None = None):
    from app.models.session import get_citation_verification

    try:
        result = get_citation_verification(thread_id, report_id)
        return {"thread_id": thread_id, "report_id": report_id, **result}
    except Exception as exc:
        logger.error("获取引用校验结果失败", extra={"thread_id": thread_id, "error": str(exc)})
        return {
            "thread_id": thread_id,
            "report_id": report_id,
            "error": str(exc),
            "stats": {},
            "coverage_rate": 0.0,
            "unfounded_rate": 0.0,
            "details": [],
        }


@app.post("/api/task/{thread_id}/cancel")
async def cancel_task(thread_id: str):
    task = await _get_task(thread_id)
    if not task or task.done():
        await _forget_task(thread_id, task)  # type: ignore[arg-type]
        raise HTTPException(status_code=404, detail="任务不存在或已结束")

    task.cancel()
    try:
        await asyncio.wait_for(task, timeout=1.0)
    except asyncio.CancelledError:
        await _forget_task(thread_id, task)
        return {"status": "cancelled", "thread_id": thread_id}
    except asyncio.TimeoutError:
        return {"status": "cancelling", "thread_id": thread_id}
    except Exception as e:
        await _forget_task(thread_id, task)
        return {"status": "cancelled", "thread_id": thread_id, "message": str(e)}

    await _forget_task(thread_id, task)
    return {"status": "cancelled", "thread_id": thread_id}


@app.get("/api/task/{thread_id}/events")
async def list_task_events(thread_id: str, limit: int = 200):
    from app.models.session import list_run_events
    safe_limit = max(1, min(limit, 1000))
    return {"thread_id": thread_id, "events": list_run_events(thread_id, safe_limit)}


@app.post("/api/upload")
async def upload_files(files: List[UploadFile] = File(...), thread_id: str = Form(...)):
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(status_code=400, detail=f"一次最多上传 {MAX_UPLOAD_FILES} 个文件")

    target_dir = updated_dir / f"session_{thread_id}"
    target_dir.mkdir(parents=True, exist_ok=True)

    saved_files = []
    for file in files:
        safe_name = _safe_upload_name(file.filename)
        file_path = (target_dir / safe_name).resolve()
        if not file_path.is_relative_to(target_dir.resolve()):
            raise HTTPException(status_code=400, detail="非法文件路径")

        written = 0
        with file_path.open("wb") as buffer:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    buffer.close()
                    file_path.unlink(missing_ok=True)
                    raise HTTPException(status_code=400, detail="单文件最大 20MB")
                buffer.write(chunk)
        saved_files.append(safe_name)

    logger.info("Files uploaded", extra={"thread_id": thread_id, "files": saved_files})
    return {"status": "uploaded", "files": saved_files}


@app.post("/api/knowledge/upload")
async def knowledge_upload(files: List[UploadFile] = File(...)):
    target_dir = PAPER_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    saved_files = []
    for file in files:
        safe_name = _safe_upload_name(file.filename, allowed_suffixes={".pdf"})
        if not safe_name.lower().endswith(".pdf"):
            continue
        file_path = (target_dir / safe_name).resolve()
        if not file_path.is_relative_to(target_dir.resolve()):
            raise HTTPException(status_code=400, detail="非法文件路径")
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        saved_files.append(safe_name)

    if saved_files:
        logger.info("Knowledge files uploaded, rebuilding index", extra={"files": saved_files})
        try:
            from app.tools.llamaindex_tools import _load_or_build_index
            _load_or_build_index()
        except Exception as exc:
            logger.warning("索引重建失败", extra={"error": str(exc)})

    return {"status": "uploaded", "files": saved_files, "target_dir": str(target_dir)}


# ─── 会话管理 ─────────────────────────────────────────

@app.get("/api/sessions")
async def list_all_sessions():
    from app.models.session import list_sessions
    try:
        sessions = list_sessions()
        return {"sessions": sessions}
    except Exception as e:
        logger.error("获取会话列表失败", extra={"error": str(e)})
        return {"sessions": [], "error": str(e)}


@app.get("/api/sessions/{session_id}")
async def get_one_session(session_id: str):
    from app.models.session import get_session

    session = get_session(session_id)
    if not session:
        return {"session": None, "files": []}

    session_dir = output_dir / f"session_{session_id}"
    files = []
    if session_dir.exists():
        for f in session_dir.iterdir():
            if f.is_file() and f.suffix.lower() in (".md", ".pdf", ".txt"):
                stat = f.stat()
                files.append({
                    "name": f.name,
                    "path": str(f),
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                })
        files.sort(key=lambda x: x.get("mtime", 0), reverse=True)

    return {"session": session, "files": files}


@app.delete("/api/sessions/{session_id}")
async def delete_one_session(session_id: str):
    from app.models.session import delete_session
    ok = delete_session(session_id)
    return {"deleted": ok}


# ─── 文件接口 ─────────────────────────────────────────
@app.get("/api/download")
async def download_file(path: str):
    try:
        abs_path = Path(path).resolve()
        output_abs = output_dir.resolve()
        if not abs_path.is_relative_to(output_abs):
            return {"error": "拒绝访问: 只能下载输出目录下的文件"}
    except Exception:
        return {"error": "无效的路径参数"}

    if not abs_path.exists():
        return {"error": "文件不存在"}

    return FileResponse(abs_path, filename=abs_path.name)


@app.get("/api/files")
async def list_files(path: str):
    try:
        abs_path = Path(path).resolve()
        output_abs = output_dir.resolve()
        if not abs_path.is_relative_to(output_abs):
            return {"error": "拒绝访问: 只能访问输出目录下的文件"}
    except Exception as e:
        return {"error": f"路径无效: {e}"}

    if not abs_path.exists():
        return {"error": "目录不存在"}

    files = []
    try:
        for file_path in abs_path.rglob("*"):
            if file_path.is_file():
                stat = file_path.stat()
                files.append({
                    "name": file_path.name,
                    "type": "file",
                    "path": str(file_path),
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                })
    except Exception as e:
        return {"error": str(e)}

    files.sort(key=lambda x: x.get("mtime", 0), reverse=True)
    return {"files": files}


@app.websocket("/ws/{thread_id}")
async def websocket_endpoint(websocket: WebSocket, thread_id: str):
    logger.info("WebSocket 连接请求", extra={"thread_id": thread_id})

    await manager.connect(websocket, thread_id)

    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_json({"type": "pong", "message": f"服务端已收到: {data}"})
    except WebSocketDisconnect:
        manager.disconnect(websocket, thread_id)
        logger.info("WebSocket 客户端已断开", extra={"thread_id": thread_id})
    except Exception as e:
        logger.error("WebSocket 连接异常", extra={"thread_id": thread_id, "error": str(e)})
        manager.disconnect(websocket, thread_id)


if __name__ == "__main__":
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)
