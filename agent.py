# -*- coding: utf-8 -*-
"""
智能体核心：大模型对话循环（Function Calling）。
流程：用户消息 → 发给大模型（附工具清单）→ 模型可能要求调用工具 → 我们执行 →
     把结果回传 → 再问模型 → 直到模型给出最终回答。
"""

import datetime
import json

import requests

import config
import models
import security
import tools

# ---------- 系统提示词：给大模型"立规矩" ----------
SYSTEM_PROMPT = """你是"学习助手 Pro"的智能体，一个运行在学生自己电脑上的学习管理助手。

你管理三类数据：DDL 任务（考试/作业等截止事项）、课程资料（课件/PDF 等）、复习计划。

工作准则：
1. 查询类问题（如"有什么考试""有哪些资料"）必须先调用对应工具查询数据库，根据真实数据回答，绝不编造数据。
2. 操作类请求（新增/完成/修改 DDL、生成复习清单）执行后要告诉用户结果。
3. 删除类操作必须先向用户复述要删除的内容并征得明确同意，用户同意后才执行。
4. 用户说的日期如果没写年份，按当前年份理解；截止时间没写具体时刻默认当天 23:59。
5. 回答用中文，简洁友好，像学长的语气。不要照搬工具返回的原始数据，要提炼成好读的句子。
6. 用户没有明确要求时，不要擅自修改数据。
7. 工具查询结果里每条 DDL 末尾的"id=数字"是它的唯一编号。执行完成/修改/删除操作时，必须使用查询结果里的这个 id，绝不自己猜测或编造 id；如果查询结果里没有对应任务，就如实告诉用户找不到。
8. 当用户用自然语言说时间（如"下周三下午两点""明天晚上9点""3天后"）时，把原话原样填进 add_ddl 的 due_at 参数，工具会自动换算成具体日期。你不需要自己心算日期，也不要擅自修改用户的原话。

当前日期：{today}"""

# 最多允许的连续工具调用轮数（防止死循环；正常流程 2-3 轮足够）
MAX_TOOL_ROUNDS = 10

# 没有配置 API Key 时的提示
API_KEY_MSG = "还没配置大模型 API Key。请先到「设置」页配置（推荐智谱 GLM-4.7-Flash，完全免费），之后我就能准确回答你的问题了。"


def _api_key():
    """
    从设置表读 API Key（加密存储，用时解密）。
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


def chat(messages):
    """
    智能体主入口。
    messages: [{"role": "user"|"assistant", "content": "..."}, ...]
    返回 (是否成功, 回复文字)。
    """
    if not _api_key():
        if config.AGENT_MOCK:
            return True, mock_chat(messages)
        return False, API_KEY_MSG
    return real_chat(messages)


# ==================== 真实模式：调用大模型 API ====================

def real_chat(messages):
    provider = models.get_setting("agent_provider") or "zhipu"
    p = config.AGENT_PROVIDERS.get(provider, config.AGENT_PROVIDERS["zhipu"])
    model = models.get_setting("agent_model") or p["default_model"]
    url = p["base_url"].rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"}

    # 系统提示词 + 最近 10 条对话（省 token）
    full = [{"role": "system", "content": SYSTEM_PROMPT.format(today=datetime.date.today().isoformat())}]
    full += messages[-10:]

    for _ in range(MAX_TOOL_ROUNDS):
        body = {
            "model": model,
            "messages": full,
            "tools": tools.TOOL_SCHEMAS,
            "tool_choice": "auto",
        }
        try:
            r = requests.post(url, headers=headers, json=body, timeout=60)
        except requests.exceptions.RequestException as e:
            return False, f"连接大模型服务失败：{e}"
        if r.status_code != 200:
            return False, f"大模型服务返回错误 {r.status_code}：{r.text[:200]}"

        msg = r.json()["choices"][0]["message"]

        # 模型要求调用工具 → 执行 → 结果回传
        if msg.get("tool_calls"):
            full.append(msg)
            for tc in msg["tool_calls"]:
                fn = tc["function"]
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                ok, result = tools.execute_tool(fn["name"], args)
                if not ok:
                    result = f"[工具失败] {result}"
                full.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
            continue

        # 模型给出了最终回答
        return True, msg.get("content") or "（没有回答）"

    return False, "工具调用次数过多，请简化你的请求。"


def test_connection():
    """
    测试 API Key 和模型配置是否可用（发一条最小的请求，几乎不花钱）。
    返回 (是否成功, 提示文字)。
    """
    key = _api_key()
    if not key:
        return False, "还没有配置 API Key，请先在上方填写。"
    provider = models.get_setting("agent_provider") or "zhipu"
    p = config.AGENT_PROVIDERS.get(provider, config.AGENT_PROVIDERS["zhipu"])
    model = models.get_setting("agent_model") or p["default_model"]
    url = p["base_url"].rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    body = {"model": model, "messages": [{"role": "user", "content": "你好"}], "max_tokens": 5}

    try:
        r = requests.post(url, headers=headers, json=body, timeout=30)
    except requests.exceptions.RequestException as e:
        return False, f"网络连接失败：{e}"
    if r.status_code == 200:
        return True, f"连接成功（{p['label']}，模型 {model}）"
    if r.status_code == 401:
        return False, "API Key 无效（401），请检查是否复制完整、有没有多余空格。"
    if r.status_code == 404:
        return False, f"模型名不存在（404）：{model}。DeepSeek 请用 deepseek-v4-flash 或 deepseek-v4-pro"
    return False, f"服务返回错误 {r.status_code}：{r.text[:150]}"


# ==================== 模拟模式：不联网的关键词应答 ====================
# 用途：开发测试、"还没配 API Key"时的兜底演示。配好 Key 后自动用真实模式。

def mock_chat(messages):
    # 取最近一条用户消息
    last = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last = m.get("content", "")
            break
    text = last

    if any(w in text for w in ("DDL", "考试", "作业", "截止", "任务", "到期", "交")):
        return "【模拟模式】我查了一下你的 DDL：\n" + tools._pending_ddls_text()
    if any(w in text for w in ("资料", "课件", "文件", "文档", "找")):
        return "【模拟模式】资料库的情况：\n" + tools._materials_text()
    if "复习" in text:
        return "【模拟模式】复习计划：\n" + tools._review_text()
    if "课程" in text:
        return "【模拟模式】你的课程：\n" + tools._courses_text()
    return ("【模拟模式】我收到你的消息了！配置真实的大模型 API Key 后"
            "（设置页，推荐完全免费的智谱 GLM-4.7-Flash），我就能准确理解并执行你的请求了。")
