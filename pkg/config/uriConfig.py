class URIString(str):
    def __new__(cls, string: str):
        assert (
            "{" not in string and "}" not in string
        ), "请使用 '/api/v1/<n>' 而非 '/api/v1/{name}' 初始化"
        return super().__new__(cls, string)

    def format(self, **kwargs):
        return self.__class__(
            super().replace("<", "{").replace(">", "}").format(**kwargs)
        )


class URIConfig:
    # URI 协议方案
    # HOST = "localhost"
    HOST = "10.119.15.182"

    import sys

    if sys.platform == "darwin":
        import socket

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # 连接到一个外部地址，不需要真正发送数据
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            HOST = local_ip
        finally:
            s.close()

    PORT = 5050
    PREFIX = f"http://{HOST}:{PORT}"

    # -------------------- 资源路径定义 --------------------
    # Node 相关 (集群级别)
    NODES_URL = URIString("/api/v1/nodes")
    NODE_SPEC_URL = URIString("/api/v1/nodes/<name>")
    NODE_SPEC_STATUS_URL = URIString("/api/v1/nodes/<name>/status")
    NODE_ALL_PODS_URL = URIString("/api/v1/nodes/<name>/pods")

    # Pod 相关 (命名空间级别)
    GLOBAL_PODS_URL = URIString("/api/v1/pods")
    PODS_URL = URIString("/api/v1/namespaces/<namespace>/pods")
    POD_SPEC_URL = URIString("/api/v1/namespaces/<namespace>/pods/<name>")
    POD_SPEC_STATUS_URL = URIString("/api/v1/namespaces/<namespace>/pods/<name>/status")
    POD_SPEC_IP_URL = URIString("/api/v1/namespaces/<namespace>/pods/<name>/ip")

    # Service 相关
    GLOBAL_SERVICES_URL = URIString("/api/v1/services")
    SERVICE_URL = URIString("/api/v1/namespaces/<namespace>/services")
    SERVICE_SPEC_URL = URIString("/api/v1/namespaces/<namespace>/services/<name>")
    SERVICE_SPEC_STATUS_URL = URIString(
        "/api/v1/namespaces/<namespace>/services/<name>/status"
    )

    # Endpoint 相关
    ENDPOINT_URL = URIString("/api/v1/namespaces/<namespace>/endpoints")
    ENDPOINT_SPEC_URL = URIString("/api/v1/namespaces/<namespace>/endpoints/<name>")

    # Job 相关
    JOBS_URL = URIString("/apis/v1/namespaces/<namespace>/jobs")
    JOB_SPEC_URL = URIString("/apis/v1/namespaces/<namespace>/jobs/<name>")
    JOB_SPEC_STATUS_URL = URIString(
        "/apis/v1/namespaces/<namespace>/jobs/<name>/status"
    )
    JOB_FILE_URL = URIString("/apis/v1/namespaces/<namespace>/jobfiles")
    JOB_FILE_SPEC_URL = URIString("/apis/v1/namespaces/<namespace>/jobfiles/<name>")

    # ReplicaSet 相关
    GLOBAL_REPLICA_SETS_URL = URIString("/apis/v1/replicasets")
    REPLICA_SETS_URL = URIString("/apis/v1/namespaces/<namespace>/replicasets")
    REPLICA_SET_SPEC_URL = URIString(
        "/apis/v1/namespaces/<namespace>/replicasets/<name>"
    )
    REPLICA_SET_SPEC_STATUS_URL = URIString(
        "/apis/v1/namespaces/<namespace>/replicasets/<name>/status"
    )

    # DNS 相关
    DNS_URL = URIString("/apis/v1/namespaces/<namespace>/dns")
    DNS_SPEC_URL = URIString("/apis/v1/namespaces/<namespace>/dns/<name>")

    # HPA 相关
    GLOBAL_HPA_URL = URIString("/apis/v1/hpas")
    HPA_URL = URIString("/apis/v1/namespaces/<namespace>/hpas")
    HPA_SPEC_URL = URIString("/apis/v1/namespaces/<namespace>/hpas/<name>")
    HPA_SPEC_STATUS_URL = URIString(
        "/apis/v1/namespaces/<namespace>/hpas/<name>/status"
    )

    # Function 相关
    GLOBAL_FUNCTIONS_URL = URIString("/apis/v1/functions")
    FUNCTION_URL = URIString("/apis/v1/namespaces/<namespace>/functions")
    FUNCTION_SPEC_URL = URIString("/apis/v1/namespaces/<namespace>/functions/<name>")

    # Workflow 相关
    GLOBAL_WORKFLOWS_URL = URIString("/apis/v1/workflows")
    WORKFLOW_URL = URIString("/apis/v1/namespaces/<namespace>/workflows")
    WORKFLOW_SPEC_URL = URIString("/apis/v1/namespaces/<namespace>/workflows/<name>")
    WORKFLOW_SPEC_STATUS_URL = URIString(
        "/apis/v1/namespaces/<namespace>/workflows/<name>/status"
    )

    # PersistentVolume 相关 (集群级别)
    GLOBAL_PVS_URL = URIString("/api/v1/persistentvolumes")
    PV_SPEC_URL = URIString("/api/v1/persistentvolumes/<name>")
    PV_SPEC_STATUS_URL = URIString("/api/v1/persistentvolumes/<name>/status")

    # PersistentVolumeClaim 相关 (命名空间级别)
    GLOBAL_PVCS_URL = URIString("/api/v1/persistentvolumeclaims")
    PVCS_URL = URIString("/api/v1/namespaces/<namespace>/persistentvolumeclaims")
    PVC_SPEC_URL = URIString("/api/v1/namespaces/<namespace>/persistentvolumeclaims/<name>")
    PVC_SPEC_STATUS_URL = URIString("/api/v1/namespaces/<namespace>/persistentvolumeclaims/<name>/status")

    # StorageClass 相关 (集群级别)
    GLOBAL_STORAGE_CLASSES_URL = URIString("/api/v1/storageclasses")
    STORAGE_CLASS_SPEC_URL = URIString("/api/v1/storageclasses/<name>")

    # Scheduler 相关
    SCHEDULER_URL = URIString("/api/v1/scheduler")
    SCHEDULER_POD_URL = URIString(
        "/api/v1/namespaces/<namespace>/pods/<name>/scheduler/<node_name>"
    )

    # -------------------- 参数定义 --------------------
    URL_PARAM_NAME = "name"
    URL_PARAM_NAMESPACE = "namespace"
    URL_PARAM_NAME_PART = "{name}"
    URL_PARAM_NAMESPACE_PART = "{namespace}"

    # -------------------- 资源映射 --------------------
    # 假设已从 api_object 模块导入相关资源类型常量
    API_RESOURCE_MAP = {
        "Pod": PODS_URL,
        "Service": SERVICE_URL,
        "Dns": DNS_URL,
        "Node": NODES_URL,
        "Job": JOBS_URL,
        "ReplicaSet": REPLICA_SETS_URL,
        "HPA": HPA_URL,
        "Function": FUNCTION_URL,
    }

    API_SPEC_RESOURCE_MAP = {
        "Pod": POD_SPEC_URL,
        "Service": SERVICE_SPEC_URL,
        "Dns": DNS_SPEC_URL,
        "Node": NODE_SPEC_URL,
        "Job": JOB_SPEC_URL,
        "ReplicaSet": REPLICA_SET_SPEC_URL,
        "HPA": HPA_SPEC_URL,
        "Function": FUNCTION_SPEC_URL,
    }


if __name__ == "__main__":
    print("[INFO]Node 列表 URL:", URIConfig.NODES_URL)
    print("[INFO]Pod 详情 URL 模板:", URIConfig.POD_SPEC_URL)
    print(
        "[INFO]Pod 详情 URL 实例:",
        URIConfig.POD_SPEC_URL.format(namespace="default", name="my-pod"),
    )
    print("[INFO]Service 资源映射:", URIConfig.API_RESOURCE_MAP["Service"])
