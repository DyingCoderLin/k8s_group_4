import requests
import pickle
import json
from requests.exceptions import RequestException
import time
import socket
import sys


class ApiClient:
    """
    统一的API Client类，负责处理与API Server的通信
    只处理基本连接逻辑，具体URI路径由调用者提供
    """

    def __init__(self, host="localhost", port=5050, max_retries=3, retry_delay=2):
        """
        初始化ApiClient

        Args:
            host: API Server主机地址
            port: API Server端口
            max_retries: 最大重试次数
            retry_delay: 重试延迟(秒)
        """
        if sys.platform == "darwin":
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                # 连接到一个外部地址，不需要真正发送数据
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
                host = local_ip
            finally:
                s.close()

        self.base_url = f"http://{host}:{port}"
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.session = requests.Session()
        print(f"[INFO]API Client initialized with base URL: {self.base_url}")

    def _make_request(self, method, path, json_data=None, params=None):
        """
        发送HTTP请求并处理重试逻辑

        Args:
            method: HTTP方法 (GET, POST, PUT, DELETE等)
            path: API端点路径 (不含域名和端口)
            json_data: JSON数据 (POST和PUT请求)
            params: URL查询参数

        Returns:
            dict or list: 解析后的JSON响应
            None: 如果请求失败
        """
        url = f"{self.base_url}{path}"
        retries = 0

        while retries < self.max_retries:
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    json=json_data,
                    params=params,
                    timeout=(3.0, 10.0),  # (连接超时, 读取超时)
                )

                # 检查请求是否成功
                response.raise_for_status()

                # 尝试解析JSON响应
                if response.content:
                    try:
                        return response.json()
                    except:  # wcc: 如果无法json，直接作为python类解析（或者python类的列表）
                        return pickle.loads(response.content)
                return None

            except (RequestException, json.JSONDecodeError) as e:
                retries += 1
                if retries >= self.max_retries:
                    print(
                        f"[ERROR]Request failed after {self.max_retries} attempts: {url}"
                    )
                    print(f"[ERROR]Exception: {str(e)}")
                    return None

                print(
                    f"[WARN]Request failed ({retries}/{self.max_retries}), retrying in {self.retry_delay}s: {url}"
                )
                print(f"[WARN]Exception: {str(e)}")
                time.sleep(self.retry_delay)

    def get(self, path, params=None):
        """
        发送GET请求

        Args:
            path: API端点路径
            params: URL查询参数

        Returns:
            解析后的响应数据或None
        """
        return self._make_request("GET", path, params=params)

    def post(self, path, data):
        """
        发送POST请求

        Args:
            path: API端点路径
            data: 请求数据

        Returns:
            解析后的响应数据或None
        """
        return self._make_request("POST", path, json_data=data)

    def put(self, path, data):
        """
        发送PUT请求

        Args:
            path: API端点路径
            data: 请求数据

        Returns:
            解析后的响应数据或None
        """
        return self._make_request("PUT", path, json_data=data)

    def delete(self, path, data=None):
        """
        发送DELETE请求

        Args:
            path: API端点路径
            data: 可选的请求数据

        Returns:
            解析后的响应数据或None
        """
        return self._make_request("DELETE", path, json_data=data)
