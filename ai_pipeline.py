#!/usr/bin/env python3
"""
Pipecat AI 电话客服 — v3（单 socket 架构）
============================================
架构：和验证通过的 debug 脚本一致
  - 主线程：单 ESL socket，阻塞 recv_event 收 CHANNEL_CREATE
  - 收到来电 → 开线程处理对话
  - API 调用：临时开一个 ESL 连接，用完即关

管道：用户→FreeSWITCH→(ESL)→本引擎→ASR(faster-whisper)→LLM(DeepSeek)→TTS(CosyVoice)

分机号：
  用户注册 1001（PCMU/PCMA）
  AI agent 分机 5000（dialplan: answer→park）

用法：
  python ai_pipeline.py --listen      # 监听来电
  python ai_pipeline.py --test        # 模拟一次对话
  python ai_pipeline.py --check       # 检查服务状态

作者：AI 工程师
日期：2026-06-23
"""
import os
import sys
import json
import time
import asyncio
import logging
import tempfile
import subprocess
import threading
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass

# 纯 Python ESL
sys.path.insert(0, str(Path.home() / "pipecat-ai"))
import puresl

log = logging.getLogger("ai_pipeline")


# ============================== 配置 ==============================
@dataclass
class Config:
    fs_host: str = "127.0.0.1"
    fs_port: int = 8022
    fs_password: str = "ClueCon"
    ai_agent_ext: str = "5000"       # AI agent 分机号
    cosyvoice_url: str = "http://127.0.0.1:9880/tts"
    cosyvoice_speaker: str = "豪哥"
    deepseek_api_key: str = os.environ.get("DEEPSEEK_API_KEY", "")
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"
    work_dir: str = str(Path.home() / "pipecat-ai")


config = Config()


# ============================== ESL API 连接（用完即关）==============================
class ESLAPI:
    """临时的 ESL API 连接 — 发一条命令，关闭"""
    @staticmethod
    def api(cmd: str, timeout: float = 10) -> str:
        conn = puresl.ESLConnection(config.fs_host, config.fs_port, config.fs_password)
        if not conn.connect():
            return ""
        try:
            result = conn.api(cmd, timeout=timeout)
            return result or ""
        finally:
            conn.disconnect()

    @staticmethod
    def answer(uuid: str) -> bool:
        resp = ESLAPI.api(f"uuid_answer {uuid}")
        log.info(f"📞 answer {uuid[:8]}: {resp[:80]}")
        return "+OK" in resp or resp == "true" or resp == ""

    @staticmethod
    def execute(uuid: str, app: str, arg: str = ""):
        conn = puresl.ESLConnection(config.fs_host, config.fs_port, config.fs_password)
        if not conn.connect():
            return
        try:
            conn.execute(uuid, app, arg)
        finally:
            conn.disconnect()

    @staticmethod
    def play_file(uuid: str, file_path: str) -> bool:
        conn = puresl.ESLConnection(config.fs_host, config.fs_port, config.fs_password)
        if not conn.connect():
            return False
        try:
            conn.api(f"uuid_broadcast {uuid} {file_path} aleg")
            return True
        finally:
            conn.disconnect()

    @staticmethod
    def milliwatt(uuid: str, duration_ms: int = 500) -> bool:
        """播放静音/提示音"""
        conn = puresl.ESLConnection(config.fs_host, config.fs_port, config.fs_password)
        if not conn.connect():
            return False
        try:
            conn.api(f"uuid_broadcast {uuid} silence://{duration_ms} aleg")
            return True
        finally:
            conn.disconnect()

    @staticmethod
    def hangup(uuid: str):
        ESLAPI.api(f"uuid_kill {uuid}")

    @staticmethod
    def transfer(uuid: str, ext: str):
        ESLAPI.api(f"uuid_transfer {uuid} {ext} XML default")

    @staticmethod
    def park(uuid: str):
        ESLAPI.execute(uuid, "park")


