#!/bin/bash

# 启动多个minik8s节点的脚本
# 这个脚本展示了如何同时启动多个带有ServiceProxy的节点

echo "=== minik8s多节点启动脚本 ==="
echo "此脚本将启动多个带有ServiceProxy的Kubernetes节点"
echo

# 节点配置
NODES=(
    "worker-01:node-1.yaml"
    "worker-02:node-1.yaml"
    "worker-03:node-1.yaml"
)

# 检查参数
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    echo "用法: $0 [选项]"
    echo "选项:"
    echo "  --help, -h     显示此帮助信息"
    echo "  --stop         停止所有节点进程"
    echo
    echo "默认启动的节点:"
    for node_config in "${NODES[@]}"; do
        node_name=$(echo "$node_config" | cut -d: -f1)
        config_file=$(echo "$node_config" | cut -d: -f2)
        echo "  - $node_name (配置: $config_file)"
    done
    echo
    exit 0
fi

# 停止所有节点
if [ "$1" = "--stop" ]; then
    echo "正在停止所有节点进程..."
    pkill -f "pkg.apiObject.node"
    echo "✅ 已发送停止信号给所有节点进程"
    exit 0
fi

# 创建日志目录
LOG_DIR="logs"
mkdir -p "$LOG_DIR"

echo "准备启动 ${#NODES[@]} 个节点..."
echo

# 启动每个节点
PIDS=()
for node_config in "${NODES[@]}"; do
    node_name=$(echo "$node_config" | cut -d: -f1)
    config_file=$(echo "$node_config" | cut -d: -f2)
    log_file="$LOG_DIR/node_${node_name}.log"
    
    echo "启动节点: $node_name (配置: $config_file)"
    
    # 在后台启动节点
    (
        export NODE_LOG_FILE="$log_file"
        python3 -m pkg.apiObject.node \
            --node-config "$config_file" \
            --node-name "$node_name" \
            > "$log_file" 2>&1
    ) &
    
    pid=$!
    PIDS+=($pid)
    echo "  PID: $pid, 日志: $log_file"
    
    # 等待一秒，避免同时启动时的资源竞争
    sleep 1
done

echo
echo "✅ 所有节点已启动"
echo "节点进程PID: ${PIDS[*]}"
echo
echo "监控命令:"
echo "  查看所有节点日志: tail -f $LOG_DIR/node_*.log"
echo "  停止所有节点: $0 --stop"
echo "  或者: kill ${PIDS[*]}"
echo

# 设置信号处理器
cleanup() {
    echo
    echo "收到中断信号，正在停止所有节点..."
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            echo "停止进程 $pid"
            kill "$pid"
        fi
    done
    
    # 等待进程退出
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            wait "$pid" 2>/dev/null
        fi
    done
    
    echo "✅ 所有节点已停止"
    exit 0
}

trap cleanup SIGINT SIGTERM

# 等待所有后台进程
echo "按 Ctrl+C 停止所有节点..."
wait
