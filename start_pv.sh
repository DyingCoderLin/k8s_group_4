#!/bin/bash

# PV 控制器启动脚本

echo "启动PV控制器..."

# 确保脚本可执行
chmod +x ./pkg/controller/pvStarter.py

# 运行控制器
./pkg/controller/pvStarter.py > ./logs/pv_controller.log 2>&1 &

# 保存PID
PID=$!
echo $PID > ./pv_controller.pid

echo "PV控制器已启动，PID: $PID"
echo "日志文件: ./logs/pv_controller.log"
