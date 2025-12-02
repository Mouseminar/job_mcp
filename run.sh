#!/bin/bash
set -e
echo "========================================"
echo "🚀 job_mcp 启动脚本"
echo "========================================"

# 找到 Python
if [ -f "/opt/python3.12/bin/python3.12" ]; then
    PYTHON="/opt/python3.12/bin/python3.12"
elif [ -f "/usr/local/bin/python3.12" ]; then
    PYTHON="/usr/local/bin/python3.12"
else
    PYTHON="python3"
fi

echo "Python 路径: $PYTHON"

if [ -d "/code" ]; then
    cd /code
else
    echo "注意: /code 不存在，使用当前目录"
fi

if [ ! -f "mcp_server.py" ]; then
    echo "错误: mcp_server.py 不存在" >&2
    exit 1
fi

export PORT=${PORT:-9000}
exec $PYTHON mcp_server.py
