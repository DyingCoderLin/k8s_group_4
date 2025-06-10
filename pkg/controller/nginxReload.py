import subprocess
import sys

def run_command(command):
    try:
        result = subprocess.run(command, shell=True, check=True, text=True, capture_output=True)
        print(f"命令 '{command}' 执行成功。")
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"执行命令 '{command}' 出错: {e.stderr}", file=sys.stderr)
        sys.exit(1)

def main():
    # 将更新后的 nginx.conf 复制到容器中
    run_command("docker cp /root/workspace2/k8s_group_4/config/nginx.conf nginx-ingress:/etc/nginx/nginx.conf")
    
    # 重新加载 Nginx 配置
    run_command("docker exec nginx-ingress nginx -s reload")

if __name__ == "__main__":
    main()
