#!/usr/bin/env python3
"""
Service Controller 启动器
负责启动和管理Service控制器
"""

import sys
import os
import time
import signal
import logging

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.insert(0, project_root)

from pkg.controller.serviceController import ServiceController
from pkg.config.uriConfig import URIConfig
from pkg.config.etcdConfig import EtcdConfig
from pkg.apiServer.etcd import Etcd


class ServiceStarter:
    """Service控制器启动器"""

    def __init__(self):
        self.service_controller = None
        self.etcd_client = None
        self.running = False

        # 设置日志
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler("logs/service_controller.log"),
                logging.StreamHandler(),
            ],
        )
        self.logger = logging.getLogger(__name__)

    def setup_signal_handlers(self):
        """设置信号处理器"""

        def signal_handler(signum, frame):
            self.logger.info(f"接收到信号 {signum}，正在关闭Service控制器...")
            self.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def start(self):
        """启动Service控制器"""
        try:
            self.logger.info("启动Service控制器...")

            # 初始化Service控制器
            uri_config = URIConfig()
            self.service_controller = ServiceController(
                etcd_client=self.etcd_client,
                uri_config=uri_config,
            )

            # 启动控制器
            self.service_controller.start()
            self.running = True

            # 保持运行
            while self.running:
                time.sleep(1)

        except KeyboardInterrupt:
            self.logger.info("接收到键盘中断，正在停止...")
            self.stop()
        except Exception as e:
            self.logger.error(f"Service控制器启动失败: {e}")
            raise

    def stop(self):
        """停止Service控制器"""
        self.running = False
        if self.service_controller:
            try:
                self.service_controller.stop()
                self.logger.info("Service控制器已停止")
            except Exception as e:
                self.logger.error(f"停止Service控制器时出错: {e}")


def main():
    """主函数"""
    # 创建日志目录
    os.makedirs("logs", exist_ok=True)

    # 启动Service控制器
    starter = ServiceStarter()
    starter.setup_signal_handlers()

    try:
        starter.start()
    except Exception as e:
        print(f"[ERROR] Service控制器启动失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
