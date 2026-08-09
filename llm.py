# -*- coding: utf-8 -*-
"""
「调大模型」的公共入口：智能体对话（agent.py）和复习内容定制（tools.py）共用。
从 agent.py 抽出，逻辑不变：读设置 → 请求 OpenAI 兼容接口 → 返回回答文本。
"""

import config
import models
import requests
import security


def api_key():
    """
    读 API Key（加密存储，用时解密）。
    兼容旧数据：如果存的还是明文（解密失败），直接返回并顺手加密回去。
    """
    raw = models.get_setting("agent_api_key")
    if not raw:
        return ""
    try:
        return security.decrypt_text(raw).strip()
    except Exception:
        # 旧版本存的明文 → 加密迁移
        try:
            models.set_setting("agent_api_key", security.encrypt_text(raw))
        except Exception:
            pass
        return raw.strip()


def provider_info():
    """当前服务商配置 + 模型名"""
    provider = models.get_setting("agent_provider") or "zhipu"
    p = config.AGENT_PROVIDERS.get(provider, config.AGENT_PROVIDERS["zhipu"])
    model = models.get_setting("agent_model") or p["default_model"]
    return p, model


def call(messages, max_tokens=1500, timeout=90):
    """
    发一次大模型请求（不附带工具调用，直接返回文字回答）。
    messages: [{"role": "system"/"user"/"assistant", "content": ...}, ...]
    失败时抛异常，调用方自行处理（复习定制会降级为默认模板）。
    """
    key = api_key()
    if not key:
        raise RuntimeError("还没有配置 API Key")
    p, model = provider_info()
    url = p["base_url"].rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    body = {"model": model, "messages": messages, "max_tokens": max_tokens}
    try:
        r = requests.post(url, headers=headers, json=body, timeout=timeout)
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"网络连接失败：{e}")
    if r.status_code != 200:
        raise RuntimeError(f"大模型服务返回错误 {r.status_code}：{r.text[:150]}")
    msg = r.json()["choices"][0]["message"]
    return msg.get("content") or ""
