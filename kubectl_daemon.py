import os
import sys
import json
import socket
import signal
import threading
import logging
import time
import argparse
from typing import Dict, Any
from pathlib import Path

# 添加项目根目录到 Python 路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from kubectl import KubectlClient

class KubectlDaemon:
    def __init__(self, socket_path: str = "/tmp/kubectl_daemon.sock"):
        self.socket_path = socket_path
        self.running = False
        self.server_socket = None
        self.logger = self._setup_logging()
        
        try:
            self.kubectl = KubectlClient()
            self.logger.info("kubectl client initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize kubectl client: {e}")
            raise
        
    def _setup_logging(self):
        """设置日志记录"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('/tmp/kubectl_daemon.log'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        return logging.getLogger('kubectl_daemon')
    
    def _cleanup_socket(self):
        """清理套接字文件"""
        try:
            if os.path.exists(self.socket_path):
                os.unlink(self.socket_path)
        except OSError as e:
            self.logger.error(f"Failed to cleanup socket: {e}")
    
    def _signal_handler(self, signum, frame):
        """信号处理器"""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.stop()
    
    def _execute_kubectl_command(self, args):
        """执行kubectl命令"""
        import io
        from contextlib import redirect_stdout, redirect_stderr
        
        # 重定向输出
        output = io.StringIO()
        error_output = io.StringIO()
        
        try:
            with redirect_stdout(output), redirect_stderr(error_output):
                # 模拟命令行参数
                sys.argv = ['kubectl'] + args
                
                # 导入并执行main函数
                from kubectl import main
                main()
            
            stdout_content = output.getvalue()
            stderr_content = error_output.getvalue()
            
            if stderr_content:
                return {"error": stderr_content}
            else:
                return {"success": True, "output": stdout_content}
                
        except SystemExit as e:
            stdout_content = output.getvalue()
            if e.code == 0:
                return {"success": True, "output": stdout_content}
            else:
                stderr_content = error_output.getvalue()
                return {"error": stderr_content or "Command failed"}
        except Exception as e:
            return {"error": str(e)}
    
    def _handle_client(self, client_socket):
        """处理客户端连接"""
        try:
            # 接收命令数据
            data = client_socket.recv(8192).decode('utf-8')
            if not data:
                return
            
            command_data = json.loads(data)
            args = command_data.get('args', [])
            
            self.logger.info(f"Executing command: {args}")
            
            # 执行命令
            response = self._execute_kubectl_command(args)
            
            # 发送响应
            response_json = json.dumps(response)
            client_socket.send(response_json.encode('utf-8'))
            
        except Exception as e:
            self.logger.error(f"Error handling client: {e}")
            error_response = {"error": str(e)}
            try:
                client_socket.send(json.dumps(error_response).encode('utf-8'))
            except:
                pass
        finally:
            client_socket.close()
    
    def start(self):
        """启动守护进程"""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        self._cleanup_socket()
        
        self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        
        try:
            self.server_socket.bind(self.socket_path)
            self.server_socket.listen(5)
            self.running = True
            
            self.logger.info(f"kubectl daemon started, listening on {self.socket_path}")
            
            while self.running:
                try:
                    client_socket, _ = self.server_socket.accept()
                    client_thread = threading.Thread(
                        target=self._handle_client, 
                        args=(client_socket,)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                    
                except socket.error as e:
                    if self.running:
                        self.logger.error(f"Socket error: {e}")
                        break
                        
        except Exception as e:
            self.logger.error(f"Failed to start daemon: {e}")
        finally:
            self.stop()
    
    def stop(self):
        """停止守护进程"""
        self.running = False
        
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        
        self._cleanup_socket()
        self.logger.info("kubectl daemon stopped")


def main():
    parser = argparse.ArgumentParser(description="kubectl daemon")
    parser.add_argument("--socket", default="/tmp/kubectl_daemon.sock", 
                       help="Unix domain socket path")
    
    args = parser.parse_args()
    
    try:
        daemon = KubectlDaemon(socket_path=args.socket)
        daemon.start()
    except Exception as e:
        print(f"Failed to start kubectl daemon: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()