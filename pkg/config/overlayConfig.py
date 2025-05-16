class OverlayConfig():
    NAME = "my_overlay_network"
    MAX_SUBNET_NUM = 5

    # 因为我们使用python不能使用go的flannel插件，所以我们用docker的overlay网络来实现CNI功能
    # 由于overlay网络一旦创建不能动态添加子网，所以我们一开始固定分配$MAX_SUBNET_NUM$个子网ip
    # 因此最多只允许$MAX_SUBNET_NUM$个Node接入
    SUBNETS = [{"Subnet": f"192.168.{i}.0/24", "Gateway": f"192.168.{i}.1"} for i in range(MAX_SUBNET_NUM)]

    def dockerapi_args(self):
        return {
            'name': self.NAME,
            'driver': "overlay",
            # 'scope': "swarm", # docker.errors.InvalidVersion: scope is not supported in API version < 1.30
            'ipam': {
                "Driver": "default",
                "Config": self.SUBNETS
            }
        }