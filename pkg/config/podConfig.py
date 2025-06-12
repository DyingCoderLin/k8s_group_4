from pkg.config.containerConfig import ContainerConfig # 确保这个导入是正确的

class PodConfig:
    def __init__(self, arg_json):
        # --- static information ---
        metadata = arg_json.get("metadata", {}) # 确保metadata是字典，避免KeyError
        self.name = metadata.get("name")
        self.namespace = metadata.get("namespace", "default")
        self.labels = metadata.get("labels", {})
        self.app = self.labels.get("app", None)
        self.env = self.labels.get("env", None)

        spec = arg_json.get("spec", {}) # 确保spec是字典，避免KeyError
        self.volumes = spec.get("volumes", [])
        containers = spec.get("containers", [])
        self.node_selector = spec.get("nodeSelector", {})

        # 新增：解析 Pod 级别的 securityContext
        self.security_context = spec.get("securityContext", {}) 

        self.volume, self.containers = dict(), []

        # 目前只支持hostPath，并且忽略type字段
        for volume in self.volumes:
            volume_name = volume.get("name")
            host_path = volume.get("hostPath")

            # 处理hostPath的不同格式
            if isinstance(host_path, dict):
                # 标准格式：hostPath是字典，包含path字段
                path = host_path.get("path")
            elif isinstance(host_path, str):
                # 简化格式：hostPath直接是路径字符串
                path = host_path
            else:
                # 异常情况：使用默认路径并记录警告
                path = "/tmp"
                print(f"[WARNING] PodConfig: volume '{volume_name}' hostPath格式异常，使用默认路径: {path}")

            self.volume[volume_name] = path

        # for container in containers:
        #     self.containers.append(ContainerConfig(self.volume, container))

        for container_json in containers: # 遍历原始的容器 JSON 配置
            # 在这里，你需要将 Pod 级别的 securityContext 传递给 ContainerConfig
            # 这样 ContainerConfig 才能知道如何合并或覆盖
            self.containers.append(ContainerConfig(self.volume, container_json, pod_security_context=self.security_context))

        # --- running information ---
        self.cni_name = None
        self.subnet_ip = None
        self.node_name = None
        self.status = None

    def to_dict(self):
        return {
            "metadata": {
                "name": self.name,
                "namespace": self.namespace,
                "labels": self.labels,
            },
            "spec": {
                "volumes": self.volumes,
                "containers": [container.to_dict() for container in self.containers],
                # "nodeSelector": self.node_selector, # 确保 nodeSelector 也在 to_dict 中
                "securityContext": self.security_context, # 新增：将 securityContext 序列化回字典
            },
            "cni_name": self.cni_name,
            "subnet_ip": self.subnet_ip,
            "node_name": str(self.node_name),
            "status": self.status,
        }

    # wcc: 别加这个
    # def __getstate__(self):
    #     return self.to_dict()

    # wcc: 加这个函数会导致pickle.load不正确

    # def __setstate__(self, state):
    #     self.__init__(state)
    # 重新初始化容器配置
    # self.containers = [ContainerConfig(self.volume, container) for container in state['spec']['containers']]

    # 为了方便selector进行，增加了函数实现
    def get_app_label(self):
        """
        从Pod的labels中获取app标签值
        如果labels不存在或app不存在，返回None
        wcc: 不一定是app
        """
        # print(f'[INFO]podConfig.get_app_label: {self.labels}')
        if hasattr(self, "labels") and self.labels:
            return self.labels.get("app", None)
        return None

    def get_env_label(self):
        """
        从Pod的labels中获取env标签值
        如果labels不存在或env不存在，返回None
        """
        # print(f'[INFO]podConfig.get_env_label: {self.labels}')
        if hasattr(self, "labels") and self.labels:
            return self.labels.get("env", None)
        return None
