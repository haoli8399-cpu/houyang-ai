#!/bin/bash
# pipecat_start.sh — Pipecat AI 电话客服启停脚本
# 用法: ./pipecat_start.sh {start|stop|restart|status|check|test|tail}
set -e

VENV="$HOME/pipecat-venv"
WORK="$HOME/projects/houyang-ai/pipecat-ai"
FS_HOME="$HOME/freeswitch"
PID_FILE="$WORK/.pipecat_pid"
COSYVOICE_PY="$HOME/miniconda3/envs/cosyvoice/bin/python"
COSYVOICE_SERVER="$HOME/projects/houyang-ai/cosyvoice/podcast-engine/server.py"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
err()   { echo -e "${RED}[✗]${NC} $1"; }

case "${1:-status}" in

  start)
    echo "🚀 启动 Pipecat AI 电话客服管道..."
    
    echo -n "  FreeSWITCH... "
    if pgrep -x freeswitch >/dev/null 2>&1; then
      info "运行中"
    else
      warn "未运行，尝试启动..."
      freeswitch -nc -conf "$FS_HOME/conf" -db "$FS_HOME/db" -log "$FS_HOME/log" -htdocs "$FS_HOME/htdocs"
      sleep 2
      if pgrep -x freeswitch >/dev/null 2>&1; then info "已启动"; else err "失败!"; exit 1; fi
    fi
    
    echo -n "  ESL 8022... "
    if lsof -i :8022 -P -n 2>/dev/null | grep -q LISTEN; then
      info "开放"
    else
      err "关闭，请检查 FreeSWITCH"
      exit 1
    fi
    
    echo -n "  CosyVoice 9880... "
    if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:9880/health --max-time 3 2>/dev/null | grep -q 200; then
      info "运行中"
    else
      info "未运行，正在启动..."
      nohup "$COSYVOICE_PY" "$COSYVOICE_SERVER" > /tmp/cosyvoice.log 2>&1 &
      COSY_PID=$!
      for i in $(seq 1 30); do
        sleep 1
        if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:9880/health --max-time 2 2>/dev/null | grep -q 200; then
          info "就绪 (${i}s, PID=$COSY_PID)"
          break
        fi
        if [ "$i" -eq 30 ]; then
          if kill -0 $COSY_PID 2>/dev/null; then
            warn "CosyVoice 启动缓慢，仍在运行中，TTS 用 espeak 兜底"
          else
            err "CosyVoice 启动失败（进程已退出），TTS 用 espeak 兜底"
          fi
        fi
      done
    fi
    
    echo -n "  ASR (whisper)... "
    if "$VENV/bin/python3" -c "import faster_whisper" 2>/dev/null; then
      info "就绪"
    else
      warn "未就绪，ASR 将模拟输入"
    fi
    
    echo -n "  AI Pipeline (v3 单socket)... "
    cd "$WORK"
    # 加载 .env 环境变量（DeepSeek API Key 等）
    if [ -f "$WORK/.env" ]; then
      set -a; source "$WORK/.env"; set +a
    fi
    nohup "$VENV/bin/python3" -u "$WORK/ai_pipeline.py" --listen > "$WORK/pipecat.log" 2>&1 &
    PID=$!
    echo $PID > "$PID_FILE"
    sleep 2
    if kill -0 $PID 2>/dev/null; then
      info "PID=$PID"
    else
      err "启动失败，查看: $WORK/pipecat.log"
      exit 1
    fi
    
    echo ""
    info "✅ Pipecat AI 电话客服已启动"
    echo "   日志:  $WORK/pipecat.log"
    echo "   停止:  $0 stop"
    ;;

  stop)
    echo "🛑 停止..."
    if [ -f "$PID_FILE" ]; then
      PID=$(cat "$PID_FILE")
      kill $PID 2>/dev/null || true
      rm -f "$PID_FILE"
      info "已停止 (PID=$PID)"
    else
      pkill -f "ai_pipeline.py.*--listen" 2>/dev/null || warn "未找到进程"
    fi
    ;;

  restart)
    $0 stop; sleep 1; $0 start
    ;;

  status)
    echo "📊 Pipecat AI 电话客服 — 状态"
    echo "------------------------------"
    pgrep -x freeswitch >/dev/null 2>&1 && info "FreeSWITCH:   运行中" || err "FreeSWITCH:   未运行"
    lsof -i :8022 -P -n 2>/dev/null | grep -q LISTEN && info "ESL 8022:     运行中" || err "ESL 8022:     未监听"
    curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:9880/health --max-time 3 2>/dev/null | grep -q 200 && info "CosyVoice:    运行中 (9880)" || warn "CosyVoice:    未就绪"
    "$VENV/bin/python3" -c "import faster_whisper" 2>/dev/null && info "ASR (本地):    faster-whisper" || warn "ASR:          未就绪"
    if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
      info "AI Pipeline:  运行中 (PID=$(cat "$PID_FILE"))"
    elif pgrep -f "ai_pipeline.py.*--listen" >/dev/null 2>&1; then
      info "AI Pipeline:  运行中"
    else
      warn "AI Pipeline:  未启动"
    fi
    echo ""
    echo "日志:  $WORK/pipecat.log (tail -f)"
    ;;

  check)
    "$VENV/bin/python3" "$WORK/ai_pipeline.py" --check
    ;;

  test)
    echo "🧪 单次测试对话..."
    "$VENV/bin/python3" "$WORK/ai_pipeline.py" --test
    ;;

  tail)
    tail -f "$WORK/pipecat.log" 2>/dev/null || echo "日志文件不存在"
    ;;

  *)
    echo "用法: $0 {start|stop|restart|status|check|test|tail}"
    exit 1
    ;;
esac
