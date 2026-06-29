"""
admin/app.py — 后仰喜剧 AI 客服运营后台 (FastAPI)

启动方式：
    cd ~/projects/houyang-ai/pipecat-ai
    ~/pipecat-venv/bin/uvicorn admin.app:app --host 127.0.0.1 --port 3001 --reload

浏览器打开：http://localhost:3001
"""

import os
import json
import time
import subprocess
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ── 路径 ──
ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
KNOWLEDGE_DIR = CONFIG_DIR / "knowledge"
RECORDS_DIR = ROOT / "records"
DB_PATH = RECORDS_DIR / "calls.db"
COSYVOICE_URL = "http://127.0.0.1:9880"

# ── 应用 ──
app = FastAPI(title="后仰喜剧 AI 客服 · 运营后台", version="1.0.0")


# ======================== 配置管理 API ========================

class TextConfig(BaseModel):
    content: str


def _read_file(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@app.get("/api/config/prompt")
def get_prompt():
    """读取 AI 人设提示词"""
    return {"content": _read_file(CONFIG_DIR / "prompt.md")}


@app.put("/api/config/prompt")
def update_prompt(data: TextConfig):
    """更新 AI 人设提示词"""
    _write_file(CONFIG_DIR / "prompt.md", data.content)
    return {"status": "ok"}


@app.get("/api/config/welcome")
def get_welcome():
    return {"content": _read_file(CONFIG_DIR / "welcome.txt")}


@app.put("/api/config/welcome")
def update_welcome(data: TextConfig):
    _write_file(CONFIG_DIR / "welcome.txt", data.content)
    return {"status": "ok"}


@app.get("/api/config/farewell")
def get_farewell():
    return {"content": _read_file(CONFIG_DIR / "farewell.txt")}


@app.put("/api/config/farewell")
def update_farewell(data: TextConfig):
    _write_file(CONFIG_DIR / "farewell.txt", data.content)
    return {"status": "ok"}


# ======================== 知识库 API ========================

class KnowledgeItem(BaseModel):
    name: str
    content: str


@app.get("/api/knowledge")
def list_knowledge():
    """列出所有知识库文件"""
    if not KNOWLEDGE_DIR.exists():
        return {"files": []}
    files = []
    for f in sorted(KNOWLEDGE_DIR.iterdir()):
        if f.suffix == ".md":
            files.append({
                "name": f.stem,
                "filename": f.name,
                "size": f.stat().st_size,
                "updated_at": time.strftime(
                    "%Y-%m-%d %H:%M", time.localtime(f.stat().st_mtime)
                ),
            })
    return {"files": files}


@app.get("/api/knowledge/{name}")
def get_knowledge(name: str):
    """获取单个知识条目"""
    path = KNOWLEDGE_DIR / f"{name}.md"
    if not path.exists():
        raise HTTPException(404, "知识条目不存在")
    return {"name": name, "content": path.read_text(encoding="utf-8")}


@app.post("/api/knowledge")
def create_knowledge(item: KnowledgeItem):
    """新增知识条目"""
    path = KNOWLEDGE_DIR / f"{item.name}.md"
    if path.exists():
        raise HTTPException(400, "同名知识条目已存在")
    _write_file(path, item.content)
    return {"status": "ok", "name": item.name}


@app.put("/api/knowledge/{name}")
def update_knowledge(name: str, item: KnowledgeItem):
    """更新知识条目"""
    path = KNOWLEDGE_DIR / f"{name}.md"
    if not path.exists():
        raise HTTPException(404, "知识条目不存在")
    _write_file(path, item.content)
    return {"status": "ok"}


@app.delete("/api/knowledge/{name}")
def delete_knowledge(name: str):
    """删除知识条目"""
    path = KNOWLEDGE_DIR / f"{name}.md"
    if not path.exists():
        raise HTTPException(404, "知识条目不存在")
    path.unlink()
    return {"status": "ok"}


# ======================== 音色管理 API ========================

@app.get("/api/speakers")
def list_speakers():
    """获取 CosyVoice 可用音色列表（通过 curl 避开代理限制）"""
    try:
        result = subprocess.run(
            ["curl", "-s", f"{COSYVOICE_URL}/speakers", "--max-time", "5"],
            capture_output=True, timeout=10, text=True,
        )
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            return {"speakers": data}
    except Exception as e:
        pass
    return {"speakers": [], "error": "无法连接 CosyVoice TTS 服务"}


@app.get("/api/config/voice")
def get_voice():
    """获取当前音色配置"""
    voice_file = CONFIG_DIR / "voice.txt"
    speaker = _read_file(voice_file).strip() or "豪哥"
    return {"speaker": speaker}


@app.put("/api/config/voice")
def update_voice(data: TextConfig):
    """更新音色配置"""
    _write_file(CONFIG_DIR / "voice.txt", data.content.strip())
    return {"status": "ok"}


@app.post("/api/test-tts")
def test_tts(data: TextConfig):
    """测试指定音色的 TTS 合成"""
    text = data.content or "您好哇，欢迎致电成都后仰喜剧！"
    output = "/tmp/admin_tts_test.wav"
    try:
        result = subprocess.run(
            ["curl", "-s", "-X", "POST", f"{COSYVOICE_URL}/tts",
             "-H", "Content-Type: application/json",
             "-d", json.dumps({"text": text, "speaker": "豪哥" if not data.content else data.content}),
             "--max-time", "30", "-o", output],
            capture_output=True, timeout=35,
        )
        if result.returncode == 0 and Path(output).stat().st_size > 100:
            return FileResponse(output, media_type="audio/wav")
    except Exception as e:
        raise HTTPException(500, f"TTS 测试失败: {e}")
    raise HTTPException(500, "TTS 合成失败")


# ======================== 通话记录 API ========================

@app.get("/api/calls")
def list_calls(limit: int = 50):
    """通话记录列表"""
    if not DB_PATH.exists():
        return {"calls": []}
    try:
        import sqlite3
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM calls ORDER BY start_time DESC LIMIT ?", (limit,)
        ).fetchall()
        calls = []
        for r in rows:
            d = dict(r)
            # 格式化时间
            d["start_time_str"] = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(d["start_time"])
            ) if d["start_time"] else ""
            d["end_time_str"] = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(d["end_time"])
            ) if d["end_time"] else ""
            calls.append(d)
        conn.close()
        return {"calls": calls}
    except Exception as e:
        return {"calls": [], "error": str(e)}


