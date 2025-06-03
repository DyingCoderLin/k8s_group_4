# Minik8s 持久化存储实现方案

## 1. 概述

本实现基于 Kubernetes PV/PVC 模型，支持静态和动态供应，实现了 hostPath 和 NFS 两种存储类型，满足单机和多机持久化存储需求。

## 2. 架构设计

### 2.1 核心组件

- **PV (Persistent Volume)**: 集群级别的存储资源抽象
- **PVC (Persistent Volume Claim)**: 用户对存储资源的请求声明  
- **SimplePV Controller**: 负责 PV/PVC 的生命周期管理和动态供应

### 2.2 存储类型

1. **hostPath**: 单机本地存储，适用于开发和测试
2. **NFS**: 网络文件系统，支持多机共享访问

## 3. 实现特性

### 3.1 PV/PVC 抽象 (简化版)

- **PV**: 由管理员创建或动态供应的存储资源
  - 容量 (capacity)
  - 状态 (phase): Available, Bound, Released
  - 存储源: hostPath 或 NFS
  - 声明引用 (claimRef): 已绑定的 PVC 信息

- **PVC**: 用户的存储请求
  - 容量需求 (resources.requests.storage)
  - 状态 (phase): Pending, Bound, Lost
  - 标签 (labels): 用于指示存储类型 (如 storage-type: nfs)

### 3.2 供应方式

#### 静态供应
1. 管理员预先创建 PV
2. 用户创建 PVC
3. 控制器根据需求匹配合适的 PV
4. 绑定 PV 和 PVC

#### 动态供应 (简化版)
1. 用户创建 PVC，可通过标签指定存储类型 (如 storage-type: nfs)
2. SimplePV 控制器检测到未绑定的 PVC
3. 自动创建对应的 PV，默认使用 hostPath，或根据标签使用 NFS
4. 自动绑定新创建的 PV 和 PVC

### 3.3 生命周期管理

```
PV: Available -> Bound -> Released -> (Deleted/Available)
PVC: Pending -> Bound -> (Deleted)
```

1. **Available**: PV 可用，等待绑定
2. **Bound**: PV 已绑定到 PVC
3. **Released**: PVC 被删除，PV 等待回收
4. **Failed**: PV 回收失败

## 4. NFS 多机存储实现

### 4.1 架构
```
[Master Node] - [Worker Node 1] - [Worker Node 2]
      |               |                |
      +--- NFS Client ---+--- NFS Client
                |
          [NFS Server]
          (存储节点)
```

### 4.2 NFS 服务器配置

在专门的存储节点或 Master 节点上部署 NFS 服务器：

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install nfs-kernel-server

# 创建共享目录
sudo mkdir -p /nfs/pv-storage
sudo chown nobody:nogroup /nfs/pv-storage
sudo chmod 777 /nfs/pv-storage

# 配置导出
echo "/nfs/pv-storage *(rw,sync,no_subtree_check,no_root_squash)" | sudo tee -a /etc/exports

# 启动服务
sudo systemctl restart nfs-kernel-server
sudo exportfs -a
```

### 4.3 客户端配置

在所有工作节点上安装 NFS 客户端：

```bash
# Ubuntu/Debian
sudo apt install nfs-common

# macOS (使用内置 NFS 客户端或安装额外工具)
# 已内置支持，无需额外安装
```

## 5. 实现细节

### 5.1 目录结构
```
pkg/
├── apiObject/
│   ├── persistentVolume.py      # PV 对象
│   └── persistentVolumeClaim.py # PVC 对象
├── config/
│   ├── pvConfig.py              # PV 配置
│   └── pvcConfig.py             # PVC 配置
├── controller/
│   ├── pvController.py          # PV 控制器
│   └── pvStarter.py            # PV 控制器启动器
└── storage/
    ├── __init__.py
    ├── provisioner.py           # 动态供应器
    ├── hostPathProvisioner.py   # hostPath 供应器
    └── nfsProvisioner.py        # NFS 供应器
```

### 5.2 核心算法

#### PV/PVC 匹配算法
1. 容量匹配：PV 容量 >= PVC 请求容量

#### 动态供应流程
1. 监听 PVC 创建事件
2. 检查是否有合适的 PV 可绑定
3. 如果没有且指定了 StorageClass，触发动态供应
4. 根据 StorageClass 配置创建新的 PV
5. 绑定新 PV 和 PVC

## 6. 使用示例

### 6.1 静态供应示例

创建 PV：
```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: nfs-pv-1
spec:
  capacity:
    storage: 1Gi
  accessModes:
    - ReadWriteMany
  persistentVolumeReclaimPolicy: Retain
  nfs:
    server: 192.168.1.100
    path: /nfs/pv-storage/vol1
```

创建 PVC：
```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: nfs-pvc
spec:
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 500Mi
```

### 6.2 动态供应示例

创建 StorageClass：
```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: nfs-dynamic
provisioner: minik8s.io/nfs
parameters:
  server: 192.168.1.100
  path: /nfs/pv-storage
```

创建 PVC（指定 StorageClass）：
```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: dynamic-pvc
spec:
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 2Gi
  storageClassName: nfs-dynamic
```

### 6.3 Pod 中使用 PVC

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: mysql-pod
spec:
  containers:
  - name: mysql
    image: mysql:5.7
    env:
    - name: MYSQL_ROOT_PASSWORD
      value: "password"
    volumeMounts:
    - name: mysql-storage
      mountPath: /var/lib/mysql
  volumes:
  - name: mysql-storage
    persistentVolumeClaim:
      claimName: nfs-pvc
```

## 7. 测试场景

### 7.1 数据持久化测试
1. 创建 Pod 并写入数据到 PV
2. 删除 Pod
3. 创建新 Pod 绑定同一 PVC
4. 验证数据仍然存在

### 7.2 多机访问测试
1. 在节点 A 创建 Pod 写入数据
2. 删除节点 A 的 Pod
3. 在节点 B 创建 Pod 绑定同一 PVC
4. 验证可以访问之前写入的数据

### 7.3 动态供应测试
1. 创建 StorageClass
2. 创建 PVC 指定该 StorageClass
3. 验证自动创建对应 PV 并绑定

## 8. 注意事项

1. **权限管理**: 确保 NFS 服务器配置正确的权限
2. **网络连通性**: 所有节点都能访问 NFS 服务器
3. **错误处理**: 处理网络断开、服务器不可用等异常情况
4. **资源清理**: 实现正确的 PV 回收策略
5. **并发控制**: 处理多个 PVC 同时请求相同 PV 的情况

## 9. 扩展功能

1. **快照支持**: 实现 VolumeSnapshot 功能
2. **容量扩展**: 支持在线扩容 PV
3. **监控指标**: 提供存储使用情况监控
4. **多存储后端**: 支持更多存储类型（Ceph、GlusterFS 等）
