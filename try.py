import subprocess

def run_docker_command(command):
    try:
        result = subprocess.run(command, shell=True, check=True, text=True, capture_output=True)
        print(f"命令执行成功: {command}")
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"命令执行失败: {command}")
        print(f"错误信息: {e.stderr}")

# 定义要执行的 Docker 命令
commands = [
    "docker stop nginx-ingress",
    "docker rm nginx-ingress",
    """docker run -d --name nginx-ingress \
       -p 80:80 \
       -v /root/workspace2/k8s_group_4/config/nginx.conf:/etc/nginx/nginx.conf:ro \
       --network bridge \
       nginx:latest"""
]

# 依次执行命令
for cmd in commands:
    run_docker_command(cmd)
