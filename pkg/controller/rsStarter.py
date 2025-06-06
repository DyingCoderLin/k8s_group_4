from pkg.controller.replicaSetController import ReplicaSetController
from pkg.config.uriConfig import URIConfig
import signal
import sys
import time


def main():
    # 创建并启动控制器
    controller = ReplicaSetController(URIConfig())
    controller.start()

    # 设置信号处理
    def signal_handler(sig, frame):
        print("\n[INFO]Shutting down...")
        controller.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 保持程序运行
    print("[INFO]Controller is running. Press CTRL+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        controller.stop()


if __name__ == "__main__":
    main()