# ============================== ASR ==============================
class ASRClient:
    """语音识别 — faster-whisper"""
    _model = None
    _whisper_type = None

    @classmethod
    def _load(cls):
        if cls._model is not None:
            return
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            # faster-whisper 未安装，回退 openai-whisper
            log.warning(f"⚠️ faster-whisper 未安装（{e}），尝试 openai-whisper...")
            try:
                import whisper
                log.info("🔄 加载 openai-whisper base...")
                cls._model = whisper.load_model("base", device="cpu")
                cls._whisper_type = "openai"
                log.info("✅ openai-whisper 加载成功")
                return
            except ImportError as e2:
                log.warning(f"❌ whisper 均不可用（faster={e}, openai={e2}）")
                return

        # faster-whisper 可用，配置设备
        device = "cpu"
        compute = "int8"
        try:
            import torch
            if torch.backends.mps.is_available():
                device = "mps"
                compute = "float16"
        except ImportError:
            log.info("⚠️ torch 未安装，使用 CPU int8 模式")
        except Exception:
            pass

        log.info(f"🔄 加载 faster-whisper base (device={device})...")
        try:
            cls._model = WhisperModel("base", device=device, compute_type=compute)
            cls._whisper_type = "faster"
            log.info("✅ faster-whisper 加载成功")
        except Exception as e:
            log.error(f"❌ whisper 模型加载失败: {e}")
            cls._model = None

    @classmethod
    def is_ready(cls) -> bool:
        cls._load()
        return cls._model is not None

    @classmethod
    def transcribe(cls, audio_path: str) -> str:
        cls._load()
        if not cls._model:
            return ""

        try:
            if cls._whisper_type == "faster":
                segments, _ = cls._model.transcribe(audio_path, language="zh")
                text = "".join(s.text for s in segments)
            else:
                result = cls._model.transcribe(audio_path, language="zh", fp16=False)
                text = result.get("text", "")

            text = text.strip()
            if text:
                log.info(f"🎤 ASR: {text[:100]}")
            return text
        except Exception as e:
            log.error(f"ASR 异常: {e}")
            return ""


# ============================== TTS ==============================
class TTSClient:
    """CosyVoice TTS"""

    @classmethod
    def is_ready(cls) -> bool:
        """检查 CosyVoice TTS 是否就绪（用 curl 避开 QClaw 代理限制）"""
        base = config.cosyvoice_url.split("/tts")[0]
        try:
            # 先检查端口是否监听
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex(("127.0.0.1", 9880))
            sock.close()
            return result == 0
        except Exception:
            return False

    @classmethod
    def synthesize(cls, text: str, output_path: str) -> Optional[str]:
        """用 curl 合成语音（避开 QClaw 代理限制）"""
        try:
            import subprocess, json as _json
            payload = _json.dumps({
                "text": text,
                "format": "wav",
                "speaker": config.cosyvoice_speaker,
            })
            result = subprocess.run(
                ["curl", "-s", "-X", "POST", config.cosyvoice_url,
                 "-H", "Content-Type: application/json",
                 "-d", payload,
                 "--max-time", "300",
                 "-o", output_path],
                capture_output=True, timeout=300,
            )
            if result.returncode == 0 and Path(output_path).stat().st_size > 100:
                log.info(f"🔊 TTS: {text[:50]} → {output_path} ({Path(output_path).stat().st_size}b)")
                return output_path
            log.warning(f"TTS curl 失败: rc={result.returncode}, stderr={result.stderr[:100]}")
            return None
        except Exception as e:
            log.error(f"TTS 异常: {e}")
            return None


