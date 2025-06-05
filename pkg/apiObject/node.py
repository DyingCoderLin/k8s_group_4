import requests
import sys
import os
import pickle
from threading import Thread
from time import sleep

from pkg.kubelet.kubelet import Kubelet
from pkg.config.kubeletConfig import KubeletConfig
from pkg.config.uriConfig import URIConfig
from pkg.config.nodeConfig import NodeConfig


class STATUS:
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"


class Node:
    def __init__(self, node_config: NodeConfig, uri_config: URIConfig = None):
        self.config = node_config
        self.uri_config = uri_config

        # 设置标准输出无缓冲，确保日志实时写入
        sys.stdout.reconfigure(write_through=True)
        sys.stderr.reconfigure(write_through=True)

    def run(self):
        uri = self.uri_config.PREFIX + self.uri_config.NODE_SPEC_URL.format(
            name=self.config.name
        )
        register_response = requests.post(uri, json=self.config.json)
        if register_response.status_code != 200:
            print(
                f"[ERROR]Cannot register to ApiServer with code {register_response.status_code}"
            )
            return
        self.config.status = STATUS.ONLINE
        res_json = register_response.json()

        kubelet_config = KubeletConfig(**self.config.kubelet_config_args(), **res_json)
        self.kubelet = Kubelet(kubelet_config, self.uri_config)
        print(f"[INFO]Successfully register to ApiServer.")

        # 从apiServer索要持久化的Pod状态信息，并运行kubelet
        uri = self.uri_config.PREFIX + self.uri_config.NODE_ALL_PODS_URL.format(
            name=self.config.name
        )
        register_response = requests.get(uri)
        if register_response.status_code != 200:
            print(f"[ERROR]Cannot fetch Pod status from apiServer")
            return
        res = pickle.loads(register_response.content)
        self.kubelet.apply(res)
        Thread(target=self.kubelet.run).start()

        # 定期发送心跳
        while True:
            sleep(2)
            uri = self.uri_config.PREFIX + self.uri_config.NODE_SPEC_URL.format(
                name=self.config.name
            )
            register_response = requests.put(uri, json=self.config.json)


if __name__ == "__main__":
    print("[INFO]Testing Node.")
    # 设置标准输出无缓冲，确保日志实时写入
    sys.stdout.reconfigure(write_through=True)
    sys.stderr.reconfigure(write_through=True)

    # 记录日志文件路径
    log_file = os.environ.get("NODE_LOG_FILE")
    if log_file:
        print(f"[INFO]Node logs will be written to: {log_file}")

    import yaml
    from pkg.config.globalConfig import GlobalConfig

    global_config = GlobalConfig()
    file_yaml = "node-1.yaml"
    test_yaml = os.path.join(global_config.TEST_FILE_PATH, file_yaml)
    print(
        f"[INFO]使用{file_yaml}作为测试配置，测试Node的创建和删除。目前没有使用volume绑定"
    )
    print(f"[INFO]请求地址: {test_yaml}")
    with open(test_yaml, "r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    node_config = NodeConfig(data)
    node = Node(node_config, URIConfig)
    node.run()
