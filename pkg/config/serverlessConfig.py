import os

class ServerlessConfig:
    # 存储路径，项目根目录的serverlessPersist目录
    PERSIST_BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'serverlessPersist')
    CODE_PATH = os.path.join(PERSIST_BASE, 'code/{namespace}/{name}')

    # 必要的文件路径，pkg目录下的serverless目录
    SRC_BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'serverless')
    SERVER_PATH = os.path.join(SRC_BASE, 'serverlessServer.py')

    # 镜像管理
    REGISTRY_URL = '10.119.15.182:7000'
    REGISTRY_USER = 'k8s'
    REGISTRY_PASSWORD = 'cloud_OS_4'

    # Pod参数
    POD_URL = "http://{host}:{port}/{function_name}"
    POD_NAMESPACE = 'function-{namespace}'
    POD_NAME = '{name}-{id}'
    POD_PORT = 6000

    # 扩容策略
    MAX_REQUESTS_PER_POD = 4
    MIN_REQUESTS_PER_POD = 1
    CHECK_TIME = 10.0