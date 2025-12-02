#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Job / Intern 搜索 MCP 包装器
将 `search_job.search_jobs` 和 `search_intern.search_interns_selenium` 封装为 FastMCP 工具
"""

import os
import json
import logging
import asyncio
from dotenv import load_dotenv
from fastmcp import FastMCP

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("job_mcp.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv()

# 创建 MCP
mcp = FastMCP("job-mcp")

# 导入搜索函数（同步）
try:
    from search_job import search_jobs
except Exception as e:
    logger.warning("无法导入 search_job.search_jobs: %s", e)
    search_jobs = None

try:
    from search_intern import search_interns_selenium
except Exception as e:
    logger.warning("无法导入 search_intern.search_interns_selenium: %s", e)
    search_interns_selenium = None


@mcp.tool()
async def job_search_tool(
    position: str,
    city: str = "",
    experience: str = "",
    education: str = "",
    salary: str = "",
    page: int = 1,
    page_size: int = 20,
    sources: list = None,
    save_to_file: bool = False,
    output_file: str = "jobs_result.json"
) -> str:
    """通过封装的爬虫搜索职位，返回 JSON 字符串结果"""
    if search_jobs is None:
        return "错误: search_jobs 未可用"

    try:
        # 调用同步函数到线程池中
        result = await asyncio.to_thread(
            search_jobs,
            position,
            city,
            experience,
            education,
            salary,
            page,
            page_size,
            sources,
            save_to_file,
            output_file,
        )
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.exception("job_search_tool 失败")
        return f"搜索失败: {str(e)}"


@mcp.tool()
async def intern_search_tool(
    position: str,
    city: str = "",
    education: str = "",
    duration: str = "",
    days_per_week: str = "",
    page: int = 1,
    page_size: int = 20,
    sources: list = None,
    headless: bool = True,
    save_to_file: bool = False,
    output_file: str = "interns_result.json"
) -> str:
    """通过 intern 爬虫搜索实习信息，返回 JSON 字符串结果"""
    if search_interns_selenium is None:
        return "错误: search_interns_selenium 未可用"

    try:
        result = await asyncio.to_thread(
            search_interns_selenium,
            position=position,
            city=city,
            education=education,
            duration=duration,
            days_per_week=days_per_week,
            page=page,
            page_size=page_size,
            sources=sources,
            headless=headless,
            save_to_file=save_to_file,
            output_file=output_file,
        )
        # 有些实现会直接保存并返回 None 或文件路径，标准化为字典
        if isinstance(result, str):
            try:
                parsed = json.loads(result)
                return json.dumps(parsed, ensure_ascii=False, indent=2)
            except Exception:
                return json.dumps({"result": result}, ensure_ascii=False)

        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.exception("intern_search_tool 失败")
        return f"搜索失败: {str(e)}"


def main():
    logger.info("启动 Job/Intern MCP 服务器")
    port = int(os.environ.get("MCP_PORT", os.environ.get("PORT", "9000")))
    mcp.run(
        transport="sse",
        host="0.0.0.0",
        port=port,
        path="/sse",
        log_level="info",
    )


if __name__ == "__main__":
    main()
