from pkg.apiObject.hpa import HPAController
from pkg.config.uriConfig import URIConfig
from pkg.apiServer.apiClient import ApiClient

def main():
    # 创建并启动HPA控制器管理器
    controller = HPAController(ApiClient(), URIConfig())
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