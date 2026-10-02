"""One structured-output adapter shared by every autonomous agent."""

import json
import os
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

DEFAULT_MODEL = "qwen3.7-plus"
T = TypeVar("T", bound=BaseModel)


def _create_openai_client() -> Any:
    """Create the configured OpenAI-compatible client without storing secrets."""
    try:
        from openai import OpenAI
    except ModuleNotFoundError as error:
        raise RuntimeError("尚未安装 OpenAI SDK，请运行 pip install -r requirements.txt") from error
    api_key = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key or len(api_key.strip()) < 20:
        raise RuntimeError("尚未设置有效的 DASHSCOPE_API_KEY 或 OPENAI_API_KEY")
    options: dict[str, str] = {"api_key": api_key.strip()}
    base_url = os.environ.get("SHOPPING_AGENT_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
    if base_url:
        options["base_url"] = base_url.strip().rstrip("/")
    if DEFAULT_MODEL.startswith("qwen") and not base_url:
        raise RuntimeError("Qwen 模型需要设置 SHOPPING_AGENT_BASE_URL")
    return OpenAI(**options)


def invoke_structured(
    system_prompt: str,
    user_prompt: str,
    response_model: type[T],
    *,
    client: Any | None = None,
    model: str | None = None,
) -> T:
    """Call OpenAI or an OpenAI-compatible model and validate locally."""

    active_client = client or _create_openai_client()
    active_model = model or os.environ.get("SHOPPING_AGENT_MODEL", DEFAULT_MODEL)
    schema = json.dumps(response_model.model_json_schema(), ensure_ascii=False)
    messages = [
        {
            "role": "system",
            "content": (
                f"{system_prompt}\n只输出符合以下 JSON Schema 的 JSON 对象：\n{schema}"
            ),
        },
        {"role": "user", "content": user_prompt},
    ]
    if active_model.startswith("qwen"):
        completion = active_client.chat.completions.create(
            model=active_model,
            messages=messages,
            response_format={"type": "json_object"},
            extra_body={"enable_thinking": False},
        )
        if not completion.choices:
            raise RuntimeError("模型没有返回候选结果")
        content = completion.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("模型没有返回 JSON")
        try:
            return response_model.model_validate_json(content)
        except ValidationError as error:
            raise RuntimeError(f"模型输出未通过 {response_model.__name__} 校验：{error}") from error

    completion = active_client.chat.completions.parse(
        model=active_model,
        messages=messages,
        response_format=response_model,
    )
    if not completion.choices:
        raise RuntimeError("模型没有返回候选结果")
    parsed = completion.choices[0].message.parsed
    if parsed is None:
        raise RuntimeError("模型没有返回结构化结果")
    return response_model.model_validate(parsed)
