import requests
import sys
import os
import pickle
import yaml
from threading import Thread
from time import sleep
from flask import Flask, request, redirect

from pkg.config.dnsConfig import DNSConfig
from pkg.config.uriConfig import URIConfig
from pkg.config.globalConfig import GlobalConfig
from pkg.config.etcdConfig import EtcdConfig
from pkg.apiServer.etcd import Etcd


class STATUS:
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    FAILED = "FAILED"


class DNS:
    def __init__(self, dns_config: DNSConfig, uri_config: URIConfig = None, etcd_config: EtcdConfig = None):
        """初始化 DNS 对象，设置配置、API 和 etcd 参数"""
        self.config = dns_config
        self.uri_config = uri_config if uri_config else URIConfig()
        self.etcd_config = etcd_config if etcd_config else EtcdConfig()
        self.etcd = Etcd(host=self.etcd_config.HOST, port=self.etcd_config.PORT)
        self.config.etcd = self.etcd  # 将 etcd 客户端注入 DNSConfig

        # 初始化 Flask 应用用于处理 DNS 请求转发
        self.app = Flask(__name__)
        self.bind_routes()

        # 设置标准输出和错误输出的无缓冲模式
        sys.stdout.reconfigure(write_through=True)
        sys.stderr.reconfigure(write_through=True)

    def bind_routes(self):
        """绑定 Flask 路由用于处理 DNS 请求"""
        @self.app.route("/<path:path>", methods=["GET", "POST", "PUT", "DELETE"])
        def forward_request(path):
            """将请求转发到对应的 Service"""
            service_mapping = self.config.get_service_mapping()
            target = service_mapping.get(f"/{path}")
            if not target:
                return {"error": f"路径 /{path} 未找到对应的 Service"}, 404

            # 转发请求到 Service IP:Port
            method = request.method.lower()
            target_url = f"http://{target}{request.full_path}"
            try:
                response = getattr(requests, method)(
                    target_url,
                    json=request.get_json(silent=True),
                    params=request.args,
                    headers=request.headers
                )
                return response.content, response.status_code, response.headers.items()
            except requests.RequestException as e:
                return {"error": f"转发请求失败: {str(e)}"}, 500

    def run(self):
        """注册 DNS 配置并启动代理服务"""
        # 验证 DNS 配置
        try:
            self.config.validate()
        except ValueError as e:
            print(f"[ERROR] DNS 配置验证失败: {str(e)}")
            self.config.status = STATUS.FAILED
            return

        # 注册 DNS 到 API 服务器
        uri = self.uri_config.PREFIX + self.uri_config.DNS_SPEC_URL.format(
            namespace=self.config.namespace, name=self.config.name
        )
        register_response = requests.post(uri, json=self.config.to_dict())
        if register_response.status_code != 200:
            print(f"[ERROR] 无法注册 DNS 到 ApiServer，状态码：{register_response.status_code}")
            self.config.status = STATUS.FAILED
            return
        self.config.status = STATUS.ACTIVE
        print(f"[INFO] 成功注册 DNS {self.config.name} 到 ApiServer。")

        # 存储 DNS 配置到 etcd
        dns_key = self.etcd_config.DNS_SPEC_KEY.format(namespace=self.config.namespace, name=self.config.name)
        self.etcd.put(dns_key, pickle.dumps(self.config.to_dict()))

        # 启动心跳线程
        Thread(target=self._heartbeat).start()

        # 启动 Flask 代理服务，监听 80 端口
        Thread(target=lambda: self.app.run(host="0.0.0.0", port=80)).start()

    def _heartbeat(self):
        """定期更新 DNS 状态"""
        while self.config.status == STATUS.ACTIVE:
            sleep(5)
            uri = self.uri_config.PREFIX + self.uri_config.DNS_SPEC_URL.format(
                namespace=self.config.namespace, name=self.config.name
            )
            # 检查 Service 是否仍然有效
            try:
                self.config.validate()
                update_response = requests.put(uri, json=self.config.to_dict())
                if update_response.status_code != 200:
                    print(f"[ERROR] DNS {self.config.name} 心跳发送失败")
                    self.config.status = STATUS.FAILED
                    break
                # 更新 etcd 中的 DNS 配置
                dns_key = self.etcd_config.DNS_SPEC_KEY.format(namespace=self.config.namespace, name=self.config.name)
                self.etcd.put(dns_key, pickle.dumps(self.config.to_dict()))
                print(f"[INFO] DNS {self.config.name} 心跳发送成功")
            except ValueError as e:
                print(f"[ERROR] DNS 验证失败: {str(e)}")
                self.config.status = STATUS.FAILED
                break
        if self.config.status != STATUS.ACTIVE:
            print(f"[INFO] DNS {self.config.name} 因状态为 {self.config.status} 停止心跳")


if __name__ == "__main__":
    print("[INFO] 测试 DNS 功能")
    sys.stdout.reconfigure(write_through=True)
    sys.stderr.reconfigure(write_through=True)

    log_file = os.environ.get('DNS_LOG_FILE')
    if log_file:
        print(f"[INFO] DNS 日志将写入：{log_file}")

    global_config = GlobalConfig()
    file_yaml = "dns-test.yaml"
    test_yaml = os.path.join(global_config.TEST_FILE_PATH, file_yaml)
    print(f"[INFO] 使用 {file_yaml} 作为 DNS 测试配置文件")
    print(f"[INFO] 请求路径：{test_yaml}")

    with open(test_yaml, "r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    dns_config = DNSConfig(data)
    dns = DNS(dns_config, URIConfig(), EtcdConfig())
    dns.run()
