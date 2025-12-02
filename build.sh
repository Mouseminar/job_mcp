#!/bin/bash
set -e
echo "========================================="
echo "📦 job_mcp: 安装依赖到 ./python 目录"
echo "========================================="

# 选择 Python
if [ -f "/opt/python3.12/bin/python3.12" ]; then
    PYTHON="/opt/python3.12/bin/python3.12"
elif command -v python3.12 &> /dev/null; then
    PYTHON="python3.12"
else
    PYTHON="python3"
fi

echo "使用 Python: $($PYTHON --version)"

mkdir -p python
$PYTHON -m pip install --upgrade pip setuptools wheel

echo "安装 requirements.txt 到 ./python"
$PYTHON -m pip install -r requirements.txt -t python --upgrade --no-cache-dir

echo "依赖安装完成"
echo "========================================="
