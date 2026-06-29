"""
db.py — 通话记录数据库 (SQLite)

用法：
    import db
    db.init_db()                          # 启动时创建表
    db.create_call(call_id, caller, dest) # 通话开始
    db.add_turn(...)                      # 每轮对话
    db.end_call(call_id, status)          # 通话结束
"""

import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).parent / "records" / "calls.db"


def get_conn() -> sqlite3.Connection:
    """获取数据库连接（每个调用独立连接，WAL 模式支持并发）"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化数据库表结构（幂等，可重复调用）"""
    conn = get_conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                call_id TEXT UNIQUE NOT NULL,
                caller TEXT NOT NULL DEFAULT '',
                dest TEXT NOT NULL DEFAULT '',
                start_time REAL NOT NULL,
                end_time REAL,
                duration_sec INTEGER,
                status TEXT NOT NULL DEFAULT 'active',
                transcript_summary TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );

            CREATE TABLE IF NOT EXISTS turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                call_id TEXT NOT NULL REFERENCES calls(call_id),
                turn_number INTEGER NOT NULL,
                user_text TEXT DEFAULT '',
                assistant_text TEXT DEFAULT '',
                action TEXT DEFAULT 'info',
                user_audio_path TEXT DEFAULT '',
                assistant_audio_path TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );

            CREATE INDEX IF NOT EXISTS idx_turns_call_id ON turns(call_id);
        """)
        conn.commit()
    finally:
        conn.close()


def create_call(call_id: str, caller: str = "", dest: str = "") -> bool:
    """通话开始：插入通话记录"""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO calls (call_id, caller, dest, start_time) VALUES (?, ?, ?, ?)",
            (call_id, caller, dest, time.time()),
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"[DB] create_call error: {e}")
        return False
    finally:
        conn.close()


def end_call(call_id: str, status: str = "completed"):
    """通话结束：更新结束时间和时长"""
    conn = get_conn()
    try:
        now = time.time()
        conn.execute(
            "UPDATE calls SET end_time=?, duration_sec=CAST(? - start_time AS INTEGER), status=? WHERE call_id=?",
            (now, now, status, call_id),
        )
        conn.commit()
    finally:
        conn.close()


def add_turn(
    call_id: str,
    turn_number: int,
    user_text: str = "",
    assistant_text: str = "",
    action: str = "info",
    user_audio_path: str = "",
    assistant_audio_path: str = "",
) -> bool:
    """记录一次对话轮次"""
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO turns
               (call_id, turn_number, user_text, assistant_text,
                action, user_audio_path, assistant_audio_path)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (call_id, turn_number, user_text, assistant_text,
             action, user_audio_path, assistant_audio_path),
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"[DB] add_turn error: {e}")
        return False
    finally:
        conn.close()
