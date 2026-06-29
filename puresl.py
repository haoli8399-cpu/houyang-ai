#!/usr/bin/env python3
"""
Pure Python FreeSWITCH ESL — 极简版
=====================================
设计原则：和调试脚本一样——单 socket、阻塞 recv、\n\n 分隔。
每个 ESLConnection 实例只做一个事情（要么收事件，要么发 API），
不混用，不抢 socket。

用法（脚本内直接测试）:
  python3 puresl.py          # 连接 8022，订阅事件，3 秒后退出
"""
import socket
import time
import logging

log = logging.getLogger("esl")


class ESLConnection:
    """纯 Python ESL 连接（极简单用途设计）"""

    def __init__(self, host="127.0.0.1", port=8022, password="ClueCon"):
        self.host = host
        self.port = port
        self.password = password
        self.sock = None
        self._buf = b""
        self._connected = False

    def connect(self):
        """连接 + 认证，返回 bool"""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(10)
            self.sock.connect((self.host, self.port))
            # 读 banner
            banner = self._read_until(b"\n\n")
            if b"auth/request" not in banner:
                log.error(f"未收到 auth/request，收到: {banner[:200]}")
                return False
            # 发密码
            self.sock.sendall(f"auth {self.password}\n\n".encode())
            resp = self._read_until(b"\n\n")
            if b"+OK" not in resp:
                log.error(f"认证失败: {resp[:200]}")
                return False
            self._connected = True
            log.info(f"✅ ESL {self.host}:{self.port} 认证成功")
            return True
        except Exception as e:
            log.error(f"❌ ESL 连接失败: {e}")
            return False

    def connected(self):
        return self._connected and self.sock is not None

    def disconnect(self):
        self._connected = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    # ── 事件模式（订阅 + 收事件）──

    def subscribe(self, event_names: str) -> bool:
        """订阅事件，event_names 空格分隔，如 'CHANNEL_CREATE CHANNEL_ANSWER'"""
        self.sock.sendall(f"event plain {event_names}\n\n".encode())
        resp = self._read_until(b"\n\n")
        ok = b"+OK" in resp
        if ok:
            log.info(f"📡 已订阅事件: {event_names}")
        else:
            log.warning(f"订阅回复异常: {resp[:200]}")
        return ok

    def recv_event(self, timeout: float = 30):
        """
        阻塞收一个事件（和调试脚本完全一致）。
        返回 ESLEvent，或超时返回 None。
        """
        try:
            self.sock.settimeout(timeout)
            data = self._read_until(b"\n\n")
            if not data or len(data.strip()) == 0:
                return None
            text = data.decode("utf-8", errors="replace").rstrip()
            evt = ESLEvent(text)

            # 有 Content-Length 就继续读 body
            cl = evt.get_header("Content-Length")
            if cl:
                length = int(cl)
                body = b""
                while len(body) < length:
                    try:
                        chunk = self.sock.recv(length - len(body))
                        if not chunk:
                            break
                        body += chunk
                    except socket.timeout:
                        break
                evt._body = body[:length]
            return evt
        except socket.timeout:
            return None
        except Exception as e:
            log.error(f"recv_event 异常: {e}")
            return None

    # ── API 模式（只发命令，只收响应）──

    def api(self, cmd: str, timeout: float = 30):
        """
        发 API 命令，返回响应体文本。
        响应格式是 ESL 头+body，提取 Reply-Text。
        """
        try:
            self.sock.settimeout(timeout)
            self.sock.sendall(f"api {cmd}\n\n".encode())
            data = self._read_until(b"\n\n")
            if not data or len(data.strip()) == 0:
                return ""

            text = data.decode("utf-8", errors="replace").rstrip()
            # 解析 Reply-Text
            for line in text.split("\n"):
                line = line.strip()
                if line.lower().startswith("reply-text:"):
                    reply = line.split(":", 1)[1].strip()
                    # 检查是否有 Content-Length（api 响应可能有 body）
                    if "Content-Length:" in text.lower():
                        for tl in text.split("\n"):
                            if tl.lower().startswith("content-length:"):
                                clen = int(tl.split(":", 1)[1].strip())
                                body = b""
                                try:
                                    while len(body) < clen:
                                        chunk = self.sock.recv(clen - len(body))
                                        if not chunk:
                                            break
                                        body += chunk
                                except Exception:
                                    pass
                                reply += body.decode("utf-8", errors="replace")[:500]
                    return reply
            return text[:500]
        except socket.timeout:
            return "TIMEOUT"
        except Exception as e:
            log.error(f"api 异常: {e}")
            return ""

    def execute(self, uuid: str, app: str, arg: str = ""):
        """在指定频道执行 APP（sendmsg 协议）"""
        cmd = f"sendmsg {uuid}\ncall-command: execute\nexecute-app-name: {app}\n"
        if arg:
            cmd += f"execute-app-arg: {arg}\n"
        cmd += "\n"
        self.sock.sendall(cmd.encode())

    # ── 底层 socket 读 ──

    def _read_until(self, delimiter: bytes):
        """阻塞读，直到 delimiter 出现。返回包含 delimiter 的完整数据。"""
        while delimiter not in self._buf:
            try:
                chunk = self.sock.recv(65536)
                if not chunk:
                    break
                self._buf += chunk
            except socket.timeout:
                break
        if delimiter in self._buf:
            idx = self._buf.index(delimiter) + len(delimiter)
            result = self._buf[:idx]
            self._buf = self._buf[idx:]
            return result
        # 超时或断线：返回所有缓冲数据
        result = self._buf
        self._buf = b""
        return result

    def fileno(self):
        """供 select/poll 直接使用"""
        return self.sock.fileno() if self.sock else -1

    def __del__(self):
        self.disconnect()


class ESLEvent:
    """极简 ESL 事件"""

    def __init__(self, header_text=""):
        self._headers = {}
        self._body = b""
        for line in header_text.strip().split("\n"):
            line = line.strip()
            if ":" in line:
                k, _, v = line.partition(":")
                self._headers[k.strip()] = v.strip()

    def get_header(self, name: str, default=None):
        return self._headers.get(name, default)

    def get_body(self):
        if isinstance(self._body, bytes):
            return self._body.decode("utf-8", errors="replace")
        return self._body or ""

    def event_name(self):
        return self.get_header("Event-Name", "")

    def get_uuid(self):
        return self.get_header("Unique-ID", "")

    def get_dest(self):
        return self.get_header("Caller-Destination-Number", "")

    def get_caller(self):
        return self.get_header("Caller-Caller-ID-Number", "")

    def __repr__(self):
        return f"<ESLEvent {self.event_name()} uuid={self.get_uuid()[:8]}>"


# ======================= 自测 =======================
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    conn = ESLConnection()
    if not conn.connect():
        exit(1)

    # 订阅事件
    conn.subscribe("CHANNEL_CREATE CHANNEL_ANSWER CHANNEL_HANGUP CHANNEL_EXECUTE CUSTOM")

    # 阻塞收事件 3 秒
    log.info("⏳ 收事件 3 秒...")
    deadline = time.time() + 3
    count = 0
    while time.time() < deadline:
        evt = conn.recv_event(timeout=0.5)
        if evt:
            count += 1
            print(f"  [{evt.event_name()}] uuid={evt.get_uuid()[:12]} "
                  f"dest={evt.get_dest()} caller={evt.get_caller()}")

    log.info(f"共收到 {count} 个事件")
    conn.disconnect()
