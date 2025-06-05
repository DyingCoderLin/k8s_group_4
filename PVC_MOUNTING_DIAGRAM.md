# PVC挂载流程图

## 整体架构图

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Pod YAML      │    │   API Server    │    │   PV Controller │
│                 │    │                 │    │                 │
│ volumes:        │    │ PVC/PV Storage  │    │ Dynamic         │
│ - name: storage │    │ & Binding Info  │    │ Provisioning    │
│   pvc:          │    │                 │    │                 │
│     claimName   │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │                       │                       │
         ▼                       │                       │
┌─────────────────┐              │                       │
│   PodConfig     │              │                       │
│                 │              │                       │
│ Parse volumes   │              │                       │
│ Extract PVC     │              │                       │
│ references      │              │                       │
└─────────────────┘              │                       │
         │                       │                       │
         ▼                       │                       │
┌─────────────────┐              │                       │
│ContainerConfig  │              │                       │
│                 │              │                       │
│ Parse           │              │                       │
│ volumeMounts    │              │                       │
│ Create PVC refs │              │                       │
└─────────────────┘              │                       │
         │                       │                       │
         ▼                       │                       │
┌─────────────────┐              │                       │
│   Pod.__init__  │              │                       │
│                 │              │                       │
│ Create          │              │                       │
│ VolumeResolver  │◄─────────────┘                       │
│                 │                                      │
└─────────────────┘                                      │
         │                                               │
         ▼                                               │
┌─────────────────┐                                      │
│ VolumeResolver  │                                      │
│                 │                                      │
│ resolve_volumes │                                      │
│ _resolve_pvc    │                                      │
│ _mount_nfs      │                                      │
└─────────────────┘                                      │
         │                                               │
         ▼                                               │
┌─────────────────┐                                      │
│Docker Container │                                      │
│                 │                                      │
│ Volume binds:   │                                      │
│ host:container  │                                      │
│                 │                                      │
└─────────────────┘                                      │
         │                                               │
         ▼                                               │
┌─────────────────┐                                      │
│ Actual Storage  │                                      │
│                 │                                      │
│ hostPath or     │◄─────────────────────────────────────┘
│ NFS mount       │
│                 │
└─────────────────┘
```

## 详细执行流程

```
1. Pod Creation Request
   │
   ▼
2. PodConfig.parse()
   │
   ├── volumes: [{"name": "storage", "persistentVolumeClaim": {"claimName": "my-pvc"}}]
   │
   ▼
3. PodConfig.volume = {"storage": {"type": "pvc", "claimName": "my-pvc"}}
   │
   ▼
4. ContainerConfig.parse()
   │
   ├── volumeMounts: [{"name": "storage", "mountPath": "/data"}]
   │
   ▼
5. ContainerConfig.volumes = {"pvc:my-pvc": {"bind": "/data", "mode": "rw"}}
   │
   ▼
6. Pod.__init__()
   │
   ├── Create VolumeResolver(api_client, uri_config)
   │
   ▼
7. VolumeResolver.resolve_volumes()
   │
   ├── Input: [{"name": "storage", "type": "pvc", "claimName": "my-pvc"}]
   │
   ▼
8. VolumeResolver._resolve_pvc("my-pvc", namespace)
   │
   ├── GET /api/v1/namespaces/{namespace}/persistentvolumeclaims/my-pvc
   │   └── Response: {"status": {"volumeName": "my-pv"}}
   │
   ├── GET /api/v1/persistentvolumes/my-pv
   │   └── Response: {"spec": {"hostPath": {"path": "/mnt/data"}}}
   │   └── 或者: {"spec": {"nfs": {"server": "192.168.1.100", "path": "/export"}}}
   │
   ▼
9. 根据PV类型处理:
   │
   ├── hostPath: 直接返回 "/mnt/data"
   │
   └── NFS: 调用 _mount_nfs_volume()
       │
       ├── 创建挂载点: "/tmp/nfs-mounts/my-pv"
       │
       ├── 执行: sudo mount -t nfs 192.168.1.100:/export /tmp/nfs-mounts/my-pv
       │
       └── 返回: "/tmp/nfs-mounts/my-pv"
   │
   ▼
10. 返回: resolved_volumes = {"storage": "/mnt/data"}
    │
    ▼
11. 容器创建循环
    │
    ├── 提取: "pvc:my-pvc" → mountPath: "/data"
    │
    ├── 查找: volume_name = "storage"
    │
    ▼
12. VolumeResolver.get_container_volume_mounts()
    │
    ├── Input: [{"name": "storage", "mountPath": "/data", "readOnly": false}]
    │
    ├── resolved_volumes: {"storage": "/mnt/data"}
    │
    ├── 生成: volume_bind = "/mnt/data:/data:rw"
    │
    └── 返回: ["/mnt/data:/data:rw"]
    │
    ▼
13. Docker容器创建
    │
    ├── docker.containers.run(**args, volumes=["/mnt/data:/data:rw"])
    │
    └── 容器内路径 /data 映射到主机路径 /mnt/data
    │
    ▼
14. 容器运行，可以访问持久化存储
```

## 数据结构转换图

```
YAML格式:
volumes:
- name: storage
  persistentVolumeClaim:
    claimName: my-pvc
containers:
- volumeMounts:
  - name: storage
    mountPath: /data

↓ PodConfig.__init__()

PodConfig.volume:
{
  "storage": {
    "type": "pvc",
    "claimName": "my-pvc"
  }
}

↓ ContainerConfig.__init__()

ContainerConfig.volumes:
{
  "volumes": {
    "pvc:my-pvc": {
      "bind": "/data",
      "mode": "rw"
    }
  }
}

↓ VolumeResolver.resolve_volumes()

resolved_volumes:
{
  "storage": "/mnt/data"  # 或 "/tmp/nfs-mounts/my-pv"
}

↓ VolumeResolver.get_container_volume_mounts()

volume_binds:
["/mnt/data:/data:rw"]

↓ Docker容器创建

Docker API参数:
{
  "volumes": ["/mnt/data:/data:rw"],
  "image": "nginx",
  "name": "container-name",
  ...
}
```

## 关键组件职责

```
┌─────────────────┐
│    PodConfig    │
│                 │
│ 职责:           │
│ • 解析Pod YAML  │
│ • 提取PVC引用   │
│ • 构建卷映射    │
└─────────────────┘
         │
         ▼
┌─────────────────┐
│ContainerConfig  │
│                 │
│ 职责:           │
│ • 解析容器配置  │
│ • 处理卷挂载点  │
│ • 生成Docker参数│
└─────────────────┘
         │
         ▼
┌─────────────────┐
│ VolumeResolver  │
│                 │
│ 职责:           │
│ • PVC→路径解析  │
│ • NFS挂载管理   │
│ • 卷绑定生成    │
│ • 资源清理      │
└─────────────────┘
         │
         ▼
┌─────────────────┐
│   Docker API    │
│                 │
│ 职责:           │
│ • 创建容器      │
│ • 绑定卷        │
│ • 网络配置      │
└─────────────────┘
```
