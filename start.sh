#!/bin/bash
# filepath: /Users/liang/code/cloud_OS/k8s/k8s_group_4/start.sh

# 设置颜色输出
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 获取当前脚本所在目录作为项目根目录
PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PID_FILE="${PROJECT_ROOT}/.k8s_pids"

# 停止函数 - 用于停止所有运行中的组件
stop_all() {
    echo "${YELLOW}正在停止所有 K8S 组件...${NC}"
    
    # if [ -f "$PID_FILE" ]; then
    #     while read pid name; do
    #         if ps -p $pid > /dev/null 2>&1; then
    #             echo "${GREEN}停止 $name (PID: $pid)${NC}"
    #             kill -15 $pid 2>/dev/null || kill -9 $pid 2>/dev/null
    #         else
    #             echo "${BLUE}$name (PID: $pid) 已经不在运行${NC}"
    #         fi
    #     done < "$PID_FILE"
        
    #     # 删除PID文件
    #     rm -f "$PID_FILE"
    #     echo "${GREEN}所有组件已停止${NC}"
    # else
    #     echo "${RED}找不到PID文件，无法停止组件${NC}"
    #     echo "${YELLOW}尝试查找并停止相关进程...${NC}"
        
        # 尝试通过进程名停止
        pkill -f "python3 -m pkg.apiServer.apiServer" || true
        pkill -f "python3 -m pkg.apiObject.node" || true
        pkill -f "python3 -m pkg.controller.rsStarter" || true
        pkill -f "python3 -m pkg.controller.hpaStarter" || true
        pkill -f "python3 -m pkg.controller.serviceStarter" || true
        pkill -f "python3 -m pkg.controller.scheduler" || true
        pkill -f "python3 -m pkg.controller.pvStarter" || true

        if [ -f "$PID_FILE" ]; then
            rm -f "$PID_FILE"
        
        echo "${GREEN}进程已停止${NC}"
    fi
    
    exit 0
}

# 检查是否传递了--stop参数
if [ "$1" == "--stop" ]; then
    stop_all
fi

echo "${BLUE}项目根目录: ${PROJECT_ROOT}${NC}"
echo "${BLUE}PID 文件: ${PID_FILE}${NC}"

# 设置 PYTHONPATH 环境变量
export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH}"
echo "${BLUE}已设置 PYTHONPATH: ${PYTHONPATH}${NC}"

# 创建日志目录
mkdir -p "${PROJECT_ROOT}/logs"

# 检查依赖程序是否存在
command -v python3 >/dev/null 2>&1 || { echo "${RED}需要安装 python3 但未找到，请先安装 python3${NC}" >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "${RED}需要安装 docker 但未找到，请先安装 docker${NC}" >&2; exit 1; }

# 启动函数，参数: 描述 命令 日志文件
start_component() {
    local description=$1
    local command=$2
    local log_file=$3

    echo "${GREEN}启动 $description...${NC}"
    $command > "${log_file}" 2>&1 &
    local pid=$!
    echo "${GREEN}$description 已启动，进程ID: $pid${NC}"
    echo "${BLUE}日志文件: $log_file${NC}"

    echo "$pid $description" >> "$PID_FILE"
}

# 确保退出时关闭所有进程
trap stop_all SIGINT SIGTERM
# trap 'echo "${YELLOW}正在关闭所有组件...${NC}"; kill ${pids[@]} 2>/dev/null; exit' SIGINT SIGTERM

echo "${YELLOW}===== 开始启动 K8S 组件 =====${NC}"

# 1. 启动 ApiServer
api_server_pid=$(start_component "ApiServer" "python3 -m pkg.apiServer.apiServer" "${PROJECT_ROOT}/logs/apiserver.log")
pids+=($api_server_pid)

# 等待 ApiServer 完全启动
echo "${BLUE}等待 ApiServer 启动 (5秒)...${NC}"
sleep 5

# 2. 启动 Scheduler
scheduler_pid=$(start_component "Scheduler" "python3 -m pkg.controller.scheduler" "${PROJECT_ROOT}/logs/scheduler.log")
pids+=(scheduler_pid)

# 等待 Scheduler 完全启动
echo "${BLUE}等待 Sheduler 启动 (5秒)...${NC}"
sleep 5

# 3. 启动 Node（会自动启动 Kubelet）
node_pid=$(start_component "Node" "python3 -m pkg.apiObject.node" "${PROJECT_ROOT}/logs/node.log")
pids+=($node_pid)

# 等待 Node 和 Kubelet 完全启动
echo "${BLUE}等待 Node 和 Kubelet 启动 (3秒)...${NC}"
sleep 3

# 4. 启动 ReplicaSetController
rs_controller_pid=$(start_component "ReplicaSetController" "python3 -m pkg.controller.rsStarter" "${PROJECT_ROOT}/logs/replicaset_controller.log")
pids+=($rs_controller_pid)

# 5. 启动 HPAController
hpa_controller_pid=$(start_component "HPAController" "python3 -m pkg.controller.hpaStarter" "${PROJECT_ROOT}/logs/hpa_controller.log")
pids+=($hpa_controller_pid)

# # 6. 启动 ServiceController
service_controller_pid=$(start_component "ServiceController" "python3 -m pkg.controller.serviceStarter" "${PROJECT_ROOT}/logs/service_controller.log")
pids+=($service_controller_pid)

# 7. 启动 PV 控制器
# pv_controller_pid=$(start_component "PVController" "python3 -m pkg.controller.pvStarter" "${PROJECT_ROOT}/logs/pv_controller.log")
# pids+=($pv_controller_pid)

echo "${YELLOW}===== 所有 K8S 组件已启动 =====${NC}"
echo "${GREEN}ApiServer PID: $api_server_pid${NC}"
echo "${GREEN}Node/Kubelet PID: $node_pid${NC}"
echo "${GREEN}ReplicaSetController PID: $rs_controller_pid${NC}"
echo "${GREEN}HPAController PID: $hpa_controller_pid${NC}"
echo "${GREEN}ServiceController PID: $service_controller_pid${NC}"
# echo "${GREEN}PVController PID: $pv_controller_pid${NC}"
echo "${GREEN}Scheduler PID: $scheduler_pid${NC}"
echo "${YELLOW}===== 组件日志已保存到 ${PROJECT_ROOT}/logs/ =====${NC}"
echo "${BLUE}查看组件日志: tail -f ${PROJECT_ROOT}/logs/*.log${NC}"
echo "${YELLOW}运行 '$0 --stop' 停止所有组件${NC}"

# 保持脚本运行，直到用户按下 Ctrl+C
wait

exit 0