# Kubernetes Service 抽象实现指南

## 概述

本项目实现了完整的Kubernetes Service抽象，支持ClusterIP和NodePort两种类型的Service。Service作为Pod的网络代理层，提供统一且稳定的虚拟IP，通过iptables实现负载均衡和流量转发。

## 功能特性

### ✅ 已实现功能
- **ClusterIP Service**: 集群内部访问的虚拟IP服务
- **NodePort Service**: 外部访问的端口映射服务
- **动态Pod发现**: 通过标签选择器自动发现匹配的Pod
- **负载均衡**: 支持随机(Random)和轮询(RoundRobin)策略
- **iptables规则管理**: 自动创建和删除网络转发规则
- **Service生命周期管理**: 创建、更新、删除Service
- **实时监控**: 动态更新Service endpoints

### 🔧 技术架构
```
Client Request
    ↓
Service ClusterIP (虚拟IP)
    ↓
iptables KUBE-SERVICES 链
    ↓
iptables KUBE-SVC-* 链 (负载均衡)
    ↓
iptables KUBE-SEP-* 链 (DNAT转发)
    ↓
Pod Real IP:Port
```

## 快速开始

### 1. 环境准备

确保系统满足以下要求：
```bash
# 必需的依赖
- Python 3.7+
- Docker 20.0+
- iptables (Linux系统)
- etcd 3.5+
- Kafka 2.8+

# 权限要求
sudo权限 (用于iptables操作)
```

### 2. 部署Service组件

使用部署脚本启动所有服务：
```bash
# 一键部署所有组件
./deploy.sh

# 或者手动启动
./start.sh
```

### 3. 验证Service功能

```bash
# 检查Service Controller是否运行
ps aux | grep serviceController

# 查看iptables规则
sudo iptables -t nat -L KUBE-SERVICES -n
```

## Service使用指南

### 1. ClusterIP Service示例

创建一个集群内部访问的Service：

```yaml
# web-service-clusterip.yaml
apiVersion: v1
kind: Service
metadata:
  name: web-service
  namespace: default
  labels:
    app: web
spec:
  type: ClusterIP
  selector:
    app: web-app
    tier: frontend
  ports:
  - name: http
    port: 80
    targetPort: 8080
    protocol: TCP
  clusterIP: 10.96.0.100  # 可选，不指定则自动分配
```

**应用Service：**
```bash
# 通过API创建Service
curl -X POST http://localhost:5050/api/v1/services \
  -H "Content-Type: application/json" \
  -d @web-service-clusterip.yaml

# 或者使用Python API
python3 -c "
from pkg.apiObject.service import Service
from pkg.config.serviceConfig import ServiceConfig
import yaml

with open('web-service-clusterip.yaml') as f:
    config = ServiceConfig(yaml.safe_load(f))
    service = Service(config)
    service.create()
"
```

### 2. NodePort Service示例

创建一个外部可访问的Service：

```yaml
# web-service-nodeport.yaml
apiVersion: v1
kind: Service
metadata:
  name: web-external
  namespace: default
spec:
  type: NodePort
  selector:
    app: web-app
  ports:
  - name: http
    port: 80
    targetPort: 8080
    nodePort: 30080
    protocol: TCP
```

**访问Service：**
```bash
# 集群内访问
curl http://web-service:80
curl http://10.96.0.100:80

# 外部访问 (NodePort)
curl http://节点IP:30080
```

### 3. 查看Service状态

```bash
# 查看所有Service
curl http://localhost:5050/api/v1/services

# 查看特定Service详情
curl http://localhost:5050/api/v1/services/default/web-service

# 查看Service endpoints
curl http://localhost:5050/api/v1/services/default/web-service/endpoints
```

## Service工作原理

### 1. Service发现机制

Service通过标签选择器发现Pod：

```python
# Service Controller定期执行
def discover_pods(service):
    """
    1. 根据service.selector查询所有Pod
    2. 匹配Pod的labels
    3. 筛选Running状态的Pod
    4. 提取Pod IP和端口信息
    """
    matching_pods = []
    for pod in get_all_pods():
        if match_labels(pod.labels, service.selector):
            if pod.status == 'Running' and pod.pod_ip:
                matching_pods.append({
                    'ip': pod.pod_ip,
                    'port': service.target_port,
                    'name': pod.name
                })
    return matching_pods
```

### 2. iptables规则生成

#### ClusterIP规则结构：
```bash
# 主入口规则 (KUBE-SERVICES链)
-A KUBE-SERVICES -d 10.96.0.100/32 -p tcp --dport 80 \
  -j KUBE-SVC-ABCD1234

# 负载均衡规则 (KUBE-SVC-*链)
-A KUBE-SVC-ABCD1234 -m statistic --mode random --probability 0.33 \
  -j KUBE-SEP-POD1
-A KUBE-SVC-ABCD1234 -m statistic --mode random --probability 0.50 \
  -j KUBE-SEP-POD2
-A KUBE-SVC-ABCD1234 -j KUBE-SEP-POD3

# 目标转换规则 (KUBE-SEP-*链)
-A KUBE-SEP-POD1 -j DNAT --to-destination 192.168.1.10:8080
-A KUBE-SEP-POD2 -j DNAT --to-destination 192.168.1.11:8080
-A KUBE-SEP-POD3 -j DNAT --to-destination 192.168.1.12:8080
```

