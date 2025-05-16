# docker swarm init
# docker swarm init --advertise-addr <manager-ip>
# docker swarm join --token <token> <manager-ip>:2377

# overlay的两个子网之间可以互相访问，打破了普通的子网的限制
overlay_network = client.networks.create(
    name="my_overlay_network",
    driver="overlay",
    scope="swarm",
    ipam={
        "Driver": "default",
        "Config": [
            {"Subnet": "192.168.10.0/24", "Gateway": "192.168.10.1"},
            {"Subnet": "192.168.20.0/24", "Gateway": "192.168.20.1"}
        ]
    }
)

# 创建第一个容器，并指定 IP 地址
container1 = client.containers.run(
    image="nginx",
    name="container1",
    network="my_overlay_network",
    detach=True,
    ip="192.168.10.10"
)
print(f"Created container1 with IP: 192.168.10.10")

# 创建第二个容器，并指定 IP 地址
container2 = client.containers.run(
    image="nginx",
    name="container2",
    network="my_overlay_network",
    detach=True,
    ip="192.168.10.11"
)
print(f"Created container2 with IP: 192.168.10.11")

# 创建第三个容器，并指定 IP 地址
container3 = client.containers.run(
    image="nginx",
    name="container3",
    network="my_overlay_network",
    detach=True,
    ip="192.168.20.10"
)

# 在 container1 中 ping container2
exec_result = container1.exec_run("ping -c 4 192.168.10.11")
print(exec_result.output.decode())