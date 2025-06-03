#!/bin/bash

# Minik8s PV/PVC测试脚本
echo "==================== Minik8s PV/PVC 功能测试 ===================="

API_SERVER="http://localhost:5050"

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 测试函数
test_api() {
    local method=$1
    local url=$2
    local data_file=$3
    local expected_status=$4
    local description=$5
    
    echo -e "${YELLOW}测试: $description${NC}"
    
    if [ -n "$data_file" ] && [ -f "$data_file" ]; then
        response=$(curl -s -w "\n%{http_code}" -X $method -H "Content-Type: application/json" -d @"$data_file" "$API_SERVER$url")
    else
        response=$(curl -s -w "\n%{http_code}" -X $method "$API_SERVER$url")
    fi
    
    # 分离响应体和状态码
    body=$(echo "$response" | head -n -1)
    status=$(echo "$response" | tail -n 1)
    
    if [ "$status" = "$expected_status" ]; then
        echo -e "${GREEN}✓ 成功 (状态码: $status)${NC}"
        echo "响应: $body"
    else
        echo -e "${RED}✗ 失败 (期望: $expected_status, 实际: $status)${NC}"
        echo "响应: $body"
    fi
    echo ""
}

# 等待API服务器启动
echo "等待API服务器启动..."
for i in {1..30}; do
    if curl -s "$API_SERVER/api/v1/nodes" > /dev/null 2>&1; then
        echo -e "${GREEN}API服务器已就绪${NC}"
        break
    fi
    sleep 1
done

echo ""
echo "==================== 1. 环境准备 ===================="

# 创建测试目录
mkdir -p /tmp/minik8s-test/static-pv
echo "This is a test file for static PV" > /tmp/minik8s-test/static-pv/test.txt
echo -e "${GREEN}✓ 创建了测试目录: /tmp/minik8s-test/static-pv${NC}"

echo ""
echo "==================== 2. 静态 PV 测试 ===================="

# 创建静态 PV
test_api "POST" "/api/v1/persistentvolumes/pv-hostpath-static" "testFile/pv-hostpath-static.yaml" "201" "创建 hostPath 静态 PV"
test_api "POST" "/api/v1/persistentvolumes/pv-nfs-static" "testFile/pv-nfs-static.yaml" "201" "创建 NFS 静态 PV"

# 获取 PV
test_api "GET" "/api/v1/persistentvolumes" "" "200" "获取所有 PV"
test_api "GET" "/api/v1/persistentvolumes/pv-hostpath-static" "" "200" "获取 hostPath 静态 PV"
test_api "GET" "/api/v1/persistentvolumes/pv-nfs-static" "" "200" "获取 NFS 静态 PV"

echo ""
echo "==================== 3. PVC 测试 ===================="

# 创建 PVC
test_api "POST" "/api/v1/namespaces/default/persistentvolumeclaims/pvc-hostpath-static" "testFile/pvc-hostpath-static.yaml" "201" "创建静态绑定 PVC"
test_api "POST" "/api/v1/namespaces/default/persistentvolumeclaims/pvc-hostpath-dynamic" "testFile/pvc-hostpath-dynamic.yaml" "201" "创建动态供应 PVC"
test_api "POST" "/api/v1/namespaces/default/persistentvolumeclaims/pvc-nfs-dynamic" "testFile/pvc-nfs-dynamic.yaml" "201" "创建 NFS 动态供应 PVC"

# 获取 PVC
test_api "GET" "/api/v1/persistentvolumeclaims" "" "200" "获取所有 PVC"
test_api "GET" "/api/v1/namespaces/default/persistentvolumeclaims" "" "200" "获取 default 命名空间的 PVC"
test_api "GET" "/api/v1/namespaces/default/persistentvolumeclaims/pvc-hostpath-static" "" "200" "获取静态 PVC"

echo ""
echo "==================== 4. 简化版动态供应测试 ===================="

