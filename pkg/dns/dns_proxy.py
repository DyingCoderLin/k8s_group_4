from confluent_kafka import Consumer
from docker import DockerClient
import pickle

class DNSProxy:
    def __init__(self, kafka_config, docker_config):
        # TODO 跟kafka相关的是不是要放在service里？
        self.kafka_config = kafka_config
        self.docker = DockerClient(**docker_config)
        self.consumer = Consumer({
            "bootstrap.servers": kafka_config.BOOTSTRAP_SERVER,
            "group.id": "dns-proxy",
            "auto.offset.reset": "latest"
        })
        self.consumer.subscribe([kafka_config.DNS_TOPIC])

    def generate_nginx_conf(self, dns_config):
        conf = "server {\n    listen 80;\n    server_name %s;\n" % dns_config["host"]
        for path in dns_config["paths"]:
            conf += "    location %s {\n        proxy_pass http://%s:%s;\n    }\n" % (
                path["path"], path["serviceName"], path["servicePort"]
            )
        conf += "}\n"
        return conf

    def apply_nginx_conf(self, conf):
        nginx_container = self.docker.containers.get("nginx-proxy")
        nginx_container.exec_run(f"echo '{conf}' > /etc/nginx/conf.d/dns.conf")
        nginx_container.exec_run("nginx -s reload")

    def run(self):
        while True:
            msg = self.consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                continue
            dns_data = pickle.loads(msg.value())
            if dns_data.get("action") == "delete":
                # 删除 Nginx 配置
                self.docker.containers.get("nginx-proxy").exec_run("rm /etc/nginx/conf.d/dns.conf")
                self.docker.containers.get("nginx-proxy").exec_run("nginx -s reload")
            else:
                # 创建或更新 Nginx 配置
                conf = self.generate_nginx_conf(dns_data)
                self.apply_nginx_conf(conf)
