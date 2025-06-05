#!/bin/bash

# 简单的节点启动脚本 - 使用默认配置启动带ServiceProxy的节点

echo "=== 启动minik8s节点（带ServiceProxy） ==="
echo

# 设置日志目录
LOG_DIR="logs"
mkdir -p "$LOG_DIR"

# 从node-1.yaml配置文件中获取节点名称
NODE_NAME=$(python3 -c "import yaml; data=yaml.safe_load(open('testFile/node-1.yaml')); print(data['metadata']['name'])" 2>/dev/null || echo "node-01")
LOG_FILE="$LOG_DIR/node_${NODE_NAME}.log"
export NODE_LOG_FILE="$LOG_FILE"

echo "节点名称: $NODE_NAME (来自 testFile/node-1.yaml)"
echo "日志文件: $LOG_FILE"
echo
echo "注意事项："
echo "1. 确保API Server正在运行 (localhost:8090)"
echo "2. 确保Kafka正在运行 (10.119.15.182:9092)"
echo "3. ServiceProxy将自动随节点启动"
echo "4. 按 Ctrl+C 优雅停止节点"
echo
echo "--- 启动节点 ---"

# 启动节点
python3 -m pkg.apiObject.node 2>&1 | tee "$LOG_FILE"