# ============================== LLM ==============================
class LLMClient:
    """DeepSeek 大模型"""

    def __init__(self):
        self.messages = [
            {
                "role": "system",
                "content": (
                    "你是「成都后仰喜剧」的AI电话客服助手，名字叫小仰。用四川普通话（带一点成都味儿）和客户聊天。\n\n"
                    "规则：\n"
                    "1. 语气轻松幽默、热情亲切，像成都本地朋友一样自然\n"
                    "2. 先自我介绍，然后问客户需要啥帮助：买票/咨询演出/转人工\n"
                    "3. 每句话控制在40字以内，口语化，不要念稿子\n"
                    "4. 可以适当用\"要得撒\"\"巴适得很\"\"莫急嘛\"等成都口头禅增加亲和力\n"
                    "5. 回复最后用JSON包裹：{\"action\":\"book|transfer|end|info\",\"reply\":\"你的回复\"}"
                ),
            }
        ]

    def chat(self, user_input: str) -> dict:
        self.messages.append({"role": "user", "content": user_input})
        return self._chat_deepseek()

    def _chat_deepseek(self) -> dict:
        if not config.deepseek_api_key:
            return self._fallback("系统正忙，请稍后再拨。")

        try:
            import requests
            resp = requests.post(
                f"{config.deepseek_base_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.deepseek_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": config.deepseek_model,
                    "messages": self.messages,
                    "temperature": 0.7,
                    "max_tokens": 500,
                },
                timeout=30,
            )
            if resp.status_code == 200:
                reply = resp.json()["choices"][0]["message"]["content"]
                self.messages.append({"role": "assistant", "content": reply})
                return self._parse(reply)
            log.error(f"DeepSeek API 错误: {resp.status_code}")
            return self._fallback("系统正忙，请稍后再拨。")
        except Exception as e:
            log.error(f"DeepSeek 异常: {e}")
            return self._fallback("系统正忙，请稍后再拨。")

    def _parse(self, reply: str) -> dict:
        try:
            start = reply.rfind("{")
            end = reply.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(reply[start:end])
                return {
                    "action": data.get("action", "info"),
                    "reply": data.get("reply", reply[:start].strip()),
                }
        except Exception:
            pass
        return {"action": "info", "reply": reply}

    def _fallback(self, text: str) -> dict:
        return {"action": "info", "reply": text}


