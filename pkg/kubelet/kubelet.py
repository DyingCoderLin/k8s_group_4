import json
import logging
import sys
import os
from time import sleep
from confluent_kafka import Consumer, KafkaError
from threading import Thread

from pkg.apiObject.pod import Pod, STATUS
from pkg.config.podConfig import PodConfig
from pkg.apiServer.apiClient import ApiClient

# 配置日志记录
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),  # 输出到标准输出
    ]
)
logger = logging.getLogger('Kubelet')

class Kubelet:
    """
    kubelet可以细分为Cri、PLEG等组件，分别用于容器管理和容器状态监控等。
    我认为这样细分会增加阅读难度，所以我将这些组件的功能全部实现在同一个循环中
    """

    def __init__(self, config, uri_config):
        self.config = config
        self.uri_config = uri_config
        self.api_client = ApiClient(self.uri_config.HOST, self.uri_config.PORT)
        self.pods_cache = []
        self.pods_status = []
        # 三个状态：apiserver存储的状态，kubelet存储的状态，Pod本身的状态。
        # 可以保证：如果http请求正常送达，则前两者保持一致。在kubelet每一轮loop后短时间内后两者一致

        self.consumer = Consumer(config.consumer_config())
        self.consumer.subscribe([config.topic])
        print(f"[INFO]Subscribe kafka({config.kafka_server}) topic {config.topic}")

    def apply(self, pod_config_list):
        self.pods_cache = [Pod(pod_config) for pod_config in pod_config_list]
        self.pods_status = [STATUS.CREATING] * len(self.pods_cache)

    def run(self):
        while True:
            # 接收Pod修改请求
            msg = self.consumer.poll(timeout=1.0)
            if msg is not None:
                if not msg.error():
                    print(
                        f"[INFO]Receive an message with key = {msg.key().decode('utf-8')}"
                    )
                    self.update_pod(
                        msg.key().decode("utf-8"),
                        json.loads(msg.value().decode("utf-8")),
                    )
                    self.consumer.commit(asynchronous=False)
                else:
                    print(f"[ERROR]Message error")

            # 重启异常退出的容器
            for pod in self.pods_cache:
                pod.restart_crash()

            # 监控状态变化并生成PLEG事件
            for i, pod in enumerate(self.pods_cache):
                status = pod.refresh_status()
                if status != self.pods_status[i]:
                    self.pods_status[i] = status
                    uri = self.uri_config.POD_SPEC_STATUS_URL.format(
                        namespace=pod.config.namespace, name=pod.config.name
                    )
                    self.api_client.put(uri, {"status": status})

    def update_pod(self, type, data):
        if type in ["ADD", "UPDATE", "DELETE", "GET"]:
            print(f"[INFO]Kubelet {type} pod with data: {data}")
        else:
            print(f"[ERROR]Unknown kubelet operation {type}.")

        # ADD和UPDATE中，status缓存都设置为CREATING，这与apiserver一致。后续通过PLEG事件修改状态
        if type == "ADD":
            config = PodConfig(data)
            # 从kubelet缓存的Pod信息检查命名是否冲突
            for pod in self.pods_cache:
                if (
                    pod.config.namespace == config.namespace
                    and pod.config.name == config.name
                ):
                    print(
                        f'[ERROR]Pod name "{config.namespace}:{config.name}" already exists'
                    )
                    return
            try:  # 尝试创建docker，可能出现名称重复、客户端未连接等容器运行时错误
                new_pod = Pod(config,self.api_client,self.uri_config)
            except Exception as e:
                print(f"[ERROR]Docker create fail: {e}")
                return

            self.pods_cache.append(new_pod)
            self.pods_status.append(STATUS.CREATING)
            print(f'[INFO]Kubelet create pod "{config.namespace}:{config.name}".')

        elif type == "UPDATE":
            config = PodConfig(data)
            # lcl: update又是在做什么？
            # wcc: 别急
            for i, pod in enumerate(self.pods_cache):
                if (
                    pod.config.namespace == config.namespace
                    and pod.config.name == config.name
                ):
                    try:  # 在旧容器删除过程中出现了容器运行时错误
                        self.pods_cache[i].remove()
                        del self.pods_cache[i]
                        del self.pods_status[i]
                    except Exception as e:
                        print(f"[ERROR]Docker rm fail: {e}")
                        return
                    try:  # 在新容器创建过程中出现容器运行时错误
                        self.pods_cache.append(Pod(config))
                        self.pods_status.append(STATUS.CREATING)
                    except Exception as e:
                        print(f"[ERROR]Docker create fail: {e}")
                        return
                    print(f'[INFO]Pod "{config.namespace}:{config.name}" updated.')
                    return
            # 从kubelet的缓存信息中无法找到对应的Pod
            print(f'[WARNING]Pod "{config.namespace}:{config.name}" not found.')

        elif type == "DELETE":
            namespace, name = data["namespace"], data["name"]
            # lcl: delete逻辑完全没有实现，需要实现
            # wcc: 别急
            for i, pod in enumerate(self.pods_cache):
                if pod.config.namespace == namespace and pod.config.name == name:
                    try:  # 在旧容器删除过程中出现了容器运行时错误
                        self.pods_cache[i].remove()
                        del self.pods_cache[i]
                        del self.pods_status[i]
                    except Exception as e:
                        print(f"[ERROR]Docker rm fail: {e}")
                        return
                    print(f'[INFO]Pod "{namespace}:{name}" deleted.')
                    return
            # 从kubelet的缓存信息中无法找到对应的Pod
            print(f'[WARNING]Pod "{namespace}:{name}" not found.')


if __name__ == "__main__":
    print("[INFO]Testing kubelet.")
    import yaml
    from pkg.apiObject.pod import Pod
    from pkg.config.kubeletConfig import KubeletConfig
    from pkg.config.globalConfig import GlobalConfig
    import os

    kubelet_config = KubeletConfig()
    kubelet = Kubelet(kubelet_config)
    global_config = GlobalConfig()
    test_yaml = os.path.join(global_config.TEST_FILE_PATH, "pod-3.yaml")

    with open(test_yaml, "r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    print(f"data = {data}")
    podConfig = PodConfig(data)
    # pod = Pod(podConfig)
    # kubelet.pods_cache.append(pod)

    print("[INFO]start kubelet(infinite retry)")
    kubelet.run()