@app.get("/api/calls/{call_id}")
def get_call_detail(call_id: str):
    """通话详情 + 对话轮次"""
    if not DB_PATH.exists():
        raise HTTPException(404, "数据库不存在")
    try:
        import sqlite3
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row

        call = conn.execute(
            "SELECT * FROM calls WHERE call_id=?", (call_id,)
        ).fetchone()
        if not call:
            conn.close()
            raise HTTPException(404, "通话记录不存在")

        turns = conn.execute(
            "SELECT * FROM turns WHERE call_id=? ORDER BY turn_number",
            (call_id,)
        ).fetchall()

        conn.close()

        data = dict(call)
        data["start_time_str"] = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(data["start_time"])
        ) if data["start_time"] else ""
        data["end_time_str"] = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(data["end_time"])
        ) if data["end_time"] else ""
        data["turns"] = [dict(t) for t in turns]

        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/records/{call_id}/{filename}")
def get_recording(call_id: str, filename: str):
    """播放录音文件"""
    file_path = RECORDS_DIR / call_id / filename
    if not file_path.exists():
        raise HTTPException(404, "录音文件不存在")
    return FileResponse(str(file_path), media_type="audio/wav")


# ======================== 服务状态 API ========================

@app.get("/api/status")
def service_status():
    """各服务运行状态"""
    status = {}

    # FreeSWITCH
    fs = subprocess.run(["pgrep", "-x", "freeswitch"], capture_output=True, text=True)
    status["freeswitch"] = "running" if fs.returncode == 0 else "stopped"

    # ESL 8022
    esl = subprocess.run(
        ["lsof", "-i", ":8022", "-P", "-n"],
        capture_output=True, text=True,
    )
    status["esl"] = "running" if "LISTEN" in esl.stdout else "stopped"

    # CosyVoice 9880
    cv = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
         f"{COSYVOICE_URL}/health", "--max-time", "3"],
        capture_output=True, text=True,
    )
    status["cosyvoice"] = "running" if cv.stdout.strip() == "200" else "stopped"

    # ASR
    status["asr"] = "configured"

    # Admin DB
    status["database"] = "ready" if DB_PATH.exists() else "not_initialized"

    return status


# ======================== 前端页面 ========================

@app.get("/", response_class=HTMLResponse)
def index():
    """管理后台首页"""
    html_path = ROOT / "admin" / "templates" / "index.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>管理后台</h1><p>index.html 未找到</p>")
