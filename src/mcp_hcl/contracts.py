"""Strict raw MCP arguments and a request-correlated result envelope."""
from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import CallToolResult, TextContent
from pydantic import ConfigDict, ValidationError, create_model


def validation_errors(exc: ValidationError) -> list[dict[str, Any]]:
    return [{"code": row["type"], "message": row["msg"], "path": list(row["loc"])}
            for row in exc.errors(include_input=False, include_context=False, include_url=False)]


def envelope(body: dict[str, Any], *, request_id: Any = None,
             operation: str | None = None, target: Any = None) -> dict[str, Any]:
    result = dict(body)
    if "request_id" in result:
        result["backend_request_id"] = result.pop("request_id")
    result.setdefault("status", "verified")
    result.setdefault("operation_id", uuid4().hex)
    result.update(request_id=request_id, contract_version=2)
    result.setdefault("operation", operation)
    result.setdefault("target", result.get("target_project", target))
    result.setdefault("verified_scope", "offline_result_only" if result["status"] in
                      {"ok", "verified", "staged"} else "none")
    result.setdefault("evidence", [])
    result.setdefault("errors", [{"code": "operation_failed", "message": result["error"]}]
                      if result.get("error") else [])
    result.setdefault("warnings", [])
    result.setdefault("runtime_verified", False)
    result.setdefault("full_live_gate_passed", False)
    return result


class StrictFastMCP(FastMCP):
    """Validate BEFORE FastMCP's JSON pre-parsing or numeric coercion.

    The adapter is intentionally isolated from the SDK's implementation details.
    The same generated model supplies tools/list and calls/tool validation.
    """

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._strict_models: dict[str, Any] = {}
        self.artifact_retries: Any = None

    def _model(self, tool: Any) -> Any:
        if tool.name not in self._strict_models:
            model = create_model(tool.name + "Arguments", __base__=tool.fn_metadata.arg_model,
                                 __config__=ConfigDict(strict=True, extra="forbid", allow_inf_nan=False))
            tool.parameters = model.model_json_schema()
            self._strict_models[tool.name] = model
        return self._strict_models[tool.name]

    async def list_tools(self) -> Any:
        for tool in self._tool_manager.list_tools():
            self._model(tool)
        return await super().list_tools()

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> CallToolResult:
        context = self.get_context()
        try:
            request_id = context.request_id
        except (ValueError, LookupError):
            request_id = None
        tool = self._tool_manager.get_tool(name)
        is_error = False
        target = arguments.get("project_path", arguments.get("artifact_directory"))
        if tool is None:
            body = {"status": "rejected", "errors": [{"code": "unknown_tool", "message": name}]}
            is_error = True
        else:
            try:
                validated = self._model(tool).model_validate(arguments).model_dump_one_level()
            except ValidationError as exc:
                body = {"status": "rejected", "errors": validation_errors(exc)}
                is_error = True
            else:
                try:
                    if self.artifact_retries and name.startswith("hcl_stage_"):
                        body = self.artifact_retries.run(
                            name, validated, lambda: tool.fn(**validated),
                            source=validated.get("project_path"))
                    else:
                        body = await tool.run(validated, context=context, convert_result=False)
                except (ValueError, OSError) as exc:
                    body = {"status": "rejected", "error": str(exc),
                            "errors": [{"code": "invalid_operation", "message": str(exc)}]}
                except ToolError:
                    body = {"status": "unverified", "errors": [{"code": "internal_error", "message": "The operation failed without a verified result"}]}
                    is_error = True
        body = envelope(body, request_id=request_id, operation=name, target=target)
        return CallToolResult(isError=is_error, structuredContent=body,
                              content=[TextContent(type="text", text=json.dumps(body, ensure_ascii=False))])
