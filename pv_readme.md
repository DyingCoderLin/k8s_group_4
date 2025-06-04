# Minik8s PV/PVC 持久化存储实现

## 概述

本实现为 Minik8s 提供了完整的持久化存储功能，包括 PV (Persistent Volume) 和 PVC (Persistent Volume Claim) 抽象。系统支持动态供应和静态绑定两种模式，简化了 Kubernetes 的存储模型，专注于核心功能。

## 核心功能

### 1. 存储类型支持
- **hostPath**: 本地主机路径存储（单节点）
- **NFS**: 网络文件系统存储（多节点共享）

### 2. PVC 绑定模式
- **动态供应**: 基于 `storageClassName` 自动创建匹配的 PV
- **特定绑定**: 基于 `volumeName` 绑定到指定的 PV（不存在时自动创建）
- **存储类型匹配**: 严格检查 PVC 的 storageClassName 与 PV 类型匹配

### 3. Pod 卷集成
- **纯 PVC 绑定**: Pod 只支持通过 PVC 挂载卷，移除了其他卷类型支持
- **自动路径解析**: 运行时自动解析 PVC 到实际存储路径
- **NFS 自动挂载**: 支持 NFS 卷的自动挂载和管理

## PVC 配置格式

### 动态供应 PVC
```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: pvc-dynamic-test
  namespace: default
spec:
  storageClassName: hostPath  # 或 nfs
  resources:
    requests:
      storage: 500Mi
```

### 特定 PV 绑定 PVC
```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: pvc-specific-test
  namespace: default
spec:
  storageClassName: hostPath  # 必须与目标 PV 类型匹配
  volumeName: my-specific-pv  # 目标 PV 名称
  resources:
    requests:
      storage: 2Gi
```

## 绑定逻辑

### 1. 当 PVC 指定了 volumeName
- 检查指定的 PV 是否存在
- **如果存在**: 验证存储类型是否匹配
  - 匹配：绑定到该 PV
  - 不匹配：标记 PVC 为 Failed 状态
- **如果不存在**: 根据 PVC 的 storageClassName 创建指定名称的 PV 并绑定

### 2. 当 PVC 未指定 volumeName（动态供应）
- 搜索可用的 PV，要求容量足够且存储类型匹配
- **找到匹配的 PV**: 直接绑定
- **未找到**: 根据 storageClassName 动态创建新 PV 并绑定

## Pod 卷挂载

Pod 现在只支持通过 PVC 挂载卷：

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: test-pod
spec:
  containers:
    - name: test-container
      image: busybox:latest
      volumeMounts:
        - name: data-volume
          mountPath: /data
  volumes:
    - name: data-volume
      persistentVolumeClaim:
        claimName: my-pvc  # 引用 PVC 名称
```

## 文件结构

```
pkg/config/
├── pvConfig.py          # PV 配置类
└── pvcConfig.py         # PVC 配置类（支持 storageClassName 和 volumeName）

pkg/apiObject/
├── persistentVolume.py     # PV API 对象
└── persistentVolumeClaim.py # PVC API 对象

pkg/controller/
├── pvController.py      # PV 控制器（动态供应和绑定逻辑）
└── pvStarter.py        # PV 控制器启动脚本

pkg/kubelet/
└── volumeResolver.py   # 卷解析器（只支持 PVC）

testFile/
├── pvc-dynamic-test.yaml           # 动态供应测试
├── pvc-specific-pv-test.yaml       # 特定 PV 绑定测试
├── pvc-specific-nfs-pv-test.yaml   # 特定 NFS PV 绑定测试
└── pod-pvc-only-test.yaml          # 纯 PVC Pod 测试
```

## 启动和测试

### 1. 启动 PV 控制器
```bash
./start_pv.sh
```

### 2. 运行新功能测试
```bash
./test_new_pv_pvc.sh
```

### 3. 运行完整测试
```bash
./test_pv_pvc.sh
```

## API 端点

### PV 管理（集群级别）
- `GET /api/v1/persistentvolumes` - 获取所有 PV
- `POST /api/v1/persistentvolumes/{name}` - 创建 PV
- `GET /api/v1/persistentvolumes/{name}` - 获取指定 PV
- `PUT /api/v1/persistentvolumes/{name}` - 更新 PV
- `DELETE /api/v1/persistentvolumes/{name}` - 删除 PV

### PVC 管理（命名空间级别）
- `GET /api/v1/persistentvolumeclaims` - 获取所有命名空间的 PVC
- `GET /api/v1/namespaces/{namespace}/persistentvolumeclaims` - 获取指定命名空间的 PVC
- `POST /api/v1/namespaces/{namespace}/persistentvolumeclaims/{name}` - 创建 PVC
- `GET /api/v1/namespaces/{namespace}/persistentvolumeclaims/{name}` - 获取指定 PVC
- `PUT /api/v1/namespaces/{namespace}/persistentvolumeclaims/{name}` - 更新 PVC
- `DELETE /api/v1/namespaces/{namespace}/persistentvolumeclaims/{name}` - 删除 PVC

## 特性说明

### 1. 简化设计
- 移除了 AccessMode、ReclaimPolicy 等复杂特性
- 移除了 StorageClass 概念，直接使用 storageClassName 字段
- 专注于核心的动态供应和绑定功能

### 2. 自动化功能
- PV 控制器自动监控 PVC 状态
- 支持动态创建 PV 和自动绑定
- 自动创建存储目录和设置权限
- NFS 卷自动挂载和管理

### 3. 错误处理
- 存储类型不匹配时的明确错误提示
- PV 不可用时的状态反馈
- API 调用失败的优雅处理

### 4. 持久化支持
- 数据在 Pod 重启后保持不变
- 支持多 Pod 共享同一 PVC（NFS）
- 完整的生命周期管理

## 环境变量配置

### NFS 相关
- `NFS_SERVER`: NFS 服务器地址（默认: localhost）
- `IS_NFS_SERVER`: 是否运行在 NFS 服务器上（默认: false）

## 测试场景

1. **动态供应测试**: 创建不同存储类型的 PVC，验证自动 PV 创建
2. **特定绑定测试**: 指定 PV 名称的 PVC 绑定和自动创建
3. **类型匹配测试**: 验证存储类型不匹配的错误处理
4. **Pod 集成测试**: 验证 Pod 只通过 PVC 挂载卷的功能
5. **持久化测试**: 验证数据在 Pod 重启后的持久性

这个实现提供了一个功能完整但简化的 Kubernetes 风格持久化存储系统，适合教学和小型部署环境使用。
