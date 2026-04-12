from __future__ import annotations

import json
import os
from typing import Any
from uuid import uuid4

import requests

FIRECRAWL_MCP_URL = "https://mcp.gumloop.com/firecrawl/mcp"
APOLLO_MCP_URL = "https://mcp.gumloop.com/apollo/mcp"


class GumloopMcpClient:
    def __init__(self, bearer_token: str):
        token = (bearer_token or "").strip()
        if not token:
            raise ValueError("Missing GUMLOOP_MCP_TOKEN.")
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

    def _rpc(self, endpoint: str, method: str, params: dict | None = None) -> dict:
        body = {
            "jsonrpc": "2.0",
            "id": str(uuid4()),
            "method": method,
            "params": params or {},
        }
        response = requests.post(
            endpoint, headers=self.headers, data=json.dumps(body), timeout=45
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and payload.get("error"):
            raise ValueError(str(payload["error"]))
        return payload

    def list_tools(self, endpoint: str) -> list[dict]:
        payload = self._rpc(endpoint, "tools/list")
        result = payload.get("result", {})
        tools = result.get("tools", [])
        return tools if isinstance(tools, list) else []

    def call_tool(self, endpoint: str, name: str, arguments: dict) -> dict:
        payload = self._rpc(
            endpoint, "tools/call", params={"name": name, "arguments": arguments}
        )
        result = payload.get("result", {})
        return result if isinstance(result, dict) else {"raw_result": result}


def _tool_candidates(tools: list[dict], keywords: list[str]) -> list[str]:
    scored: list[tuple[int, str]] = []
    for tool in tools:
        name = str(tool.get("name", ""))
        hay = f"{name} {tool.get('description', '')}".lower()
        score = sum(1 for word in keywords if word in hay)
        if score > 0:
            scored.append((score, name))
    scored.sort(reverse=True)
    return [name for _score, name in scored]


def _prioritize_tool(candidates: list[str], preferred_tool: str) -> list[str]:
    unique = []
    seen = set()
    for item in candidates:
        if item not in seen:
            unique.append(item)
            seen.add(item)
    if preferred_tool in unique:
        unique.remove(preferred_tool)
    return [preferred_tool] + unique


def _extract_text(result: Any) -> str:
    if isinstance(result, str):
        return result.strip()
    if isinstance(result, dict):
        if "text" in result and isinstance(result["text"], str):
            return result["text"].strip()
        if "content" in result and isinstance(result["content"], list):
            chunks: list[str] = []
            for item in result["content"]:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    chunks.append(item["text"])
            if chunks:
                return "\n".join(chunks).strip()
        return json.dumps(result, indent=2)
    if isinstance(result, list):
        return "\n".join(_extract_text(item) for item in result).strip()
    return str(result)


def _is_error_payload_text(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return False
    lowered = stripped.lower()
    substring_markers = [
        "error_status",
        "traceback",
        "no credentials available",
        "credentials not found for user",
        "authentication first",
        "managed key is configured",
        "input validation error",
        "is a required property",
        "invalid_request",
    ]
    if any(marker in lowered for marker in substring_markers):
        return True
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return False
    if not isinstance(parsed, dict):
        return False
    keys = {str(key).lower() for key in parsed.keys()}
    error_markers = {"error", "error_status", "traceback", "message"}
    if keys.intersection(error_markers):
        return True
    message = str(parsed.get("message", "")).lower()
    return "credentials not found" in message or "authentication first" in message


def _is_credentials_error_text(text: str) -> bool:
    lowered = (text or "").lower()
    return any(
        marker in lowered
        for marker in [
            "no credentials available",
            "credentials not found for user",
            "authentication first",
            "managed key is configured",
        ]
    )


def scrape_onboarding_data(
    linkedin_url: str, job_url: str, gumloop_token: str | None = None
) -> dict:
    token = (gumloop_token or os.getenv("GUMLOOP_MCP_TOKEN", "")).strip()
    client = GumloopMcpClient(token)

    output: dict[str, str] = {
        "job_description": "",
        "candidate_context": "",
        "job_source": "",
        "linkedin_source": "",
    }

    if job_url.strip():
        firecrawl_tools = client.list_tools(FIRECRAWL_MCP_URL)
        firecrawl_tool_names = {tool.get("name", "") for tool in firecrawl_tools}
        firecrawl_candidates = _tool_candidates(
            firecrawl_tools, ["scrape", "crawl", "extract", "website", "url"]
        )
        if "scrape" in firecrawl_tool_names:
            firecrawl_candidates = _prioritize_tool(firecrawl_candidates, "scrape")
        if not firecrawl_candidates:
            raise ValueError("No scrape-like tool found on Firecrawl MCP server.")
        last_error = None
        for tool_name in firecrawl_candidates[:3]:
            for args in [
                {"url": job_url.strip()},
                {"urls": [job_url.strip()]},
                {"query": job_url.strip()},
            ]:
                try:
                    result = client.call_tool(FIRECRAWL_MCP_URL, tool_name, args)
                    text = _extract_text(result)
                    if isinstance(result, dict) and bool(result.get("isError")):
                        last_error = ValueError(text or "Firecrawl tool returned an error.")
                        if _is_error_payload_text(text):
                            raise last_error
                        continue
                    if text:
                        if _is_error_payload_text(text):
                            last_error = ValueError(text)
                            continue
                        output["job_description"] = text
                        output["job_source"] = tool_name
                        last_error = None
                        break
                except Exception as exc:
                    if _is_credentials_error_text(str(exc)):
                        raise
                    last_error = exc
            if output["job_description"]:
                break
        if not output["job_description"] and last_error:
            raise ValueError(f"Firecrawl scrape failed: {last_error}")

    if linkedin_url.strip():
        apollo_tools = client.list_tools(APOLLO_MCP_URL)
        apollo_tool_names = {tool.get("name", "") for tool in apollo_tools}
        apollo_candidates = _tool_candidates(
            apollo_tools, ["linkedin", "person", "profile", "enrich", "lookup"]
        )
        if "enrich_person" in apollo_tool_names:
            apollo_candidates = _prioritize_tool(apollo_candidates, "enrich_person")
        if not apollo_candidates:
            raise ValueError("No LinkedIn/profile tool found on Apollo MCP server.")
        last_error = None
        for tool_name in apollo_candidates[:3]:
            for args in [
                {"linkedin_url": linkedin_url.strip()},
                {"profile_url": linkedin_url.strip()},
                {"url": linkedin_url.strip()},
            ]:
                try:
                    result = client.call_tool(APOLLO_MCP_URL, tool_name, args)
                    text = _extract_text(result)
                    if isinstance(result, dict) and bool(result.get("isError")):
                        last_error = ValueError(text or "Apollo tool returned an error.")
                        if _is_error_payload_text(text):
                            raise last_error
                        continue
                    if text:
                        if _is_error_payload_text(text):
                            last_error = ValueError(text)
                            continue
                        output["candidate_context"] = text
                        output["linkedin_source"] = tool_name
                        last_error = None
                        break
                except Exception as exc:
                    if _is_credentials_error_text(str(exc)):
                        raise
                    last_error = exc
            if output["candidate_context"]:
                break
        if not output["candidate_context"] and last_error:
            raise ValueError(f"Apollo profile scrape failed: {last_error}")

    return output
