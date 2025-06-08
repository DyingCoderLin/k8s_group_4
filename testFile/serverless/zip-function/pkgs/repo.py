import requests

def use_api():
    api_url = "https://jsonplaceholder.typicode.com/todos/1"
    response = requests.get(api_url)
    response.raise_for_status()  # 检查HTTP错误

    return response