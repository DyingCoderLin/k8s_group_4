import requests
import sys
import os
import pickle
import signal
import logging
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

        # 改进的心跳循环，增加异常处理和退避策略
        consecutive_failures = 0
        max_failures = 10  # 最大连续失败次数
        base_interval = 2  # 基础心跳间隔（秒）
        max_interval = 60  # 最大心跳间隔（秒）
        
        print("[INFO]开始心跳循环")
        
        while True:
            try:
                sleep(min(base_interval * (2 ** min(consecutive_failures, 5)), max_interval))
                
                uri = self.uri_config.PREFIX + self.uri_config.NODE_SPEC_URL.format(name=self.config.name)
                register_response = requests.put(uri, json=self.config.json, timeout=10)
                
                if register_response.status_code == 200:
                    if consecutive_failures > 0:
                        print(f"[INFO]心跳恢复正常，重置失败计数")
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    print(f"[WARNING]心跳失败 {consecutive_failures}/{max_failures}: HTTP {register_response.status_code}")
                    
            except requests.exceptions.RequestException as e:
                consecutive_failures += 1
                print(f"[WARNING]心跳网络异常 {consecutive_failures}/{max_failures}: {e}")
                
            except Exception as e:
                consecutive_failures += 1
                print(f"[ERROR]心跳发生未知错误 {consecutive_failures}/{max_failures}: {e}")
            
            # 如果连续失败次数过多，退出循环
            if consecutive_failures >= max_failures:
                print(f"[ERROR]连续心跳失败 {max_failures} 次，节点退出以避免API Server过载")
                break

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
    import argparse
    import logging
    import yaml
    from pkg.config.globalConfig import GlobalConfig

    # 命令行参数解析
    parser = argparse.ArgumentParser(description="Kubernetes Node with integrated ServiceProxy")
    parser.add_argument("--node-config", help="Node configuration file path")
    parser.add_argument("--node-name", help="Node name override")
    args = parser.parse_args()

    print("[INFO]Starting Node with integrated ServiceProxy.")
    
    # 设置日志
    log_file = os.environ.get('NODE_LOG_FILE')
    if log_file:
        print(f"[INFO]Node logs will be written to: {log_file}")
        
        # 配置logging，同时输出到控制台和文件
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, mode='a'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        # 配置requests库的日志级别，减少噪音
        logging.getLogger("requests").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
    
    # 确定配置文件路径
    if args.node_config:
        config_file = args.node_config
        if not os.path.isabs(config_file):
            config_file = os.path.join(os.getcwd(), config_file)
    else:
        # 使用默认配置
        global_config = GlobalConfig()
        config_file = os.path.join(global_config.TEST_FILE_PATH, "node-1.yaml")
    
    print(f"[INFO]使用配置文件: {config_file}")
    
    try:
        with open(config_file, "r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
        
        node_config = NodeConfig(data)
        
        # 如果提供了节点名称参数，覆盖配置文件中的名称
        if args.node_name:
            node_config.name = args.node_name
        
        print(f"[INFO]节点名称: {node_config.name}")
        print(f"[INFO]ServiceProxy将以节点名称 '{node_config.name}' 启动")
        
        # 重定向标准输出到日志文件（如果指定）
        if log_file:
            # 确保日志文件存在
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            
            # 由于在daemon环境中，可能没有适当的标准输出，
            # 我们需要处理sys.stdout.reconfigure()的兼容性问题
            try:
                if hasattr(sys.stdout, 'reconfigure'):
                    sys.stdout.reconfigure(encoding='utf-8')
                if hasattr(sys.stderr, 'reconfigure'):
                    sys.stderr.reconfigure(encoding='utf-8')
            except (AttributeError, OSError):
                # 在某些环境中（如StringIO），reconfigure方法可能不存在或失败
                pass
        
        # 创建并启动节点
        node = Node(node_config, URIConfig())
        node.run()
        
    except FileNotFoundError:
        print(f"[ERROR]配置文件未找到: {config_file}")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"[ERROR]配置文件YAML格式错误: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR]启动节点时发生错误: {e}")
        sys.exit(1)
