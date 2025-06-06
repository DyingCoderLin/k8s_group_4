import requests
import sys
import os
import pickle
import signal
from threading import Thread
from time import sleep

from pkg.kubelet.kubelet import Kubelet
from pkg.config.kubeletConfig import KubeletConfig
from pkg.config.uriConfig import URIConfig
from pkg.config.nodeConfig import NodeConfig
from pkg.config.kafkaConfig import KafkaConfig
from pkg.network.serviceProxy import ServiceProxy


class STATUS:
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"


class Node:
    def __init__(self, node_config: NodeConfig, uri_config: URIConfig = None):
        self.config = node_config
        self.uri_config = uri_config
        self.service_proxy = None

    def run(self):
        uri = self.uri_config.PREFIX + self.uri_config.NODE_SPEC_URL.format(
            name=self.config.name
        )
        register_response = requests.post(uri, json=self.config.json)
        if register_response.status_code != 200:
            print(f"[ERROR]Cannot register to ApiServer with code {register_response.status_code}")
            return
        self.config.status = STATUS.ONLINE
        res_json = register_response.json()

        kubelet_config = KubeletConfig(**self.config.kubelet_config_args(), **res_json)
        self.kubelet = Kubelet(kubelet_config, self.uri_config)
        print(f"[INFO]Successfully register to ApiServer.")

        # 初始化并启动ServiceProxy
        self._start_service_proxy()

        # 从apiServer索要持久化的Pod状态信息，并运行kubelet
        uri = self.uri_config.PREFIX + self.uri_config.NODE_ALL_PODS_URL.format(name = self.config.name)
        register_response = requests.get(uri)
        if register_response.status_code != 200:
            print(f"[ERROR]Cannot fetch Pod status from apiServer")
            return
        res = pickle.loads(register_response.content)
        self.kubelet.apply(res)
        Thread(target=self.kubelet.run).start()

        # 设置信号处理器，确保优雅关闭
        try:
            if self._is_main_thread():
                signal.signal(signal.SIGINT, self._signal_handler)
                signal.signal(signal.SIGTERM, self._signal_handler)
                print("[INFO]信号处理器已设置")
            else:
                print("[INFO]非主线程环境，跳过信号处理器设置")
        except Exception as e:
            print(f"[WARNING]设置信号处理器失败: {e}")

        # 定期发送心跳
        while True:
            sleep(2)
            uri = self.uri_config.PREFIX + self.uri_config.NODE_SPEC_URL.format(name=self.config.name)
            register_response = requests.put(uri, json=self.config.json)

    def _start_service_proxy(self):
        """启动ServiceProxy守护进程"""
        try:
            # 配置Kafka连接信息
            kafka_config = {
                'bootstrap_servers': KafkaConfig.BOOTSTRAP_SERVER
            }
            
            # 创建ServiceProxy实例
            self.service_proxy = ServiceProxy(
                node_name=self.config.name,
                kafka_config=kafka_config
            )
            
            # 启动ServiceProxy守护进程
            self.service_proxy.start_daemon()
            print(f"[INFO]ServiceProxy已在节点 {self.config.name} 上启动")
            
        except Exception as e:
            print(f"[ERROR]启动ServiceProxy失败: {e}")
            # 即使ServiceProxy启动失败，节点仍然可以继续运行
    
    def _signal_handler(self, signum, frame):
        """信号处理器，用于优雅关闭"""
        print(f"\n[INFO]收到退出信号 {signum}，正在关闭节点...")
        
        # 停止ServiceProxy
        if self.service_proxy:
            try:
                self.service_proxy.stop_daemon()
                print("[INFO]ServiceProxy已停止")
            except Exception as e:
                print(f"[ERROR]停止ServiceProxy失败: {e}")
        
        # 这里可以添加其他清理逻辑
        sys.exit(0)
        
    def _is_main_thread(self):
        """检查是否在主线程中"""
        import threading
        return threading.current_thread() is threading.main_thread()


if __name__ == "__main__":
    print("[INFO]Starting Node with integrated ServiceProxy.")
    
    # 记录日志文件路径
    log_file = os.environ.get('NODE_LOG_FILE')
    if log_file:
        print(f"[INFO]Node logs will be written to: {log_file}")
        
    import yaml
    from pkg.config.globalConfig import GlobalConfig

    global_config = GlobalConfig()
    file_yaml = "node-1.yaml"
    test_yaml = os.path.join(global_config.TEST_FILE_PATH, file_yaml)
    print(
        f"[INFO]使用{file_yaml}作为测试配置，节点将自动启动ServiceProxy"
    )
    print(f"[INFO]请求地址: {test_yaml}")
    with open(test_yaml, "r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    node_config = NodeConfig(data)
    print(f"[INFO]节点名称: {node_config.name}")
    print(f"[INFO]ServiceProxy将以节点名称 '{node_config.name}' 启动")
    
    node = Node(node_config, URIConfig())
    node.run()
