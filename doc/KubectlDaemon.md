# kubectl 守护进程使用指南

kubectl现在支持作为后台守护进程运行，提供更高效的命令行体验。

## 文件说明

- `kubectl.py` - 原始的kubectl实现（仍可直接使用）
- `kubectl_daemon.py` - kubectl守护进程服务器
- `kubectl_client.py` - kubectl客户端（连接到守护进程）
- `kubectl_service.sh` - 守护进程管理脚本
- `kubectl` - 便捷的kubectl包装脚本
- `test_kubectl_daemon.sh` - 功能测试脚本

## 快速开始

### 方法一：使用管理脚本

```bash
# 启动守护进程
./kubectl_service.sh start

# 使用客户端执行命令
python3 kubectl_client.py get nodes
python3 kubectl_client.py apply -f testFile/test-pod-server-1.yaml

# 停止守护进程
./kubectl_service.sh stop
```

### 方法二：使用便捷脚本（推荐）

```bash
# 直接使用kubectl脚本（会自动启动守护进程）
./kubectl get nodes
./kubectl apply -f testFile/test-pod-server-1.yaml
./kubectl get pods
```

## 守护进程管理

### 启动守护进程

```bash
# 使用管理脚本
./kubectl_service.sh start

# 或者手动启动
python3 kubectl_daemon.py --daemonize
```

### 检查状态

```bash
./kubectl_service.sh status
```

### 停止守护进程

```bash
./kubectl_service.sh stop
```

### 重启守护进程

```bash
./kubectl_service.sh restart
```

## 支持的命令

守护进程支持所有原有的kubectl命令：

### Get 命令
```bash
./kubectl get nodes
./kubectl get pods
./kubectl get services
./kubectl get replicasets
./kubectl get hpa
./kubectl get pods --all-namespaces
```

### Apply 命令（统一）
```bash
./kubectl apply -f simple.yaml  # 自动识别资源类型
./kubectl apply -f testFile/test-pod-server-1.yaml
./kubectl apply -f testFile/test-service-clusterip.yaml
./kubectl apply -f testFile/test-replicaset.yaml
```

### Add Node 命令（特殊处理）
```bash
./kubectl add node testFile/node-1.yaml
```

### Describe 命令
```bash
./kubectl describe node node-1
./kubectl describe pod my-pod
./kubectl describe service my-service
```

### Delete 命令
```bash
./kubectl delete pod my-pod
./kubectl delete service my-service
./kubectl delete replicaset my-rs
```

### Scale 命令
```bash
./kubectl scale replicaset my-rs --replicas=3
```

## 测试

运行完整的功能测试：

## 故障排除

### 守护进程无法启动
```bash
# 检查是否有旧的套接字文件
ls -la /tmp/kubectl_daemon.sock
rm -f /tmp/kubectl_daemon.sock

# 查看错误日志
tail -f /tmp/kubectl_daemon.log
```

### 客户端连接失败
```bash
# 确认守护进程正在运行
./kubectl_service.sh status

# 重启守护进程
./kubectl_service.sh restart
```

### 权限问题
```bash
# 确保脚本有执行权限
chmod +x kubectl kubectl_service.sh kubectl_daemon.py kubectl_client.py
```

## 配置选项

### 自定义套接字路径
```bash
# 启动守护进程
python3 kubectl_daemon.py --socket /custom/path/kubectl.sock

# 使用客户端
python3 kubectl_client.py --socket /custom/path/kubectl.sock
```

### 后台运行选项
```bash
# 前台运行（调试用）
python3 kubectl_daemon.py

# 后台运行
python3 kubectl_daemon.py --daemonize
```

## 兼容性

- 完全兼容原有的kubectl.py命令
- 支持所有现有的YAML配置文件
- 保持相同的命令行参数格式
- 可以随时切换回原有的直接模式

## 开发和调试

### 查看日志
```bash
tail -f /tmp/kubectl_daemon.log
```

### 手动测试通信
```bash
# 启动守护进程（前台模式便于调试）
python3 kubectl_daemon.py

# 在另一个终端测试客户端
python3 kubectl_client.py get nodes
```
