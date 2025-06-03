import requests
import sys
import os
import pickle
import yaml
from threading import Thread
from time import sleep

from pkg.config.dnsConfig import DNSConfig
from pkg.config.uriConfig import URIConfig
from pkg.config.globalConfig import GlobalConfig


class STATUS:
    PENDING = "PENDING"  # DNS 配置初始状态，等待注册
    ACTIVE = "ACTIVE"    # DNS 配置已成功注册并运行
    FAILED = "FAILED"    # DNS 配置注册或运行失败


class DNS:
    def __init__(self, dns_config: DNSConfig, uri_config: URIConfig = None):
        """初始化 DNS 对象，设置配置和 API 通信参数"""
        self.config = dns_config  # DNS 配置对象，包含域名、路径等信息
        self.uri_config = uri_config if uri_config else URIConfig()  # API 服务器 URI 配置，默认为 URIConfig()

        # 设置标准输出和错误输出的无缓冲模式，确保日志实时写入
        sys.stdout.reconfigure(write_through=True)
        sys.stderr.reconfigure(write_through=True)

    def run(self):
        """将 DNS 配置注册到 API 服务器并维护其状态"""
        # 构造注册 DNS 的 API 地址，包含命名空间和 DNS 名称
        uri = self.uri_config.PREFIX + self.uri_config.DNS_SPEC_URL.format(
            namespace=self.config.namespace, name=self.config.name
        )
        # 通过 POST 请求向 API 服务器注册 DNS 配置
        register_response = requests.post(uri, json=self.config.to_dict())
        if register_response.status_code != 200:
            # 注册失败，记录错误并设置状态为 FAILED
            print(f"[ERROR] 无法注册 DNS 到 ApiServer，状态码：{register_response.status_code}")
            self.config.status = STATUS.FAILED
            return
        # 注册成功，设置状态为 ACTIVE
        self.config.status = STATUS.ACTIVE
        print(f"[INFO] 成功注册 DNS {self.config.name} 到 ApiServer。")

        # 获取与当前命名空间相关的服务信息，确保引用的服务存在
        uri = self.uri_config.PREFIX + self.uri_config.SERVICE_URL.format(
            namespace=self.config.namespace
        )
        service_response = requests.get(uri)
        if service_response.status_code != 200:
            # 获取服务失败，记录错误并设置状态为 FAILED
            print(f"[ERROR] 无法获取命名空间 {self.config.namespace} 的服务信息")
            self.config.status = STATUS.FAILED
            return
        services = pickle.loads(service_response.content)
        print(f"[INFO] 为 DNS {self.config.name} 获取到 {len(services)} 个服务。")

        # 启动心跳线程，定期更新 DNS 状态
        Thread(target=self._heartbeat).start()

    def _heartbeat(self):
        """定期向 API 服务器发送心跳，更新 DNS 状态"""
        while self.config.status == STATUS.ACTIVE:
            sleep(5)  # 每 5 秒发送一次心跳
            uri = self.uri_config.PREFIX + self.uri_config.DNS_SPEC_URL.format(
                namespace=self.config.namespace, name=self.config.name
            )
            # 通过 PUT 请求更新 DNS 配置状态
            update_response = requests.put(uri, json=self.config.to_dict())
            if update_response.status_code != 200:
                # 心跳发送失败，记录错误并设置状态为 FAILED
                print(f"[ERROR] DNS {self.config.name} 心跳发送失败")
                self.config.status = STATUS.FAILED
                break
            print(f"[INFO] DNS {self.config.name} 心跳发送成功。")
        if self.config.status != STATUS.ACTIVE:
            print(f"[INFO] DNS {self.config.name} 因状态为 {self.config.status} 停止心跳")

if __name__ == "__main__":
    print("[INFO] Testing DNS.")

    # 设置标准输出无缓冲，确保日志实时写入
    sys.stdout.reconfigure(write_through=True)
    sys.stderr.reconfigure(write_through=True)

    # 记录日志文件路径
    log_file = os.environ.get('DNS_LOG_FILE')
    if log_file:
        print(f"[INFO] DNS logs will be written to: {log_file}")

    # Load test DNS configuration from YAML
    global_config = GlobalConfig()
    file_yaml = "dns-test.yaml"
    test_yaml = os.path.join(global_config.TEST_FILE_PATH, file_yaml)

    print(f"[INFO]使用{file_yaml}作为测试配置，测试Node的创建和删除。目前没有使用volume绑定")
    print(f"[INFO]请求地址: {test_yaml}")

    with open(test_yaml, "r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    dns_config = DNSConfig(data)
    dns = DNS(dns_config, URIConfig())
    dns.run()

