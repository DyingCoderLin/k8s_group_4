class ContainerConfig:
    def __init__(self, volumes_map, arg_json, pod_security_context=None):
        self.name = arg_json.get("name")
        self.image = arg_json.get("image")
        self.command = arg_json.get("command", [])
        self.args = arg_json.get("args", [])

        # --- Port Mapping Handling ---
        self.port = dict()
        if arg_json.get("port") is not None:
            port = dict()
            for port_json in arg_json.get("port"):
                protocol = port_json.get("protocol", "tcp").lower()
                container_port = port_json.get('containerPort')
                host_port = port_json.get("hostPort", None)
                port[f"{container_port}/{protocol}"] = (host_port)
            self.port["ports"] = port 

        # --- Resource Limits Handling ---
        self.resources = dict()
        if arg_json.get("resources"):
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

        # --- Volume Mounts Handling --- 
        self.volumes = dict()
        if arg_json.get("volumeMounts") is not None:
            volumes = dict()
            for volume in arg_json.get("volumeMounts"):
                mode = "ro" if volume.get("readOnly", False) else "rw"
                volume_name = volume.get("name")

                # 安全获取主机路径，处理缺失卷的情况
                if volume_name in volumes_map:
                    host_path = volumes_map[volume_name]
                else:
                    print(f"[WARNING] ContainerConfig: volume '{volume_name}' not found in volumes_map. Available volumes: {list(volumes_map.keys())}")
                    # 使用默认路径作为后备
                    host_path = "/tmp"

                bind_path = volume.get("mountPath")

                volumes[host_path] = {"bind": bind_path, "mode": mode}
            self.volumes["volumes"] = volumes
            
        # --- Security Context Handling ---
        # 容器自身的 securityContext
        self.container_security_context = arg_json.get("securityContext", {})
        
        # 合并 Pod 级别和容器级别的 securityContext
        # 容器级别的设置会覆盖 Pod 级别的同名字段
        self.effective_security_context = {}
        if pod_security_context:
            self.effective_security_context.update(pod_security_context)
        self.effective_security_context.update(self.container_security_context)

        # 从合并后的 securityContext 中提取常用字段，方便直接访问
        self.run_as_user = self.effective_security_context.get("runAsUser")
        self.run_as_group = self.effective_security_context.get("runAsGroup")
        self.fs_group = self.effective_security_context.get("fsGroup")

        # 确保这些字段从 effective_security_context 中提取
        self.privileged = self.effective_security_context.get("privileged", False)
        self.read_only_root_filesystem = self.effective_security_context.get("readOnlyRootFilesystem", False)

        # 处理 capabilities
        capabilities = self.effective_security_context.get("capabilities", {})
        self.cap_add = capabilities.get("add", [])
        self.cap_drop = capabilities.get("drop", [])

        # 处理 supplementalGroups
        self.supplemental_groups = self.effective_security_context.get("supplementalGroups", [])

    def dockerapi_args(self):
        container_args = {
            'image': self.image,
            'name': self.name,
            'command': self.command + self.args,
            # **self.volumes,
            **self.port,
            **self.resources,
        }
        if 'cpu_quota' in container_args and isinstance(container_args['cpu_quota'], float):
            container_args['cpu_quota'] = int(container_args['cpu_quota'])
            
        # 添加 Security Context 相关的 Docker 参数 (直接作为顶层参数)
        # user 参数
        if self.run_as_user is not None:
            user_str = str(self.run_as_user)
            if self.run_as_group is not None:
                user_str += f":{self.run_as_group}"
            container_args['user'] = user_str
        elif self.run_as_group is not None:
            # 如果只设置了 runAsGroup 但没有 runAsUser，Docker 的 'user' 参数通常需要用户ID。
            # 为了简化，这里将 runAsGroup 作为附加组处理。
            if self.run_as_group not in self.supplemental_groups:
                self.supplemental_groups.append(self.run_as_group)
            print(f"[WARNING] Container '{self.name}': runAsGroup specified without runAsUser. Adding to supplemental groups. Docker 'user' parameter not set with only group.")

        if "volumes" in self.volumes: # 检查 self.volumes 中是否有 'volumes' 键
            container_args['volumes'] = self.volumes["volumes"]
            
        # privileged 参数
        container_args['privileged'] = self.privileged

        # read_only 参数 (对应 readOnlyRootFilesystem)
        container_args['read_only'] = self.read_only_root_filesystem

        # cap_add 参数
        if self.cap_add:
            container_args['cap_add'] = [c.upper() for c in self.cap_add] # Docker expects uppercase

        # cap_drop 参数
        if self.cap_drop:
            container_args['cap_drop'] = [c.upper() for c in self.cap_drop] # Docker expects uppercase

        # group_add 参数 (对应 supplementalGroups)
        if self.supplemental_groups:
            # Docker's group_add expects a list of group names or GIDs (as strings)
            container_args['group_add'] = [str(g) for g in self.supplemental_groups]

        # fsGroup: Kubernetes 的 fsGroup 主要影响挂载卷的权限。
        # Docker 没有直接的 'fsGroup' 参数用于 `run()`。
        # 我们将其存储在 self.fs_group 中，但不直接映射到 dockerapi_args。
        
        return container_args

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

        # 添加容器级别的 securityContext
        if self.container_security_context:
            result["securityContext"] = self.container_security_context

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

    def get_effective_security_context(self):
        """返回此容器最终生效的 security context。"""
        return self.effective_security_context

