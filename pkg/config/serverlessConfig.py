import os

class ServerlessConfig:
    BASE_PATH = os.path.join(os.getenv('PYTHONPATH', '.'), 'serverlessPersist')

    CODE_PATH = os.path.join(BASE_PATH, 'code/{namespace}/{name}')
    IMAGE_PATH = os.path.join(BASE_PATH, 'images/{namespace}/{name}')

    SERVER_PORT = 5000
    FUNCTION_SPEC_URL = URIString("/apis/v1/namespaces/<namespace>/functions/<name>")