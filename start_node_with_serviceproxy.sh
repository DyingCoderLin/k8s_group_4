#!/bin/bash

# 启动minik8s节点（集成ServiceProxy）的脚本
# 这个脚本展示了如何在不同的节点上启动带有ServiceProxy的Node

echo "=== minik8s节点启动脚本 ==="
echo "此脚本将启动带有ServiceProxy的Kubernetes节点"
echo

# 检查参数
if [ $# -eq 0 ]; then
    echo "用法: $0 <节点名称> [配置文件]"
    echo "示例:"
    echo "  $0 worker-01                    # 使用默认配置启动worker-01节点"
    echo "  $0 worker-02 node-2.yaml      # 使用指定配置启动worker-02节点"
    echo
    exit 1
fi

NODE_NAME=$1
CONFIG_FILE=${2:-"node-1.yaml"}

echo "节点名称: $NODE_NAME"
echo "配置文件: $CONFIG_FILE"
echo

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到python3命令"
    exit 1
fi

# 检查配置文件是否存在
if [ ! -f "testFile/$CONFIG_FILE" ] && [ ! -f "$CONFIG_FILE" ]; then
    echo "❌ 错误: 配置文件 $CONFIG_FILE 不存在"
    echo "请检查文件路径或创建配置文件"
    exit 1
fi

echo "✅ 环境检查通过"
echo

# 设置日志文件
LOG_DIR="logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/node_${NODE_NAME}.log"
export NODE_LOG_FILE="$LOG_FILE"

echo "日志文件: $LOG_FILE"
echo

# 启动节点
echo "正在启动节点 $NODE_NAME ..."
echo "注意："
echo "1. 确保API Server正在运行 (通常在 localhost:8090)"
echo "2. 确保Kafka正在运行 (通常在 10.119.15.182:9092)"
echo "3. 按 Ctrl+C 可以优雅地停止节点"
echo
echo "--- 节点日志开始 ---"

# 启动节点，同时输出到控制台和日志文件
python3 -m pkg.apiObject.node \
    --node-config "$CONFIG_FILE" \
    --node-name "$NODE_NAME" \
    2>&1 | tee "$LOG_FILE"

echo
echo "--- 节点已停止 ---"
echo "日志已保存到: $LOG_FILE"
