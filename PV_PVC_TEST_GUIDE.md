# PV/PVC 新功能测试指南

## 概述

这个指南将帮助你测试新的 PV/PVC 功能，包括基于 `storageClassName` 的动态供应和基于 `volumeName` 的特定 PV 绑定。

## 前置准备

1. **确保 API 服务器和 etcd 正在运行**
   ```bash
   # 在一个终端窗口中启动主服务
   ./start.sh
   ```

2. **启动 PV 控制器**
   ```bash
   # 在另一个终端窗口中启动 PV 控制器
   ./start_pv.sh
   ```

3. **等待服务就绪**
   - API 服务器通常在 5050 端口启动
   - PV 控制器会自动连接到 etcd 并开始监控 PVC

## 快速测试

运行综合测试脚本来验证所有新功能：

```bash
./test_new_pv_pvc.sh
```

这个脚本会测试：
- 动态供应（基于 storageClassName）
- 特定 PV 绑定（基于 volumeName）
- Pod 纯 PVC 挂载
- 存储类型匹配验证

## 手动测试步骤

### 1. 测试动态供应

创建一个使用 hostPath 存储类的 PVC：
```bash
curl -X POST http://localhost:5050/api/v1/namespaces/default/persistentvolumeclaims/my-dynamic-pvc \
  -H "Content-Type: application/json" \
  -d '{
    "apiVersion": "v1",
    "kind": "PersistentVolumeClaim",
    "metadata": {
      "name": "my-dynamic-pvc",
      "namespace": "default"
    },
    "spec": {
      "storageClassName": "hostPath",
      "resources": {
        "requests": {
          "storage": "1Gi"
        }
      }
    }
  }'
```

等待几秒钟，然后检查是否自动创建了 PV：
```bash
curl http://localhost:5050/api/v1/persistentvolumes
```

### 2. 测试特定 PV 绑定

创建一个指定 PV 名称的 PVC：
```bash
curl -X POST http://localhost:5050/api/v1/namespaces/default/persistentvolumeclaims/my-specific-pvc \
  -H "Content-Type: application/json" \
  -d '{
    "apiVersion": "v1",
    "kind": "PersistentVolumeClaim",
    "metadata": {
      "name": "my-specific-pvc",
      "namespace": "default"
    },
    "spec": {
      "storageClassName": "hostPath",
      "volumeName": "my-target-pv",
      "resources": {
        "requests": {
          "storage": "2Gi"
        }
      }
    }
  }'
```

检查是否创建了名为 "my-target-pv" 的 PV：
```bash
curl http://localhost:5050/api/v1/persistentvolumes/my-target-pv
```

### 3. 测试 Pod 挂载

创建一个只使用 PVC 的 Pod：
```bash
curl -X POST http://localhost:5050/api/v1/namespaces/default/pods/test-pod \
  -H "Content-Type: application/json" \
  -d '{
    "apiVersion": "v1",
    "kind": "Pod",
    "metadata": {
      "name": "test-pod",
      "namespace": "default"
    },
    "spec": {
      "containers": [
        {
          "name": "test-container",
          "image": "busybox:latest",
          "command": ["sleep", "3600"],
          "volumeMounts": [
            {
              "name": "data-volume",
              "mountPath": "/data"
            }
          ]
        }
      ],
      "volumes": [
        {
          "name": "data-volume",
          "persistentVolumeClaim": {
            "claimName": "my-dynamic-pvc"
          }
        }
      ]
    }
  }'
```

### 4. 验证数据持久性

连接到容器并创建测试文件：
```bash
# 首先获取容器ID（需要 kubelet 运行）
docker exec -it <container_id> sh

# 在容器内创建测试文件
echo "Hello from PVC!" > /data/test.txt
cat /data/test.txt
exit
```

删除并重新创建 Pod，验证数据是否保持：
```bash
curl -X DELETE http://localhost:5050/api/v1/namespaces/default/pods/test-pod
# 等待几秒钟
# 重新创建相同的 Pod（使用上面的命令）
# 再次检查 /data/test.txt 是否仍然存在
```

## 错误测试

### 测试存储类型不匹配

创建一个 hostPath PV：
```bash
curl -X POST http://localhost:5050/api/v1/persistentvolumes/hostpath-pv \
  -H "Content-Type: application/json" \
  -d '{
    "apiVersion": "v1",
    "kind": "PersistentVolume",
    "metadata": {
      "name": "hostpath-pv"
    },
    "spec": {
      "capacity": {
        "storage": "1Gi"
      },
      "hostPath": {
        "path": "/tmp/test"
      }
    }
  }'
```

然后尝试用 NFS storageClassName 绑定到它：
```bash
curl -X POST http://localhost:5050/api/v1/namespaces/default/persistentvolumeclaims/mismatch-pvc \
  -H "Content-Type: application/json" \
  -d '{
    "apiVersion": "v1",
    "kind": "PersistentVolumeClaim",
    "metadata": {
      "name": "mismatch-pvc",
      "namespace": "default"
    },
    "spec": {
      "storageClassName": "nfs",
      "volumeName": "hostpath-pv",
      "resources": {
        "requests": {
          "storage": "1Gi"
        }
      }
    }
  }'
```

检查 PVC 状态，应该显示 Failed：
```bash
curl http://localhost:5050/api/v1/namespaces/default/persistentvolumeclaims/mismatch-pvc
```

## 日志监控

监控 PV 控制器的日志来了解处理过程：
```bash
# 如果使用 start_pv.sh 启动，日志会显示在终端
# 查看处理日志，包括：
# - PVC 检测
# - PV 创建
# - 绑定操作
# - 错误处理
```

## 清理

测试完成后清理资源：
```bash
# 删除 Pod
curl -X DELETE http://localhost:5050/api/v1/namespaces/default/pods/test-pod

# 删除 PVC（会自动解绑 PV）
curl -X DELETE http://localhost:5050/api/v1/namespaces/default/persistentvolumeclaims/my-dynamic-pvc
curl -X DELETE http://localhost:5050/api/v1/namespaces/default/persistentvolumeclaims/my-specific-pvc
curl -X DELETE http://localhost:5050/api/v1/namespaces/default/persistentvolumeclaims/mismatch-pvc

# 删除 PV
curl -X DELETE http://localhost:5050/api/v1/persistentvolumes/my-target-pv
curl -X DELETE http://localhost:5050/api/v1/persistentvolumes/hostpath-pv
# 动态创建的 PV 会有自动生成的名称，需要先列出再删除
```

## 故障排除

1. **PVC 一直处于 Pending 状态**
   - 检查 PV 控制器是否运行
   - 检查存储类型是否正确
   - 查看控制器日志了解错误信息

2. **Pod 无法挂载 PVC**
   - 确认 PVC 已绑定到 PV
   - 检查 kubelet 是否运行
   - 验证存储路径是否存在

3. **NFS 挂载失败**
   - 检查 NFS 服务器是否运行
   - 验证网络连接
   - 确认 NFS 导出配置

4. **类型不匹配错误**
   - 检查 PVC 的 storageClassName 与目标 PV 类型是否匹配
   - 查看 PV 控制器日志中的错误信息

这个测试指南应该帮助你全面验证新的 PV/PVC 功能是否正常工作。
