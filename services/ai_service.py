import json
import logging

import requests

from constants import AI_CONFIGS

logger = logging.getLogger(__name__)

CONCISE_SYSTEM_PROMPT = (
    "你是一名阀门、管件、流量计行业的技术顾问。"
    "回答问题时优先依据提供的内部知识库资料，结合自身专业知识作答。"
    "涉及标准/材质/压力时标注标准号和牌号。"
    "不确定时如实说明，不编造信息。"
    "回答使用清晰的结构化格式（分点、小标题）。"
)


def _build_reference_text(question: str, kb_content: str, web_content: str) -> str:
    parts = [f"用户问题：{question}"]
    if kb_content and kb_content.strip():
        parts.append(f"内部知识库资料（请优先采用）：\n{kb_content}")
    if web_content and web_content.strip():
        parts.append(f"联网搜索结果（仅供参考）：\n{web_content}")
    return "\n\n".join(parts)


def _build_messages(question: str, kb_content: str, web_content: str,
                    history: list[dict] | None = None) -> list[dict]:
    reference = _build_reference_text(question, kb_content, web_content)
    messages = [{"role": "system", "content": CONCISE_SYSTEM_PROMPT}]
    if history:
        messages += history
    messages.append({"role": "user", "content": reference})
    return messages


def _build_zhipu_messages(question: str, kb_content: str, web_content: str) -> list[dict]:
    system_content = CONCISE_SYSTEM_PROMPT
    if kb_content and kb_content.strip():
        system_content += f"\n\n内部知识库资料（请优先采用）：\n{kb_content}"
    if web_content and web_content.strip():
        system_content += f"\n\n联网搜索结果（仅供参考）：\n{web_content}"
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": question},
    ]


def _stream_response(response: requests.Response,
                     stream_callback: callable,
                     cancelled_flag: callable,
                     is_ollama: bool = False) -> str:
    full_response: list[str] = []
    for line in response.iter_lines():
        if cancelled_flag():
            response.close()
            break
        if not line:
            continue
        try:
            line_str = line.decode("utf-8", errors="replace").strip()
            if line_str.startswith("data: "):
                data_str = line_str[6:]
                if data_str.strip() == "[DONE]":
                    break
            elif is_ollama:
                data_str = line_str
                if data_str == "done" or '"done":true' in data_str:
                    break
            else:
                continue

            chunk = json.loads(data_str)
            content = ""
            if is_ollama:
                content = chunk.get("message", {}).get("content", "") or chunk.get("response", "")
            else:
                content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")

            if content:
                full_response.append(content)
                current = "".join(full_response)
                if stream_callback:
                    stream_callback(current)
        except json.JSONDecodeError:
            logger.warning("AI流式响应解析失败，跳过异常行: %s", line[:100])
        except Exception as e:
            logger.warning("AI流式响应处理异常: %s", e)

    response.close()
    return "".join(full_response)


def call_ollama(question: str, kb_content: str, web_content: str,
                stream_callback: callable = None, cancelled_flag: callable = lambda: False,
                history: list[dict] | None = None,
                custom_config: dict | None = None) -> str:
    config = dict(AI_CONFIGS["ollama"])
    if custom_config:
        config.update(custom_config)
    messages = _build_messages(question, kb_content, web_content, history)
    data = {
        "model": config["model"],
        "messages": messages,
        "stream": True,
        "options": {"temperature": 0.3, "num_predict": 2048},
    }
    try:
        response = requests.post(config["api_url"], json=data, timeout=(5, 15), stream=True)
        if response.status_code == 200:
            return _stream_response(response, stream_callback, cancelled_flag, is_ollama=True)
        return f"Ollama返回异常（状态码{response.status_code}）"
    except requests.exceptions.ConnectionError:
        return "无法连接到Ollama服务（http://localhost:11434），请确认Ollama已启动"
    except requests.exceptions.ReadTimeout:
        return "Ollama响应超时（15秒），请确认模型已加载且非量化模型文件完整"
    except Exception as e:
        return f"Ollama调用失败: {e}"


def call_openai_compat(provider: str, question: str, kb_content: str,
                       web_content: str, api_key: str = "",
                       stream_callback: callable = None,
                       cancelled_flag: callable = lambda: False,
                       history: list[dict] | None = None,
                       custom_config: dict | None = None) -> str:
    base_config = AI_CONFIGS.get(provider)
    if not base_config:
        return "AI服务配置错误，请检查设置"
    config = dict(base_config)
    if custom_config:
        config.update(custom_config)

    headers = {"Content-Type": "application/json"}
    if config.get("need_key"):
        if not api_key:
            return "当前服务需要API Key，请在设置菜单中填写"
        headers["Authorization"] = f"Bearer {api_key}"

    messages = _build_messages(question, kb_content, web_content, history)
    data = {
        "model": config["model"],
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 2048,
        "stream": True,
    }

    try:
        response = requests.post(config["api_url"], headers=headers, json=data, timeout=(5, 15), stream=True)
        if response.status_code == 200:
            return _stream_response(response, stream_callback, cancelled_flag)
        if response.status_code == 401:
            return "API Key错误或无权限，请检查设置"
        if response.status_code == 429:
            return "API调用频率限制，请稍后再试"
        return f"AI返回异常（状态码{response.status_code}），请检查API配置"
    except requests.exceptions.ConnectionError:
        return f"无法连接到AI服务（{config['api_url']}），请确认服务已启动"
    except requests.exceptions.ReadTimeout:
        return f"AI服务响应超时（15秒），请检查网络或服务负载"
    except Exception as e:
        return f"AI调用失败: {e}"


def call_zhipu_websearch(question: str, kb_content: str, web_content: str, api_key: str,
                         stream_callback: callable = None,
                         cancelled_flag: callable = lambda: False,
                         history: list[dict] | None = None,
                         custom_config: dict | None = None) -> str:
    base_config = AI_CONFIGS.get("zhipu_cloud")
    if not base_config:
        return "[错误] 智谱云配置错误"
    config = dict(base_config)
    if custom_config:
        config.update(custom_config)
    if not api_key:
        return "[错误] 智谱 API Key 为空，请在设置中填写"

    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    messages = _build_messages(question, kb_content, web_content, history)
    payload = {
        "model": config["model"],
        "messages": messages,
        "stream": True,
        "temperature": 0.3,
    }

    try:
        response = requests.post(config["api_url"], headers=headers, json=payload,
                                 stream=True, timeout=(5, 15))
        if response.status_code != 200:
            err_body = response.text[:300] if response.text else "无响应体"
            logger.error("智谱API返回非200状态码: %s, body=%s", response.status_code, err_body)
            if response.status_code == 401:
                return "[错误] 智谱 API Key 错误或无权限，请检查设置中的 API Key"
            if response.status_code == 429:
                return "[错误] 智谱 API 调用频率限制，请稍后再试"
            return f"[错误] 智谱API返回{response.status_code}：{err_body}"

        return _stream_response(response, stream_callback, cancelled_flag)
    except requests.exceptions.ConnectionError:
        return "[错误] 无法连接到智谱API（open.bigmodel.cn），请检查网络连接"
    except requests.exceptions.ReadTimeout:
        return "[错误] 智谱API响应超时（15秒），请检查网络或重试"
    except Exception as e:
        logger.error("智谱API调用异常: %s", e, exc_info=True)
        return f"[错误] 智谱API调用异常: {e}"