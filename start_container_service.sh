#!/bin/bash

# 在容器内启动 HTTP 服务的脚本
echo "🚀 在容器内启动 HTTP 服务"
echo "========================"

echo "当前容器网络信息:"
ip addr show eth0

echo ""
echo "方法1: 使用 nc (netcat) 启动简单的 HTTP 服务"
echo "在容器内运行以下命令:"
echo ""
echo "while true; do"
echo "  echo -e 'HTTP/1.1 200 OK\\r\\nContent-Type: text/plain\\r\\nContent-Length: 25\\r\\n\\r\\nHello from Container!' | nc -l -p 8080"
echo "done &"

echo ""
echo "方法2: 使用 Python 启动 HTTP 服务 (如果容器内有 Python)"
echo "在容器内运行:"
echo "python3 -m http.server 8080 &"

echo ""
echo "方法3: 使用 busybox httpd"
echo "在容器内运行:"
echo "echo 'Hello from Container Server!' > /tmp/index.html"
echo "busybox httpd -f -p 8080 -h /tmp &"

echo ""
echo "启动服务后，你可以在宿主机测试:"
echo "curl http://10.5.53.5:8080"
echo ""
echo "或者测试 Service 负载均衡:"
CLUSTER_IP=$(iptables-save | grep "KUBE-SERVICES.*hello-world" | grep -o "10\.[0-9]\+\.[0-9]\+\.[0-9]\+" | head -1)
if [ ! -z "$CLUSTER_IP" ]; then
    echo "curl http://$CLUSTER_IP"
fi
