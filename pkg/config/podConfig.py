from pkg.config.containerConfig import ContainerConfig


class PodConfig:
    def __init__(self, arg_json):
        # --- static information ---
        metadata = arg_json.get("metadata")
        self.name = metadata.get("name")
        self.namespace = metadata.get("namespace", "default")
        # lcl: 之前遗漏了labels属性，添加上，方便selector进行
        # wcc: 是的忘了。label的key不固定是app和env，只能保存一个json
        self.labels = metadata.get("labels", {})
        self.app = self.labels.get("app", None)
        self.env = self.labels.get("env", None)

        spec = arg_json.get("spec")
        volumes = spec.get("volumes", [])
        containers = spec.get("containers", [])
        self.node_selector = spec.get("nodeSelector", {})
        self.volume, self.containers = dict(), []

        # 解析卷配置，只支持 PVC 类型
        for volume in volumes:
            volume_name = volume.get("name")
            if "persistentVolumeClaim" in volume:
                # PVC 类型
                pvc = volume.get("persistentVolumeClaim")
                self.volume[volume_name] = {
                    "type": "pvc",
                    "claimName": pvc.get("claimName"),
                }
            else:
                # 不支持的卷类型，跳过并记录警告
                print(
                    f"[WARN] Unsupported volume type in volume '{volume_name}', only persistentVolumeClaim is supported"
                )
                continue

        for container in containers:
            self.containers.append(ContainerConfig(self.volume, container))

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
                "volumes": self.volume,
                "containers": [container.to_dict() for container in self.containers],
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
