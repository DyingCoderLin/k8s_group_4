#!/usr/bin/env python3

import sys
import os
import signal
import time

# 添加项目根目录到 Python 路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pkg.controller.pvController import PVController
from pkg.config.etcdConfig import EtcdConfig

def signal_handler(signum, frame):
    """信号处理器"""
    print(f"\n[INFO] Received signal {signum}, shutting down PV Controller...")
    if controller:
        controller.stop()
    sys.exit(0)

def main():
    """主函数"""
    global controller
    
    print("[INFO] Starting PV Controller...")
    
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # 创建并启动控制器
        controller = PVController(EtcdConfig)
        controller.start()
        
        print("[INFO] PV Controller is running. Press Ctrl+C to stop.")
        
        # 保持运行
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n[INFO] Keyboard interrupt received, shutting down...")
    except Exception as e:
        print(f"[ERROR] SimplePV Controller error: {e}")
    finally:
        if controller:
            controller.stop()

if __name__ == "__main__":
    controller = None
    main()
