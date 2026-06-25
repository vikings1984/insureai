#!/bin/bash
# InsureScope 快速启动脚本

set -e

echo "📋 InsureScope - AI 驱动的保险信息聚合系统"
echo "============================================"

# 检查 Python 版本
PYTHON_VERSION=$(python3 --version 2>/dev/null | grep -oP '\d+\.\d+' || echo "0.0")
if [ "$(echo "$PYTHON_VERSION >= 3.10" | bc -l)" -eq 0 ]; then
    echo "❌ 需要 Python 3.10+，当前: $PYTHON_VERSION"
    exit 1
fi

# 检查 .env 文件
if [ ! -f .env ]; then
    echo "⚠️  未找到 .env 文件，从模板创建..."
    cp .env.example .env
    echo "📝 请编辑 .env 文件，填入你的 API Key"
    echo "   必填: OPENAI_API_KEY"
    echo ""
    read -p "是否现在编辑 .env? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        ${EDITOR:-nano} .env
    else
        echo "请稍后手动编辑 .env 文件"
    fi
fi

# 安装依赖
echo "📦 安装依赖..."
uv sync 2>/dev/null || pip install -e .

# 验证配置
echo "🔍 验证配置..."
uv run insure-scope validate || python -m src.main validate

echo ""
echo "✅ 准备就绪!"
echo ""
echo "使用方法:"
echo "  运行采集:  uv run insure-scope run"
echo "  启动 API:  uv run insure-scope api"
echo "  验证配置:  uv run insure-scope validate"
