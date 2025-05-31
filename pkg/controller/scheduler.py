import json
import pickle
import random
from time import sleep
from confluent_kafka import Consumer, KafkaError
from pkg.apiServer.apiClient import ApiClient
from abc import ABC, abstractmethod


class Strategy(ABC):
    """抽象策略基类，所有方法需由子类实现"""

    @abstractmethod
    def schedule(self, pod):
        """从列表中选中一个元素（需子类实现具体策略）"""
        raise NotImplementedError("Subclasses must implement select()")

    @abstractmethod
    def update(self, new_list):
        """更新策略内部状态（如轮询指针或权重）"""
        raise NotImplementedError("Subclasses must implement update()")


class RandomSelector(Strategy):
    def __init__(self):
        self.list = []
        self.last_selected = None

    def update(self, new_list):
        """更新内部列表（与RoundRobin逻辑一致）"""
        # 保留原有顺序但同步新增/删除的元素
        self.list = [item for item in self.list if item in new_list]
        for item in new_list:
            if item not in self.list:
                self.list.append(item)

    def schedule(self, pod):
        """随机选择一个元素"""
        if not self.list:
            return None

        # 如果列表只有一个元素，直接返回
        if len(self.list) == 1:
            return self.list[0]

        # 随机选择（避免连续重复）
        if self.last_selected is not None:
            candidates = [item for item in self.list if item != self.last_selected]
            selected = random.choice(candidates) if candidates else self.last_selected

        self.last_selected = selected
        return selected

    def __str__(self):
        return f"RandomSelector(last={self.last_selected}, list={self.list})"


class RoundRobin(Strategy):
    def __init__(self):
        self.list = []
        self.ptr = 0  # 当前指针位置

    def update(self, new_list):
        """更新内部列表，保持原有顺序但同步新增/删除的元素"""
        # 删除不存在于新列表中的元素
        self.list = [item for item in self.list if item in new_list]

        # 添加新元素（保持在新列表中的顺序）
        for item in new_list:
            if item not in self.list:
                self.list.append(item)

        # 确保指针不越界
        if self.ptr >= len(self.list):
            self.ptr = 0

    def schedule(self, pod):
        """获取下一个轮询元素"""
        if len(self.list) == 0:
            return None

        selected = self.list[self.ptr]
        self.ptr = (self.ptr + 1) % len(self.list)  # 环形递增
        return selected

    def __str__(self):
        return f"RoundRobin(current={self.list[self.ptr] if self.list else None}, list={self.list})"


class FilterSelect(Strategy):
    def __init__(self, base_strategy=RandomSelector()):
        self.base_startegy = base_strategy
        self.list = []

    def update(self, new_list):
        self.list = [item for item in self.list if item in new_list]

        for item in new_list:
            if item not in self.list:
                self.list.append(item)

    def schedule(self, pod):
        """
        目前只支持设备选择
        """

        def check_taints(taints, kvs):
            for k, v in kvs:
                has_key = False
                for taint in taints:
                    if taint["key"] == k:
                        has_key = True
                        if taint["value"] != v:
                            return False
                if has_key == False:
                    return False
            return True

        filter_list = self.list

        # 根据node的污点标签筛选。对于给定的key，value必须满足
        filter_list = [
            node
            for node in filter_list
            if check_taints(node.taints, pod.node_selector.items())
        ]

        self.base_strategy.update(filter_list)
        return self.base_strategy.schedule(pod)


class Scheduler:
    def __init__(self, uri_config, strategy=RoundRobin()):
        self.uri_config = uri_config
        self.api_client = ApiClient(self.uri_config.HOST, self.uri_config.PORT)
        self.strategy = strategy
        self.kafka_server = None
        self.kafka_topic = None

    def run(self):
        # 注册到apiServer
        response = self.api_client.post(self.uri_config.SCHEDULER_URL, {})

        if response:
            self.kafka_server = response["kafka_server"]
            self.kafka_topic = response["kafka_topic"]
            print(f"[INFO]Successfully register to ApiServer.")
        else:
            print(f"[ERROR]Cannot register to ApiServer {response}")
            return

        try:
            self.consumer = Consumer(
                {
                    "bootstrap.servers": self.kafka_server,
                    "group.id": "1",
                    "auto.offset.reset": "latest",
                    "enable.auto.commit": True,
                    "debug": "consumer",
                }
            )
            self.consumer.subscribe([self.kafka_topic])
            print(
                f"[INFO]Subscribe kafka({self.kafka_server}) topic {self.kafka_topic}"
            )
            sleep(5)
            print(f"[INFO]Scheduler init succuess.")
        except Exception as e:
            print(f"[ERROR]Cannot subscribe kafka: {e}")
            return

        # 轮询执行调度
        while True:
            msg = self.consumer.poll(timeout=1.0)

            if msg is not None:
                if not msg.error():
                    print(f"[INFO]Receive an message")
                    pod_config = pickle.loads(msg.value())

                    # 获取node信息
                    node_response = self.api_client.get(self.uri_config.NODES_URL)
                    if node_response is None:
                        print("[ERROR]Get node info failed.")
                        continue

                    # 执行调度
                    self.strategy.update(node_response)
                    select_node = self.strategy.schedule(pod_config)
                    self.consumer.commit(asynchronous=False)
                    if select_node is None:
                        print(
                            f"[ERROR]Schedule is impossible: no suitable nodes to choose from"
                        )
                        return

                    # 向apiServer发送调度结果
                    uri = self.uri_config.SCHEDULER_POD_URL.format(
                        namespace=pod_config.namespace,
                        name=pod_config.name,
                        node_name=select_node.name,
                    )
                    response = self.api_client.put(uri, {})
                    print(
                        f"[INFO]Scheduled Pod {pod_config.namespace}:{pod_config.name} to Node {select_node.name}"
                    )
                else:
                    print(f"[ERROR]Message error")


if __name__ == "__main__":
    from pkg.config.uriConfig import URIConfig

    scheduler = Scheduler(URIConfig)
    scheduler.run()
