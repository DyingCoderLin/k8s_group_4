#!/bin/bash

# MiniK8s 持久化存储测试启动脚本

echo "============== MiniK8s 持久化存储测试 =============="
echo 

# 创建日志目录
mkdir -p logs

# 启动API服务器
echo "启动API服务器..."
python3 ./pkg/apiServer/apiServer.py > ./logs/apiserver.log 2>&1 &
API_SERVER_PID=$!
echo $API_SERVER_PID > ./apiserver.pid
echo "API服务器已启动，PID: $API_SERVER_PID"

# 等待API服务器启动
echo "等待API服务器就绪..."
sleep 5

# 启动调度器
echo "启动调度器..."
python3 ./pkg/controller/scheduler.py > ./logs/scheduler.log 2>&1 &
SCHEDULER_PID=$!
echo $SCHEDULER_PID > ./scheduler.pid
echo "调度器已启动，PID: $SCHEDULER_PID"

# 启动PV控制器
echo "启动PV控制器..."
chmod +x ./pkg/controller/pvStarter.py
./pkg/controller/pvStarter.py > ./logs/pv_controller.log 2>&1 &
PV_CONTROLLER_PID=$!
echo $PV_CONTROLLER_PID > ./pv_controller.pid
echo "PV控制器已启动，PID: $PV_CONTROLLER_PID"

echo
echo "所有服务已启动，日志文件在 logs/ 目录"
echo 
echo "可以使用以下命令测试PV/PVC功能:"
echo "  ./test_pv_pvc.sh"
echo
echo "使用以下命令停止所有服务:"
echo "  kill \$(cat ./apiserver.pid ./scheduler.pid ./pv_controller.pid)"
echo 
