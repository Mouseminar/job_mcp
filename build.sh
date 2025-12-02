#!/bin/bash
# 构建脚本 - 安装依赖到正确的位置

set -e

echo "========================================="
echo "📦 开始安装依赖"
echo "========================================="
echo "当前目录: $(pwd)"

# 查找 Python 3.12
if [ -f "/opt/python3.12/bin/python3.12" ]; then
    PYTHON="/opt/python3.12/bin/python3.12"
elif [ -f "/opt/python3.12/bin/python" ]; then
    PYTHON="/opt/python3.12/bin/python"
elif command -v python3.12 &> /dev/null; then
    PYTHON="python3.12"
else
    echo "⚠️  警告: 未找到 Python 3.12，使用默认 Python"
    PYTHON="python3"
fi

echo "Python 版本: $($PYTHON --version)"
echo "Pip 版本: $($PYTHON -m pip --version)"
echo "系统架构: $(uname -m)"
echo "========================================="

# 创建 python 依赖目录
mkdir -p python

# 升级 pip 和 setuptools
$PYTHON -m pip install --upgrade pip setuptools wheel

# 安装依赖到 python 目录
# 不使用预编译包限制，让 pip 自动选择合适的版本
echo "安装依赖到 ./python 目录..."
$PYTHON -m pip install -r requirements.txt -t python --upgrade --no-cache-dir

echo "========================================="
echo "✓ 依赖安装完成"
echo "========================================="
echo "检查关键包:"
if [ -d "python/pydantic_core" ]; then
    echo "✓ pydantic_core 已安装"
    ls -la python/pydantic_core/*.so 2>/dev/null | head -5 || echo "  (无 .so 文件)"
else
    echo "✗ pydantic_core 未安装"
fi

if [ -d "python/fastmcp" ]; then
    echo "✓ fastmcp 已安装"
else
    echo "✗ fastmcp 未安装"
fi
echo "========================================="