#### NodePort规则结构：
```bash
# NodePort入口规则
-A INPUT -p tcp --dport 30080 -j DNAT \
  --to-destination 10.96.0.100:80

## filepath: /Users/liang/code/cloud_OS/k8s/k8s_group_4/SERVICE_README.md
# Kubernetes Service 抽象实现指南

## 概述

本项目实现了完整的Kubernetes Service抽象，支持ClusterIP和NodePort两种类型的Service。Service作为Pod的网络代理层，提供统一且稳定的虚拟IP，通过iptables实现负载均衡和流量转发。

## 功能特性

### ✅ 已实现功能
- **ClusterIP Service**: 集群内部访问的虚拟IP服务
- **NodePort Service**: 外部访问的端口映射服务
- **动态Pod发现**: 通过标签选择器自动发现匹配的Pod
- **负载均衡**: 支持随机(Random)和轮询(RoundRobin)策略
- **iptables规则管理**: 自动创建和删除网络转发规则
- **Service生命周期管理**: 创建、更新、删除Service
- **实时监控**: 动态更新Service endpoints

### 🔧 技术架构
```
Client Request
    ↓
Service ClusterIP (虚拟IP)
    ↓
iptables KUBE-SERVICES 链
    ↓
iptables KUBE-SVC-* 链 (负载均衡)
    ↓
iptables KUBE-SEP-* 链 (DNAT转发)
    ↓
Pod Real IP:Port
```

## 快速开始

### 1. 环境准备

确保系统满足以下要求：
```bash
# 必需的依赖
- Python 3.7+
- Docker 20.0+
- iptables (Linux系统)
- etcd 3.5+
- Kafka 2.8+

# 权限要求
sudo权限 (用于iptables操作)
```

### 2. 部署Service组件

使用部署脚本启动所有服务：
```bash
# 一键部署所有组件
./deploy.sh

# 或者手动启动
./start.sh
```

### 3. 验证Service功能

```bash
# 检查Service Controller是否运行
ps aux | grep serviceController

# 查看iptables规则
sudo iptables -t nat -L KUBE-SERVICES -n
```

## Service使用指南

### 1. ClusterIP Service示例

创建一个集群内部访问的Service：

```yaml
# web-service-clusterip.yaml
apiVersion: v1
kind: Service
metadata:
  name: web-service
  namespace: default
  labels:
    app: web
spec:
  type: ClusterIP
  selector:
    app: web-app
    tier: frontend
  ports:
  - name: http
    port: 80
    targetPort: 8080
    protocol: TCP
  clusterIP: 10.96.0.100  # 可选，不指定则自动分配
```

**应用Service：**
```bash
# 通过API创建Service
curl -X POST http://localhost:5050/api/v1/services \
  -H "Content-Type: application/json" \
  -d @web-service-clusterip.yaml

# 或者使用Python API
python3 -c "
from pkg.apiObject.service import Service
from pkg.config.serviceConfig import ServiceConfig
import yaml

with open('web-service-clusterip.yaml') as f:
    config = ServiceConfig(yaml.safe_load(f))
    service = Service(config)
    service.create()
"
```

### 2. NodePort Service示例

创建一个外部可访问的Service：

```yaml
# web-service-nodeport.yaml
apiVersion: v1
kind: Service
metadata:
  name: web-external
  namespace: default
spec:
  type: NodePort
  selector:
    app: web-app
  ports:
  - name: http
    port: 80
    targetPort: 8080
    nodePort: 30080
    protocol: TCP
```

**访问Service：**
```bash
# 集群内访问
curl http://web-service:80
curl http://10.96.0.100:80

# 外部访问 (NodePort)
curl http://节点IP:30080
```

### 3. 查看Service状态

```bash
# 查看所有Service
curl http://localhost:5050/api/v1/services

# 查看特定Service详情
curl http://localhost:5050/api/v1/services/default/web-service

# 查看Service endpoints
curl http://localhost:5050/api/v1/services/default/web-service/endpoints
```

## Service工作原理

### 1. Service发现机制

Service通过标签选择器发现Pod：

```python
# Service Controller定期执行
def discover_pods(service):
    """
    1. 根据service.selector查询所有Pod
    2. 匹配Pod的labels
    3. 筛选Running状态的Pod
    4. 提取Pod IP和端口信息
    """
    matching_pods = []
    for pod in get_all_pods():
        if match_labels(pod.labels, service.selector):
            if pod.status == 'Running' and pod.pod_ip:
                matching_pods.append({
                    'ip': pod.pod_ip,
                    'port': service.target_port,
                    'name': pod.name
                })
    return matching_pods
```

### 2. iptables规则生成

#### ClusterIP规则结构：
```bash
# 主入口规则 (KUBE-SERVICES链)
-A KUBE-SERVICES -d 10.96.0.100/32 -p tcp --dport 80 \
  -j KUBE-SVC-ABCD1234

# 负载均衡规则 (KUBE-SVC-*链)
-A KUBE-SVC-ABCD1234 -m statistic --mode random --probability 0.33 \
  -j KUBE-SEP-POD1
-A KUBE-SVC-ABCD1234 -m statistic --mode random --probability 0.50 \
  -j KUBE-SEP-POD2
-A KUBE-SVC-ABCD1234 -j KUBE-SEP-POD3

# 目标转换规则 (KUBE-SEP-*链)
-A KUBE-SEP-POD1 -j DNAT --to-destination 192.168.1.10:8080
-A KUBE-SEP-POD2 -j DNAT --to-destination 192.168.1.11:8080
-A KUBE-SEP-POD3 -j DNAT --to-destination 192.168.1.12:8080
```

#### NodePort规则结构：
```bash
# NodePort入口规则
-A INPUT -p tcp --dport 30080 -j DNAT \
  --to-destination 10.96.0.100:80

