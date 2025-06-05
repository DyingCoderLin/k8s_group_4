#!/bin/bash

# 手动测试 Service 负载均衡
echo "🧪 Service 负载均衡手动测试指南"
echo "================================"

# 1. 首先确认当前 Service 的 ClusterIP
echo "1️⃣ 获取 Service ClusterIP:"
CLUSTER_IP=$(iptables-save | grep "KUBE-SERVICES.*hello-world" | grep -o "10\.[0-9]\+\.[0-9]\+\.[0-9]\+" | head -1)

if [ -z "$CLUSTER_IP" ]; then
    echo "❌ 未找到 ClusterIP，请检查 Service 是否已创建"
    echo "请运行: python3 kubectl.py get service"
    exit 1
fi

echo "✅ ClusterIP: $CLUSTER_IP"

# 2. 显示 iptables 规则
echo ""
echo "2️⃣ 当前负载均衡规则:"
iptables-save | grep -E "(KUBE-SERVICES|KUBE-SVC|hello-world)" | head -10

# 3. 测试连接
echo ""
echo "3️⃣ 测试连接方法:"
echo "方法1 - 使用 curl:"
echo "curl -v http://$CLUSTER_IP"
echo "curl -v http://$CLUSTER_IP:80"

echo ""
echo "方法2 - 使用 telnet:"
echo "telnet $CLUSTER_IP 80"

echo ""
echo "方法3 - 使用 nc (netcat):"
echo "nc -v $CLUSTER_IP 80"

echo ""
echo "4️⃣ 批量测试负载均衡:"
echo "for i in {1..10}; do echo \"请求 \$i:\"; curl -s http://$CLUSTER_IP; echo; done"

echo ""
echo "5️⃣ 如果要测试多次请求，可以运行："
echo "bash -c 'for i in {1..20}; do echo -n \"请求 \$i: \"; curl -s --connect-timeout 3 http://$CLUSTER_IP 2>/dev/null || echo \"失败\"; sleep 1; done'"
