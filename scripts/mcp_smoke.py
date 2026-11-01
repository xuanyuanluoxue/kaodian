#!/usr/bin/env python3
"""MCP 冒烟测试：通过 stdio 连接 server.py，列工具并调用一次 list_subjects。

用法：
    KAODIAN_API=http://127.0.0.1:8010 .venv/bin/python scripts/mcp_smoke.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


async def main() -> int:
    env = dict(os.environ)
    env.setdefault("KAODIAN_API", "http://127.0.0.1:8010")
    env.setdefault("KAODIAN_WEB", env["KAODIAN_API"])
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(ROOT / "apps" / "mcp" / "server.py")],
        env=env,
        cwd=str(ROOT),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            print(f"tools ({len(names)}): {', '.join(names)}")
            result = await session.call_tool("list_subjects", {})
            text = "\n".join(c.text for c in result.content if getattr(c, "text", None))
            if "computer" not in text:
                print("list_subjects 未返回 computer，可能 API 未启动")
                return 1
            print("list_subjects: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))