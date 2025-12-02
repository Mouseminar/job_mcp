#!/bin/bash
# 阿里云函数计算启动脚本
# 使用绝对路径确保能找到 Python 和代码文件

set -e

echo "========================================" >&2
echo "🚀 启动脚本开始执行" >&2
echo "========================================" >&2
echo "当前目录: $(pwd)" >&2
echo "用户: $(whoami)" >&2
echo "========================================" >&2

# 查找 Python 3.12（优先使用层中的 Python 3.12）
if [ -f "/opt/python3.12/bin/python3.12" ]; then
    PYTHON="/opt/python3.12/bin/python3.12"
    echo "✓ 找到 Python 3.12 (层)" >&2
elif [ -f "/opt/python3.12/bin/python" ]; then
    PYTHON="/opt/python3.12/bin/python"
    echo "✓ 找到 Python 3.12" >&2
elif [ -f "/usr/local/bin/python3.12" ]; then
    PYTHON="/usr/local/bin/python3.12"
    echo "✓ 找到 Python 3.12 (系统)" >&2
elif [ -f "/usr/bin/python3.12" ]; then
    PYTHON="/usr/bin/python3.12"
    echo "✓ 找到 Python 3.12 (系统)" >&2
else
    echo "⚠️  未找到 Python 3.12，使用默认 Python" >&2
    PYTHON="python3"
fi

echo "Python 路径: $PYTHON" >&2
echo "Python 版本: $($PYTHON --version)" >&2

# 确保在代码目录
if [ -d "/code" ]; then
    cd /code
    echo "切换到 /code 目录" >&2
else
    echo "警告: /code 目录不存在，当前目录: $(pwd)" >&2
fi

# 列出文件
echo "目录内容:" >&2
ls -la >&2

# 检查 mcp_server.py 是否存在
if [ ! -f "mcp_server.py" ]; then
    echo "错误: mcp_server.py 不存在！" >&2
    exit 1
fi

echo "========================================" >&2
echo "🚀 启动 MCP 服务器" >&2
echo "========================================" >&2

# 设置端口环境变量（阿里云函数计算会传入 PORT 环境变量）
export PORT=${PORT:-9000}

# 使用 exec 替换当前进程
exec $PYTHON mcp_server.py

