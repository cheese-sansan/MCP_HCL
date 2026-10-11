"""Capture declarations from hash-pinned Python registries without importing them."""

import argparse
import ast
import hashlib
import json
from pathlib import Path


def declarations(source: bytes, kind: str) -> dict:
    result = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and isinstance(decorator.func.value, ast.Name)
                and decorator.func.value.id == "mcp"
                and decorator.func.attr == kind
            ):
                continue
            if decorator.keywords or (kind == "tool" and decorator.args):
                raise ValueError("Unsupported registration declaration")
            name = node.name
            if kind == "resource":
                if len(decorator.args) != 1:
                    raise ValueError("Resource requires a literal URI")
                name = ast.literal_eval(decorator.args[0])
            if not isinstance(name, str) or name in result:
                raise ValueError("Duplicate or invalid declaration")
            if node.args.posonlyargs or node.args.vararg or node.args.kwarg:
                raise ValueError("Unsupported variadic declaration")
            parameters = []
            defaults = [None] * (len(node.args.args) - len(node.args.defaults))
            defaults += node.args.defaults
            for argument, default in zip(
                node.args.args + node.args.kwonlyargs,
                defaults + node.args.kw_defaults,
                strict=True,
            ):
                item = {
                    "name": argument.arg,
                    "annotation": ast.unparse(argument.annotation) if argument.annotation else None,
                    "required": default is None,
                }
                if default is not None:
                    try:
                        item["default"] = {"kind": "literal", "value": ast.literal_eval(default)}
                    except (ValueError, TypeError):
                        item["default"] = {"kind": "expression", "source": ast.unparse(default)}
                parameters.append(item)
            result[name] = {
                "parameters": parameters,
                "return_annotation": ast.unparse(node.returns) if node.returns else None,
            }
    return dict(sorted(result.items()))


def capture(tool_source: bytes, resource_source: bytes, inventory: dict) -> dict:
    sources = {}
    for kind, source in (("tool", tool_source), ("resource", resource_source)):
        digest = hashlib.sha256(source).hexdigest()
        if digest != inventory["upstream"][f"{kind}_registry_sha256"]:
            raise ValueError(f"{kind} registry does not match the pinned source bytes")
        sources[kind + "_registry_sha256"] = digest
    tools = declarations(tool_source, "tool")
    resources = declarations(resource_source, "resource")
    if set(tools) != {row["upstream_tool"] for row in inventory["tools"]}:
        raise ValueError("Tool declarations do not match the inventory")
    if set(resources) != {row["upstream_uri"] for row in inventory["resources"]}:
        raise ValueError("Resource declarations do not match the inventory")
    return {
        "schema_version": 1,
        "revision": inventory["upstream"]["revision"],
        "verified_scope": "python_declarations_only; nested models and runtime behavior unverified",
        "sources": sources,
        "tools": tools,
        "resources": resources,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool-registry", type=Path, required=True)
    parser.add_argument("--resource-registry", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    snapshot = capture(
        args.tool_registry.read_bytes(),
        args.resource_registry.read_bytes(),
        json.loads(args.inventory.read_text(encoding="utf-8")),
    )
    args.output.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    main()
