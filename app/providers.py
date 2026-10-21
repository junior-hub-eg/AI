"""Binding the tools to a model. Most providers take LangChain's tools as they are; Cohere needs its own shape."""

from __future__ import annotations

from typing import Any, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool


def is_cohere(model: BaseChatModel) -> bool:
    return type(model).__name__ == "ChatCohere"


def bind(model: BaseChatModel, tools: Sequence[BaseTool], tool_choice: str, force: str | None = None) -> Runnable:
    """The model with `tools` offered.

    tool_choice "auto": the model may answer without a tool. Otherwise a tool call is required; `force` names the one
    tool to call where the provider supports that (OpenAI, Anthropic, Gemini). Cohere can only require *a* tool call,
    which is enough because it is only offered the one tool when `force` is set.
    """
    if is_cohere(model):
        return _bind_cohere(model, tools, required=tool_choice != "auto")
    if tool_choice == "auto":
        return model.bind_tools(tools)
    return model.bind_tools(tools, tool_choice=force or tool_choice)


def _bind_cohere(model: BaseChatModel, tools: Sequence[BaseTool], required: bool) -> Runnable:
    # langchain-cohere's own conversion drops enums, item shapes and parameter descriptions (the `topic` values and
    # the shape of `links`), so the full JSON schema is sent instead, simplified to what Cohere accepts.
    from cohere import ToolV2, ToolV2Function

    specs = []
    for tool in tools:
        fn = convert_to_openai_tool(tool)["function"]
        specs.append(ToolV2(type="function", function=ToolV2Function(
            name=fn["name"], description=fn.get("description", ""),
            parameters=simplify_schema(fn.get("parameters") or {"type": "object", "properties": {}}),
        )))
    # Cohere cites tool results inline by default ("<co>...</co: 0:[0]>" inside the text); citations are not used here.
    extra: dict[str, Any] = {"citation_options": {"mode": "OFF"}}
    if required:
        extra["tool_choice"] = "REQUIRED"
    return model.bind(tools=specs, **extra)


def simplify_schema(schema: Any) -> Any:
    """Optional fields become plain types (anyOf [X, null] → X), and null defaults and titles are dropped."""
    if isinstance(schema, list):
        return [simplify_schema(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    if "anyOf" in schema:
        options = [o for o in schema["anyOf"] if not (isinstance(o, dict) and o.get("type") == "null")]
        if len(options) == 1:
            merged = {**{k: v for k, v in schema.items() if k != "anyOf"}, **options[0]}
            return simplify_schema(merged)
    return {k: simplify_schema(v) for k, v in schema.items() if k != "title" and not (k == "default" and v is None)}