# ============================== 对话处理器 ==============================
class CallHandler:
    """一次完整 AI 通话"""

    def __init__(self, uuid: str, caller: str, dest: str):
        self.uuid = uuid
        self.caller = caller
        self.dest = dest
        self.turn = 0
        self.llm = LLMClient()
        self.call_active = True

    def run(self):
        log.info(f"📞 新通话: {self.caller} → {self.dest} (uuid={self.uuid[:12]})")

        # 1. 确保分机已接通（dialplan 已经 answer，但再加一次以防万一）
        ESLAPI.answer(self.uuid)

        # 2. 录音准备
        self._setup_audio()

        # 3. 对话循环
        try:
            self._loop()
        except Exception as e:
            log.error(f"通话异常: {e}")
        finally:
            ESLAPI.hangup(self.uuid)
            log.info(f"🔚 通话结束: {self.uuid[:12]}")

    def _setup_audio(self):
        """配置音频链路"""
        log.info(f"🔊 配置音频链路...")

    def _loop(self):
        """对话主循环"""
        # 首轮问候
        welcome = "您好哇！欢迎致电成都后仰喜剧！我是AI客服小仰，有啥子需要帮忙的嘛？买票咨询都可以跟我说哈。"
        self._speak(welcome)

        while self.call_active and self.turn < 20:
            self.turn += 1

            # 收用户语音 → ASR
            user_text = self._capture_speech()
            if not user_text:
                if not self.call_active:
                    break
                continue

            # 检查结束语
            if any(kw in user_text for kw in ["再见", "拜拜", "挂了", "没其他事", "没有要"]):
                self._speak("感谢您的来电，祝您生活愉快，再见！")
                break

            # LLM
            start = time.time()
            reply_obj = self.llm.chat(user_text)
            elapsed = time.time() - start
            log.info(f"🤖 LLM ({elapsed:.1f}s): {reply_obj['reply'][:80]}")

            # 动作
            if reply_obj["action"] == "transfer":
                self._speak("好的，正在为您转接人工客服，请稍候。")
                ESLAPI.transfer(self.uuid, "9999")
                break
            elif reply_obj["action"] == "end":
                self._speak(reply_obj["reply"])
                break

            # TTS 播放回复
            self._speak(reply_obj["reply"])

    def _capture_speech(self) -> Optional[str]:
        """录音 → ASR 转写"""
        if not ASRClient.is_ready():
            log.info("⏳ ASR 未就绪，等待键盘输入...")
            try:
                return input("🎤 (模拟) > ").strip() or "我不清楚"
            except EOFError:
                return "我不清楚"

        record_path = f"/tmp/pipecat_turn_{self.uuid[:8]}_{self.turn}.wav"

        try:
            # 播一个提示音，表示"你可以说话了"
            ESLAPI.milliwatt(self.uuid, 300)

            # uuid_record 录音 + VAD 轮询（最长 8s）
            ESLAPI.api(f"uuid_record {self.uuid} start {record_path}")
            log.info(f"🎙️ 录音中 (VAD, 最长 8s)...")
            for i in range(8):
                time.sleep(1)
                if Path(record_path).exists() and Path(record_path).stat().st_size > 1024:
                    log.info(f"🎙️ VAD 检测到语音 ({i+1}s)")
                    break
            ESLAPI.api(f"uuid_record {self.uuid} stop {record_path}")

            if Path(record_path).exists() and Path(record_path).stat().st_size > 1024:
                text = ASRClient.transcribe(record_path)
                if text:
                    log.info(f"🎤 用户: {text[:100]}")
                    return text
            log.info("🤫 用户未说话或录音为静音")
            return None
        except Exception as e:
            log.error(f"录音/ASR 异常: {e}")
            return None

    def _speak(self, text: str):
        """TTS 合成并通过 FS 播放"""
        if not text:
            return
        log.info(f"🔊 播报: {text[:80]}")

        if TTSClient.is_ready():
            tts_path = f"/tmp/pipecat_tts_{self.uuid[:8]}_{self.turn}.wav"
            result = TTSClient.synthesize(text, tts_path)
            if result:
                ESLAPI.play_file(self.uuid, tts_path)
                # 估算播放时间（中文正常语速约 3.5 字/秒 + 1s buffer）
                play_sec = max(1.5, len(text) / 3.5 + 1.0)
                log.info(f"⏳ 等待 {play_sec:.1f}s 播放完毕")
                time.sleep(play_sec)
                return

        # TTS 兜底 — espeak
        log.info("⚠️ TTS 不可用，用 espeak 兜底")
        try:
            tts_path = f"/tmp/pipecat_tts_{self.uuid[:8]}_{self.turn}.wav"
            subprocess.run(
                ["espeak", "-v", "zh", "-s", "140", "-w", tts_path, text],
                timeout=30, capture_output=True,
            )
            if Path(tts_path).exists():
                ESLAPI.play_file(self.uuid, tts_path)
                play_sec = max(1.5, len(text) / 3.5 + 1.0)
                time.sleep(play_sec)
        except Exception as e:
            log.warning(f"espeak 失败: {e}")
            time.sleep(2)


# ============================== 主入口 ==============================
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Pipecat AI 电话客服")
    parser.add_argument("--listen", action="store_true", help="监听 FreeSWITCH 来电")
    parser.add_argument("--test", action="store_true", help="模拟一次对话")
    parser.add_argument("--check", action="store_true", help="检查服务状态")
    args = parser.parse_args()

    if args.check:
        check_services()
        return

    if args.listen:
        listen_mode()

    if args.test:
        test_mode()


