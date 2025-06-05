#!/bin/bash

# Service 负载均衡测试脚本
# 测试 ClusterIP 的负载均衡分发功能

set -e

echo "🚀 开始 Service 负载均衡测试"
echo "================================"

# 配置
KUBECTL_CMD="python3 kubectl.py"
SERVICE_NAME="hello-world-service"
TEST_ITERATIONS=20

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 1. 创建测试 Pods
echo -e "${BLUE}步骤 1: 创建测试 Pods${NC}"
echo "创建 3 个测试服务器 Pods..."

echo "创建 test-server-1..."
$KUBECTL_CMD apply -f testFile/test-pod-server-1.yaml

echo "创建 test-server-2..."
$KUBECTL_CMD apply -f testFile/test-pod-server-2.yaml

echo "创建 test-server-3..."
$KUBECTL_CMD apply -f testFile/test-pod-server-3.yaml

echo "等待 Pods 启动..."
sleep 15

# 2. 检查 Pods 状态
echo -e "${BLUE}步骤 2: 检查 Pods 状态${NC}"
$KUBECTL_CMD get pods

# 3. 创建 Service
echo -e "${BLUE}步骤 3: 创建 Service${NC}"
$KUBECTL_CMD apply -f testFile/test-service-clusterip.yaml

echo "等待 Service 创建..."
sleep 10

# 4. 查看 Service 信息
echo -e "${BLUE}步骤 4: 查看 Service 信息${NC}"
$KUBECTL_CMD get service

# 5. 获取 ClusterIP
echo -e "${BLUE}步骤 5: 获取 ClusterIP${NC}"
CLUSTER_IP=$(iptables-save | grep "KUBE-SERVICES.*${SERVICE_NAME}" | grep -o "10\.[0-9]\+\.[0-9]\+\.[0-9]\+" | head -1)

if [ -z "$CLUSTER_IP" ]; then
    echo -e "${RED}❌ 无法获取 ClusterIP，请检查 Service 是否创建成功${NC}"
    exit 1
fi

echo -e "${GREEN}✅ 发现 ClusterIP: $CLUSTER_IP${NC}"

# 6. 查看 iptables 规则
echo -e "${BLUE}步骤 6: 查看 iptables 负载均衡规则${NC}"
echo "当前 iptables 规则:"
iptables-save | grep -E "(KUBE-SERVICES|KUBE-SVC|hello-world)" | head -10

# 7. 测试负载均衡
echo -e "${BLUE}步骤 7: 测试负载均衡分发${NC}"
echo "向 ClusterIP $CLUSTER_IP:80 发送 $TEST_ITERATIONS 个请求..."

# 创建结果统计
declare -A response_count
total_requests=0
successful_requests=0

for i in $(seq 1 $TEST_ITERATIONS); do
    echo -n "发送请求 $i/$TEST_ITERATIONS... "
    
    # 使用 curl 发送请求，超时 5 秒
    response=$(timeout 5 curl -s "http://$CLUSTER_IP" 2>/dev/null || echo "TIMEOUT")
    
    if [[ "$response" == *"SERVER-"* ]]; then
        # 提取服务器标识
        server_id=$(echo "$response" | grep -o "SERVER-[0-9]")
        response_count[$server_id]=$((${response_count[$server_id]} + 1))
        successful_requests=$((successful_requests + 1))
        echo -e "${GREEN}✅ $server_id${NC}"
    else
        echo -e "${RED}❌ 请求失败: $response${NC}"
    fi
    
    total_requests=$((total_requests + 1))
    sleep 0.5
done

# 8. 显示测试结果
echo -e "${BLUE}步骤 8: 测试结果统计${NC}"
echo "================================"
echo "总请求数: $total_requests"
echo "成功请求数: $successful_requests"
echo "成功率: $(( successful_requests * 100 / total_requests ))%"
echo ""
echo "负载均衡分发统计:"

for server in "${!response_count[@]}"; do
    count=${response_count[$server]}
    percentage=$(( count * 100 / successful_requests ))
    echo -e "${GREEN}$server: $count 次 ($percentage%)${NC}"
done

# 9. 验证负载均衡效果
echo -e "${BLUE}步骤 9: 验证负载均衡效果${NC}"
unique_servers=${#response_count[@]}

if [ $unique_servers -ge 2 ]; then
    echo -e "${GREEN}✅ 负载均衡工作正常！请求分发到了 $unique_servers 个不同的服务器${NC}"
else
    echo -e "${YELLOW}⚠️  负载均衡可能有问题，只有 $unique_servers 个服务器响应${NC}"
fi

# 10. 清理资源 (可选)
echo -e "${BLUE}步骤 10: 清理测试资源${NC}"
read -p "是否清理测试资源? (y/N): " cleanup

if [[ $cleanup =~ ^[Yy]$ ]]; then
    echo "清理测试 Pods..."
    $KUBECTL_CMD delete pod test-server-1 --ignore-not-found=true
    $KUBECTL_CMD delete pod test-server-2 --ignore-not-found=true  
    $KUBECTL_CMD delete pod test-server-3 --ignore-not-found=true
    
    echo "清理 Service..."
    $KUBECTL_CMD delete service $SERVICE_NAME --ignore-not-found=true
    
    echo -e "${GREEN}✅ 清理完成${NC}"
else
    echo "保留测试资源，你可以手动清理："
    echo "  $KUBECTL_CMD delete pod test-server-1 test-server-2 test-server-3"
    echo "  $KUBECTL_CMD delete service $SERVICE_NAME"
fi

echo -e "${GREEN}🎉 Service 负载均衡测试完成！${NC}"
