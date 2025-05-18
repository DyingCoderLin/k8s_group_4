from pkg.controller.hpaController import HPAController
from pkg.config.uriConfig import URIConfig

def main():
    """启动HPA控制器"""
    # 创建并启动控制器
    controller = HPAController(URIConfig())
    controller.start()
    
    try:
        # 保持程序运行
        import time
        while True:
            print("[INFO]HPA controller running...")
            time.sleep(60)
    except KeyboardInterrupt:
        print("[INFO]Stopping HPA controller...")
        controller.stop()
        print("[INFO]HPA controller stopped")

if __name__ == "__main__":
    print("[INFO]Starting HPA controller...")
    main()