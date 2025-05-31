class ContainerConfig:
    def __init__(self, volumes_map, arg_json):
        self.name = arg_json.get("name")
        self.image = arg_json.get("image")
        self.command = arg_json.get("command", [])
        self.args = arg_json.get("args", [])

        self.port = dict()
        if arg_json.get("port") is not None:
            port = dict()
            for port_json in arg_json.get("port"):
                protocol = port_json.get("protocol", "tcp").lower()
                port[f"{port_json.get('containerPort')}/{protocol}"] = (
                    port_json.get("hostPort", None)
                )
            self.port["ports"] = port

        # resource只支持cpu和内存的request和limit，不支持ephemeral-storage和nvidia.com/gpu
        self.resources = dict()
        requests = arg_json.get("resources").get("requests")
        if requests:
            if requests.get("cpu"):
                self.resources["cpu_shares"] = int(requests.get("cpu") * 1024)
            if requests.get("memory"):
                self.mem_request = requests.get("memory")
        limits = arg_json.get("resources").get("limits")
        if limits:
            if limits.get("cpu"):
                self.resources["cpu_period"] = 100000
                self.resources["cpu_quota"] = (
                    limits.get("cpu") * self.resources["cpu_period"]
                )
            if limits.get("memory"):
                self.resources["mem_limit"] = limits.get("memory")

        # volumeMounts部分忽略subPath字段
        self.volumes = dict()
        if arg_json.get("volumeMounts") is not None:
            volumes = dict()
            for volume in arg_json.get("volumeMounts"):
                mode = "ro" if volume.get("readOnly", False) else "rw"
                host_path = volumes_map[volume.get("name")]
                bind_path = volume.get("mountPath")

                volumes[host_path] = {"bind": bind_path, "mode": mode}
            self.volumes["volumes"] = volumes

    def dockerapi_args(self):
        return {
            "image": self.image,
            "name": self.name,
            "command": self.command + self.args,
            **self.volumes,
            **self.port,
            **self.resources,
        }

    def to_dict(self):
        """
        将ContainerConfig对象转换为字典表示，保留所有属性。
        返回的字典格式与Kubernetes API中container spec保持一致。
        """
        result = {"name": self.name, "image": self.image}

        # 处理命令和参数
        if self.command:
            result["command"] = self.command
        if self.args:
            result["args"] = self.args

        # 处理端口
        if hasattr(self, "port") and self.port and "ports" in self.port:
            ports = []
            for port_str, host_port in self.port["ports"].items():
                container_port, protocol = port_str.split("/")
                port_obj = {
                    "containerPort": int(container_port),
                    "protocol": protocol.upper(),
                }
                if host_port is not None:
                    port_obj["hostPort"] = int(host_port)
                ports.append(port_obj)
            if ports:
                result["ports"] = ports

        # 处理资源限制
        resources = {}

        # 处理requests
        requests = {}
        if hasattr(self, "resources") and "cpu_shares" in self.resources:
            requests["cpu"] = self.resources["cpu_shares"] / 1024
        if hasattr(self, "mem_request"):
            requests["memory"] = self.mem_request

        # 处理limits
        limits = {}
        if hasattr(self, "resources"):
            if "cpu_quota" in self.resources and "cpu_period" in self.resources:
                limits["cpu"] = (
                    self.resources["cpu_quota"] / self.resources["cpu_period"]
                )
            if "mem_limit" in self.resources:
                limits["memory"] = self.resources["mem_limit"]

        # 组合资源字段
        if requests:
            resources["requests"] = requests
        if limits:
            resources["limits"] = limits
        if resources:
            result["resources"] = resources

        # 处理卷挂载
        if hasattr(self, "volumes") and "volumes" in self.volumes:
            volume_mounts = []
            for host_path, mount_info in self.volumes["volumes"].items():
                mount = {
                    "name": self._derive_volume_name(host_path),  # 从host_path派生名称
                    "mountPath": mount_info["bind"],
                }
                if mount_info["mode"] == "ro":
                    mount["readOnly"] = True
                volume_mounts.append(mount)
            if volume_mounts:
                result["volumeMounts"] = volume_mounts

        return result

    def _derive_volume_name(self, host_path):
        """从主机路径派生卷名称"""
        # 简单方法：使用路径的最后一部分作为卷名
        import os

        base_name = os.path.basename(host_path)
        # 替换非法字符
        volume_name = base_name.replace(".", "-").replace("_", "-").lower()
        # 确保名称符合DNS子域名规则
        if not volume_name:
            return "volume"
        return volume_name