# 创建简化版动态供应 PVC
test_api "POST" "/api/v1/namespaces/default/persistentvolumeclaims/pvc-dynamic-test" "testFile/pvc-dynamic-test.yaml" "201" "创建简化版动态供应 PVC (hostPath)"
test_api "POST" "/api/v1/namespaces/default/persistentvolumeclaims/pvc-nfs-dynamic-test" "testFile/pvc-nfs-dynamic-test.yaml" "201" "创建简化版动态供应 PVC (NFS)"

# 等待动态供应完成
echo "等待动态供应完成..."
sleep 5

# 检查是否创建了动态 PV
test_api "GET" "/api/v1/persistentvolumes" "" "200" "检查动态创建的 PV"
test_api "GET" "/api/v1/namespaces/default/persistentvolumeclaims/pvc-dynamic-test" "" "200" "检查动态 PVC 绑定状态"

echo ""
echo "==================== 5. Pod 挂载 PVC 测试 ===================="

# 创建使用 PVC 的 Pod
test_api "POST" "/api/v1/namespaces/default/pods/pod-with-hostpath-pvc" "testFile/pod-with-hostpath-pvc.yaml" "201" "创建使用 hostPath PVC 的 Pod"
test_api "POST" "/api/v1/namespaces/default/pods/pod-with-nfs-pvc" "testFile/pod-with-nfs-pvc.yaml" "201" "创建使用 NFS PVC 的 Pod"
test_api "POST" "/api/v1/namespaces/default/pods/pod-mixed-volumes" "testFile/pod-mixed-volumes.yaml" "201" "创建使用混合卷类型的 Pod"
test_api "POST" "/api/v1/namespaces/default/pods/data-pod" "testFile/pod-with-dynamic-pvc.yaml" "201" "创建使用动态 PVC 的 Pod"

# 等待一段时间让 Pod 启动
echo "等待 Pod 启动..."
sleep 10

# 检查 Pod 状态
test_api "GET" "/api/v1/namespaces/default/pods/pod-with-hostpath-pvc" "" "200" "检查 hostPath PVC Pod 状态"
test_api "GET" "/api/v1/namespaces/default/pods/pod-with-nfs-pvc" "" "200" "检查 NFS PVC Pod 状态"

echo ""
echo "==================== 5. 清理测试 ===================="

# 删除 Pod
test_api "DELETE" "/api/v1/namespaces/default/pods/pod-with-hostpath-pvc" "" "200" "删除 hostPath PVC Pod"
test_api "DELETE" "/api/v1/namespaces/default/pods/pod-with-nfs-pvc" "" "200" "删除 NFS PVC Pod"
test_api "DELETE" "/api/v1/namespaces/default/pods/pod-mixed-volumes" "" "200" "删除混合卷 Pod"

# 删除 PVC
test_api "DELETE" "/api/v1/namespaces/default/persistentvolumeclaims/pvc-hostpath-static" "" "200" "删除静态 PVC"
test_api "DELETE" "/api/v1/namespaces/default/persistentvolumeclaims/pvc-hostpath-dynamic" "" "200" "删除动态 PVC"
test_api "DELETE" "/api/v1/namespaces/default/persistentvolumeclaims/pvc-nfs-dynamic" "" "200" "删除 NFS PVC"

# 删除 PV
test_api "DELETE" "/api/v1/persistentvolumes/pv-hostpath-static" "" "200" "删除 hostPath 静态 PV"
test_api "DELETE" "/api/v1/persistentvolumes/pv-nfs-static" "" "200" "删除 NFS 静态 PV"

# 清理测试目录
rm -rf /tmp/minik8s-test/static-pv
echo -e "${GREEN}✓ 清理了测试目录${NC}"

echo ""
echo -e "${GREEN}==================== 测试完成 ====================${NC}"
echo "请检查上述输出以验证 PV/PVC 功能是否正常工作"
