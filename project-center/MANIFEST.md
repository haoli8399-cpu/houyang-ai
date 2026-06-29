# MANIFEST — AI 电话客服系统

> 项目全景概述
> 最后更新：2026-06-23

---

**一句话：** 后仰喜剧 AI 电话客服，用户拨打电话后 AI 自动接听并用四川话风格提供服务。

**解决的问题：** 人工客服忙时无人接听，7×24 小仰 AI 秒接，替代 80% 常规咨询。

**怎么工作的：** FreeSWITCH 接电话 → ESL 事件触发 ai_pipeline.py → faster-whisper ASR 转文字 → DeepSeek LLM 生成回复 → CosyVoice TTS 合成语音播报。

**技术栈：** FreeSWITCH + Python 3.11 + faster-whisper + DeepSeek API + CosyVoice，全部本地部署（除 DeepSeek 云端 API）。

**当前状态：** MVP 全链路已跑通，ASR 修复中、TTS 音色已切换为豪哥、播放时序已优化，等待重启验证。