def listen_mode():
    """监听模式 — 单 socket 阻塞收事件"""
    log.info("=" * 50)
    log.info("🚀 Pipecat AI 电话客服 — 监听模式启动")
    log.info("=" * 50)

    conn = puresl.ESLConnection(config.fs_host, config.fs_port, config.fs_password)
    if not conn.connect():
        log.error("❌ 无法连接 FreeSWITCH ESL，退出")
        sys.exit(1)

    conn.subscribe("CHANNEL_CREATE CHANNEL_ANSWER CHANNEL_HANGUP COMPLETE")

    # 预热 ASR 模型（首次加载约 5 秒，避免通话中阻塞）
    log.info("🔄 预热 ASR 模型...")
    if ASRClient.is_ready():
        log.info("✅ ASR 预热完成")
    else:
        log.warning("⚠️ ASR 预热失败，将使用键盘输入兜底")

    log.info("✅ 事件监听已启动 (Ctrl+C 退出)")
    log.info(f"📡 等待拨分机 {config.ai_agent_ext} ...")

    active_calls = set()

    while True:
        try:
            evt = conn.recv_event(timeout=30)
            if evt is None:
                log.debug("⏳ 无事件 (timeout)")
                continue

            event_name = evt.event_name()
            uuid = evt.get_uuid()
            dest = evt.get_dest()
            caller = evt.get_caller()

            log.info(f"🎯 事件 [{event_name}] uuid={uuid[:12]} caller={caller} dest={dest}")

            # 只处理 5000 分机的 CHANNEL_CREATE
            if event_name == "CHANNEL_CREATE" and dest == config.ai_agent_ext:
                if uuid in active_calls:
                    log.info(f"⏭️ 忽略重复 uuid={uuid[:12]}")
                    continue
                active_calls.add(uuid)

                log.info(f"📞 新呼叫: {caller} → {dest}")
                t = threading.Thread(
                    target=_run_handler,
                    args=(uuid, caller, dest, active_calls),
                    daemon=True,
                )
                t.start()

        except KeyboardInterrupt:
            log.info("👋 退出")
            break
        except Exception as e:
            log.error(f"监听异常: {e}")
            time.sleep(1)

    conn.disconnect()


def _run_handler(uuid: str, caller: str, dest: str, active_calls: set):
    """在独立线程中处理一次通话"""
    handler = CallHandler(uuid, caller, dest)
    try:
        handler.run()
    except Exception as e:
        log.error(f"处理通话异常: {e}")
    finally:
        active_calls.discard(uuid)


def test_mode():
    """测试模式 — 模拟一次对话"""
    log.info("🧪 测试模式")
    conn = puresl.ESLConnection(config.fs_host, config.fs_port, config.fs_password)
    if conn.connect():
        resp = conn.api("status")
        log.info(f"FS status: {resp[:100]}")
        conn.disconnect()
    else:
        log.warning("FS 未连接")

    # 模拟对话
    handler = CallHandler("test_0001", "模拟用户", "5000")
    handler.run()


def check_services():
    """服务检查"""
    print("\n" + "=" * 60)
    print("🔍 Pipecat AI — 服务状态检查")
    print("=" * 60)

    # FS
    conn = puresl.ESLConnection(config.fs_host, config.fs_port, config.fs_password)
    if conn.connect():
        status = conn.api("status")
        lines = [l for l in status.split("\n") if l.strip()]
        print(f"✅ FreeSWITCH: 运行中 ({lines[1] if len(lines) > 1 else 'OK'})")
        conn.disconnect()
    else:
        print("❌ FreeSWITCH: 未连接")

    # ASR
    if ASRClient.is_ready():
        print("✅ ASR: faster-whisper (base)")
    else:
        print("⚠️  ASR: 未就绪")

    # TTS
    if TTSClient.is_ready():
        print(f"✅ CosyVoice: {config.cosyvoice_url}")
    else:
        print("⚠️  CosyVoice: 未就绪")

    # LLM
    if config.deepseek_api_key:
        print("✅ DeepSeek: API Key 已配置")
    else:
        print("⚠️  DeepSeek: API Key 未设置")

    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    main()
