#!/bin/bash

# 启动minik8s节点（集成ServiceProxy）的脚本
# 这个脚本展示了如何启动带有ServiceProxy的Node，使用YAML配置文件

echo "=== minik8s节点启动脚本 ==="
echo "此脚本将启动带有ServiceProxy的Kubernetes节点"
echo

# 检查参数
if [ $# -eq 0 ]; then
    echo "用法: $0 <配置文件> [节点名称环境变量]"
    echo "示例:"
    echo "  $0 node-1.yaml                    # 使用node-1.yaml配置启动节点"
    echo "  $0 node-2.yaml                    # 使用node-2.yaml配置启动节点"
    echo "  NODE_NAME=worker-01 $0 node-1.yaml # 通过环境变量设置节点名称（如果需要覆盖配置文件）"
    echo
    exit 1
fi

CONFIG_FILE=$1

echo "配置文件: $CONFIG_FILE"
if [ ! -z "$NODE_NAME" ]; then
    echo "环境变量节点名称: $NODE_NAME"
fi
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

# 从配置文件中提取节点名称（如果没有设置环境变量）
if [ -z "$NODE_NAME" ]; then
    if [ -f "testFile/$CONFIG_FILE" ]; then
        NODE_NAME=$(python3 -c "import yaml; data=yaml.safe_load(open('testFile/$CONFIG_FILE')); print(data['metadata']['name'])" 2>/dev/null || echo "unknown")
    else
        NODE_NAME=$(python3 -c "import yaml; data=yaml.safe_load(open('$CONFIG_FILE')); print(data['metadata']['name'])" 2>/dev/null || echo "unknown")
    fi
fi

LOG_FILE="$LOG_DIR/node_${NODE_NAME}.log"
export NODE_LOG_FILE="$LOG_FILE"

echo "节点名称: $NODE_NAME"
echo "日志文件: $LOG_FILE"
echo

# 启动节点
echo "正在启动节点 $NODE_NAME ..."
echo "注意："
echo "1. 确保API Server正在运行 (通常在 localhost:8090)"
echo "2. 确保Kafka正在运行 (通常在 10.119.15.182:9092)"
echo "3. 按 Ctrl+C 可以优雅地停止节点"
echo "4. ServiceProxy将自动随节点启动"
echo
echo "--- 节点日志开始 ---"

# 启动节点，同时输出到控制台和日志文件
# 确保使用正确的配置文件路径
if [ -f "testFile/$CONFIG_FILE" ]; then
    # 修改配置文件名称以使用正确的配置
    cd testFile && ln -sf "$CONFIG_FILE" node-1.yaml && cd .. || true
fi

python3 -m pkg.apiObject.node 2>&1 | tee "$LOG_FILE"

echo
echo "--- 节点已停止 ---"
echo "日志已保存到: $LOG_FILE"
