#!/bin/bash

# Minik8s PV/PVC 新功能测试脚本
echo "==================== Minik8s PV/PVC 新功能测试 ===================="

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
echo "==================== 1. 清理环境 ===================="

# 清理可能存在的资源
curl -s -X DELETE "$API_SERVER/api/v1/namespaces/default/pods/pod-pvc-only-test" > /dev/null
curl -s -X DELETE "$API_SERVER/api/v1/namespaces/default/persistentvolumeclaims/pvc-dynamic-test" > /dev/null
curl -s -X DELETE "$API_SERVER/api/v1/namespaces/default/persistentvolumeclaims/pvc-specific-pv-test" > /dev/null
curl -s -X DELETE "$API_SERVER/api/v1/namespaces/default/persistentvolumeclaims/pvc-specific-nfs-pv-test" > /dev/null
curl -s -X DELETE "$API_SERVER/api/v1/persistentvolumes/my-specific-pv" > /dev/null
curl -s -X DELETE "$API_SERVER/api/v1/persistentvolumes/my-nfs-pv" > /dev/null

sleep 2
echo -e "${GREEN}✓ 环境清理完成${NC}"

echo ""
echo "==================== 2. 测试动态PVC（storageClassName）===================="

# 创建动态PVC（使用storageClassName）
test_api "POST" "/api/v1/namespaces/default/persistentvolumeclaims/pvc-dynamic-test" "testFile/pvc-dynamic-test.yaml" "201" "创建动态 hostPath PVC"
test_api "POST" "/api/v1/namespaces/default/persistentvolumeclaims/pvc-nfs-dynamic-test" "testFile/pvc-nfs-dynamic-test.yaml" "201" "创建动态 NFS PVC"

# 等待动态供应完成
echo "等待PV控制器处理PVC..."
sleep 8

# 检查动态创建的PV
test_api "GET" "/api/v1/persistentvolumes" "" "200" "检查动态创建的PV"
test_api "GET" "/api/v1/namespaces/default/persistentvolumeclaims/pvc-dynamic-test" "" "200" "检查动态PVC绑定状态"

echo ""
echo "==================== 3. 测试指定PV名称的PVC（volumeName）===================="

# 创建指定PV名称的PVC
test_api "POST" "/api/v1/namespaces/default/persistentvolumeclaims/pvc-specific-pv-test" "testFile/pvc-specific-pv-test.yaml" "201" "创建指定PV名称的PVC (hostPath)"
test_api "POST" "/api/v1/namespaces/default/persistentvolumeclaims/pvc-specific-nfs-pv-test" "testFile/pvc-specific-nfs-pv-test.yaml" "201" "创建指定PV名称的PVC (NFS)"

# 等待PV创建和绑定
echo "等待指定PV创建和绑定..."
sleep 8

# 检查指定的PV是否创建
test_api "GET" "/api/v1/persistentvolumes/my-specific-pv" "" "200" "检查指定的hostPath PV"
test_api "GET" "/api/v1/persistentvolumes/my-nfs-pv" "" "200" "检查指定的NFS PV"
test_api "GET" "/api/v1/namespaces/default/persistentvolumeclaims/pvc-specific-pv-test" "" "200" "检查指定PV的PVC绑定状态"

echo ""
echo "==================== 4. 测试Pod只使用PVC绑定 ===================="

# 创建只使用PVC的Pod
test_api "POST" "/api/v1/namespaces/default/pods/pod-pvc-only-test" "testFile/pod-pvc-only-test.yaml" "201" "创建只使用PVC的Pod"

# 等待Pod启动
echo "等待Pod启动..."
sleep 10

# 检查Pod状态
test_api "GET" "/api/v1/namespaces/default/pods/pod-pvc-only-test" "" "200" "检查Pod状态"

echo ""
echo "==================== 5. 测试存储类型匹配错误 ===================="

# 创建一个hostPath PV
echo '{
  "apiVersion": "v1",
  "kind": "PersistentVolume",
  "metadata": {
    "name": "hostpath-pv-for-test"
  },
  "spec": {
    "capacity": {
      "storage": "1Gi"
    },
    "hostPath": {
      "path": "/tmp/test-hostpath"
    }
  }
}' > /tmp/hostpath-pv-test.json

test_api "POST" "/api/v1/persistentvolumes/hostpath-pv-for-test" "/tmp/hostpath-pv-test.json" "201" "创建hostPath测试PV"

# 创建一个尝试绑定到hostPath PV但使用nfs storageClassName的PVC
echo '{
  "apiVersion": "v1",
  "kind": "PersistentVolumeClaim",
  "metadata": {
    "name": "pvc-type-mismatch-test",
    "namespace": "default"
  },
  "spec": {
    "storageClassName": "nfs",
    "volumeName": "hostpath-pv-for-test",
    "resources": {
      "requests": {
        "storage": "1Gi"
      }
    }
  }
}' > /tmp/pvc-type-mismatch.json

test_api "POST" "/api/v1/namespaces/default/persistentvolumeclaims/pvc-type-mismatch-test" "/tmp/pvc-type-mismatch.json" "201" "创建类型不匹配的PVC"

# 等待处理
sleep 5

# 检查PVC状态（应该失败）
test_api "GET" "/api/v1/namespaces/default/persistentvolumeclaims/pvc-type-mismatch-test" "" "200" "检查类型不匹配PVC状态"

echo ""
echo "==================== 6. 清理测试 ===================="

# 删除Pod
test_api "DELETE" "/api/v1/namespaces/default/pods/pod-pvc-only-test" "" "200" "删除测试Pod"

# 删除PVC
test_api "DELETE" "/api/v1/namespaces/default/persistentvolumeclaims/pvc-dynamic-test" "" "200" "删除动态PVC"
test_api "DELETE" "/api/v1/namespaces/default/persistentvolumeclaims/pvc-nfs-dynamic-test" "" "200" "删除NFS动态PVC"
test_api "DELETE" "/api/v1/namespaces/default/persistentvolumeclaims/pvc-specific-pv-test" "" "200" "删除指定PV的PVC"
test_api "DELETE" "/api/v1/namespaces/default/persistentvolumeclaims/pvc-specific-nfs-pv-test" "" "200" "删除指定NFS PV的PVC"
test_api "DELETE" "/api/v1/namespaces/default/persistentvolumeclaims/pvc-type-mismatch-test" "" "200" "删除类型不匹配的PVC"

# 删除PV
test_api "DELETE" "/api/v1/persistentvolumes/my-specific-pv" "" "200" "删除指定的PV"
test_api "DELETE" "/api/v1/persistentvolumes/my-nfs-pv" "" "200" "删除指定的NFS PV"
test_api "DELETE" "/api/v1/persistentvolumes/hostpath-pv-for-test" "" "200" "删除测试用hostPath PV"

# 获取所有剩余的PV（应该包含动态创建的PV）
test_api "GET" "/api/v1/persistentvolumes" "" "200" "获取所有剩余的PV"

# 清理临时文件
rm -f /tmp/hostpath-pv-test.json /tmp/pvc-type-mismatch.json

echo ""
echo -e "${GREEN}==================== 测试完成 ====================${NC}"
echo ""
echo "测试总结："
echo "1. ✓ 测试了基于storageClassName的动态PVC"
echo "2. ✓ 测试了基于volumeName的特定PV绑定"
echo "3. ✓ 测试了Pod只使用PVC卷绑定"
echo "4. ✓ 测试了存储类型不匹配的错误处理"
echo ""
echo "请检查上述输出以验证新的PV/PVC功能是否正常工作"
