"""FastAPI 服务：提供 HTTP 接口进行 PDF 文档抽取

架构:
  DrDD API (8001)  ──HTTP──>  mineru-api (8000)  ──解析 PDF──>  content_list
       │                                                              │
       └────────── 调用 pipeline 处理 content_list ────────────────────┘
"""

import asyncio
import json
import logging
import os
import shutil
import tempfile
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config as cfg
from . import pipeline

LOG = logging.getLogger("uvicorn")

TASK_STORE: Dict[str, dict] = {}
TASK_META: Dict[str, dict] = {}

BASE_DIR = Path(os.getenv("DRDD_BASE_DIR", str(Path(tempfile.gettempdir()) / "drdd")))
TASKS_DIR = Path(os.getenv("DRDD_TASKS_DIR", str(BASE_DIR / "tasks")))
WORK_DIR = BASE_DIR / "work"
TASKS_DIR.mkdir(parents=True, exist_ok=True)
WORK_DIR.mkdir(parents=True, exist_ok=True)

MINERU_API_URL = os.getenv("MINERU_API_URL", "http://127.0.0.1:8000")
MINERU_PARSE_BACKEND = os.getenv("MINERU_PARSE_BACKEND", "pipeline")

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    _check_config()
    yield


def _check_config() -> None:
    api_key = cfg.API_KEY
    if not api_key or api_key == "sk-your-api-key-here":
        LOG.warning("API_KEY 未配置 — LLM 调用将失败")
    else:
        LOG.info("API_KEY 已配置")

    if not os.access(TASKS_DIR, os.W_OK):
        LOG.error("TASKS_DIR 不可写: %s", TASKS_DIR)
    else:
        LOG.info("数据目录: %s", BASE_DIR)

    LOG.info("mineru-api 地址: %s (后端: %s)", MINERU_API_URL, MINERU_PARSE_BACKEND)


app = FastAPI(
    title="DrDD API",
    description="金融长文档字段抽取服务",
    version="1.0.0",
    lifespan=lifespan,
)


def _load_meta_from_disk() -> None:
    if not TASKS_DIR.exists():
        return
    for meta_path in sorted(TASKS_DIR.iterdir()):
        mp = meta_path / "metadata.json"
        if mp.exists():
            try:
                meta = json.loads(mp.read_text(encoding="utf-8"))
                tid = meta.get("task_id")
                if tid:
                    TASK_META[tid] = meta
            except (json.JSONDecodeError, OSError):
                pass

