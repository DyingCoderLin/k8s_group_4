#!/bin/bash

# 停止node进程的脚本

echo "=== 停止Kubernetes Node进程 ==="

# 查找并停止node进程
NODE_PIDS=$(pgrep -f "pkg.apiObject.node")

if [ -z "$NODE_PIDS" ]; then
    echo "没有找到运行中的node进程"
    exit 0
fi

echo "找到以下node进程:"
for pid in $NODE_PIDS; do
    echo "  PID: $pid - $(ps -p $pid -o command= 2>/dev/null || echo 'process not found')"
done

echo
read -p "是否要停止这些进程? (y/N): " confirm

if [[ $confirm =~ ^[Yy]$ ]]; then
    echo "正在停止node进程..."
    for pid in $NODE_PIDS; do
        echo "  停止PID: $pid"
        kill -TERM $pid
    done
    
    # 等待进程优雅退出
    sleep 3
    
    # 检查是否还有进程在运行
    REMAINING_PIDS=$(pgrep -f "pkg.apiObject.node")
    if [ ! -z "$REMAINING_PIDS" ]; then
        echo "一些进程仍在运行，强制终止..."
        for pid in $REMAINING_PIDS; do
            echo "  强制终止PID: $pid"
            kill -KILL $pid
        done
    fi
    
    echo "✅ Node进程已停止"
else
    echo "操作已取消"
fi