_load_meta_from_disk()


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.post("/extract")
async def extract(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    ext = Path(file.filename).suffix.lower()
    if ext not in (".pdf", ".json"):
        raise HTTPException(status_code=400, detail="只支持 PDF 或 JSON 文件")

    task_id = str(uuid.uuid4())
    task_dir = WORK_DIR / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    file_path = task_dir / file.filename
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    file_type = "json" if ext == ".json" else "pdf"

    meta = {
        "task_id": task_id,
        "file_name": file.filename,
        "file_type": file_type,
        "status": "processing",
        "created_at": datetime.now().isoformat(),
        "completed_at": None,
        "document_id": None,
        "document_type": None,
        "error": None,
    }
    TASK_META[task_id] = meta

    TASK_STORE[task_id] = {
        "status": "processing",
        "file_path": str(file_path),
        "task_dir": str(task_dir),
        "file_type": file_type,
    }

    asyncio.create_task(_run_extraction(task_id))

    return JSONResponse(status_code=202, content={"task_id": task_id})


@app.get("/status/{task_id}")
async def get_status(task_id: str):
    task = TASK_STORE.get(task_id)
    if not task:
        meta = TASK_META.get(task_id)
        if not meta:
            raise HTTPException(status_code=404, detail="任务不存在")
        return _meta_to_status(meta)

    if task["status"] == "processing":
        return {"status": "processing"}

    if task["status"] == "done":
        return {"status": "done", "result": task["result"]}

    if task["status"] == "failed":
        return {"status": "failed", "error": task["error"]}

    return {"status": task["status"]}


@app.get("/tasks")
async def list_tasks():
    tasks = []
    for meta in TASK_META.values():
        tasks.append({
            "task_id": meta["task_id"],
            "file_name": meta["file_name"],
            "file_type": meta["file_type"],
            "status": meta["status"],
            "created_at": meta["created_at"],
            "completed_at": meta["completed_at"],
            "document_id": meta["document_id"],
            "document_type": meta["document_type"],
            "error": meta["error"],
        })
    tasks.sort(key=lambda t: t.get("created_at", ""), reverse=True)
    return {"tasks": tasks}


@app.get("/tasks/{task_id}/result")
async def get_task_result(task_id: str):
    result_path = TASKS_DIR / task_id / "result.json"
    meta = TASK_META.get(task_id)
    if not meta:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not result_path.exists():
        if meta["status"] == "failed":
            return {"error": meta["error"]}
        raise HTTPException(status_code=404, detail="结果文件未找到")
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
        return result
    except (json.JSONDecodeError, OSError) as e:
        raise HTTPException(status_code=500, detail=f"读取结果文件失败: {e}")


@app.get("/tasks/{task_id}/download")
async def download_task_result(task_id: str):
    result_path = TASKS_DIR / task_id / "result.json"
    meta = TASK_META.get(task_id)
    if not meta:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not result_path.exists():
        if meta["status"] == "failed":
            raise HTTPException(status_code=400, detail="任务失败，无法下载结果")
        raise HTTPException(status_code=404, detail="结果文件未找到")

    safe_name = meta.get("document_id") or Path(meta["file_name"]).stem
    return FileResponse(
        str(result_path),
        media_type="application/json",
        filename=f"{safe_name}_result.json",
    )


def _meta_to_status(meta: dict) -> dict:
    if meta["status"] == "done":
        return {"status": "done", "result": None}
    if meta["status"] == "failed":
        return {"status": "failed", "error": meta["error"]}
    return {"status": meta["status"]}


async def _run_extraction(task_id: str):
    task = TASK_STORE[task_id]
    file_path = Path(task["file_path"])
    task_dir = Path(task["task_dir"])
    file_type = task["file_type"]
    result = None
    error_msg = None

    try:
        if file_type == "pdf":
            mineru_output_dir = task_dir / "mineru-output"
            mineru_output_dir.mkdir(parents=True, exist_ok=True)

            async with httpx.AsyncClient(timeout=600.0) as client:
                with open(file_path, "rb") as f:
                    resp = await client.post(
                        f"{MINERU_API_URL}/file_parse",
                        files={"files": (file_path.name, f, "application/pdf")},
                        data={
                            "backend": MINERU_PARSE_BACKEND,
                            "return_content_list": "true",
                            "return_md": "true",
                            "lang_list": "ch",
                        },
                    )

                if resp.status_code != 200:
                    error_msg = f"mineru-api 解析失败 ({resp.status_code}): {resp.text[:300]}"
                    task["status"] = "failed"
                    task["error"] = error_msg
                    return

                data = resp.json()
                file_name = file_path.stem
                results = data.get("results", {})
                file_result = None
                for key in results:
                    file_result = results[key]
                    break

                if not file_result or "content_list" not in file_result:
                    error_msg = "mineru-api 响应中未包含 content_list"
                    task["status"] = "failed"
                    task["error"] = error_msg
                    return

                content_list = file_result["content_list"]
                cl_path = mineru_output_dir / f"{file_name}_content_list.json"
                with open(cl_path, "w", encoding="utf-8") as f:
                    json.dump(content_list, f, ensure_ascii=False, indent=2)

            input_dir = str(mineru_output_dir)

        else:
            input_dir = str(task_dir)

    except httpx.ConnectError:
        error_msg = f"无法连接到 mineru-api ({MINERU_API_URL})，请确认 mineru-api 服务已启动"
        task["status"] = "failed"
        task["error"] = error_msg
        return
    except Exception as e:
        error_msg = f"{'mineru 解析' if file_type == 'pdf' else '文件处理'}失败: {e}"
        task["status"] = "failed"
        task["error"] = error_msg
        return

    try:
        result = await pipeline.run_pipeline_async(input_dir)
        task["status"] = "done"
        task["result"] = result
    except Exception as e:
        error_msg = f"字段抽取失败: {e}"
        task["status"] = "failed"
        task["error"] = error_msg
    finally:
        _persist_task(task_id, result, error_msg)
        shutil.rmtree(task_dir, ignore_errors=True)


def _persist_task(task_id: str, result: Optional[dict], error: Optional[str]) -> None:
    meta = TASK_META.get(task_id, {})
    meta["status"] = "done" if result else ("failed" if error else "processing")
    meta["completed_at"] = datetime.now().isoformat()
    result = _extract_result(result, task_id, meta)
    meta["document_id"] = result.get("document_id") if isinstance(result, dict) else None
    meta["document_type"] = result.get("document_type") if isinstance(result, dict) else None
    meta["error"] = error if error else meta.get("error")
    TASK_META[task_id] = meta

    task_dir = TASKS_DIR / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    with open(task_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    if result:
        with open(task_dir / "result.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)


def _extract_result(result, task_id, meta) -> dict:
    return result or {}


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
