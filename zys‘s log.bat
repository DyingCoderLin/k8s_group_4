conda activate k8s
cd E:\本科学习\大三下\Cloud-OS\k8s_group_4
$env:PYTHONPATH="E:\本科学习\大三下\Cloud-OS\k8s_group_4"
python .\pkg\apiServer\apiServer.py

export PYTHONPATH=/root/workspace2/k8s_group_4:$PYTHONPATH

$env:PYTHONPATH="E:\本科学习\大三下\Cloud-OS\k8s_group_4"
python .\pkg\apiServer\apiServer.py


$env:PYTHONPATH="E:\本科学习\大三下\Cloud-OS\k8s_group_4"
python .\pkg\controller\dnsController.py

python ./pkg/controller/dnsController.py


docker ps
docker ps -a 
docker rm -f $(docker ps -aq)
docker start $(docker ps -aq)

cd ./yamls
docker compose down
docker compose up -d
cd ../

docker exec -it etcd /bin/sh
etcdctl put /coreos.com/network/config '{ "Network": "10.5.0.0/16", "Backend": {"Type": "vxlan"}}'
systemctl restart flanneld.service （三个都要）



docker exec -it pause_default_test-server-1 /bin/sh


./start.sh
cat ./logs/apiserver.log
cat ./logs/scheduler.log

./kubectl get nodes

./kubectl add node ./testFile/node-1.yaml
cat ./logs/node.log
./stop_node.sh

./kubectl apply -f ./testFile/test-pod-server-1.yaml
./kubectl apply -f ./testFile/test-pod-server-2.yaml
./kubectl apply -f ./testFile/test-pod-server-3.yaml
docker ps -a （看看pod启动在哪里了）
./kubectl get pods

// 在一个label下可以直接启
./kubectl apply -f ./testFile/test-service-clusterip.yaml
./kubectl get services
curl clusterip:port
./kubectl delete service hello-world-service


./kubectl apply -f ./testFile/test-pod-server-1.yaml
./kubectl apply -f ./testFile/test-service-clusterip.yaml

 10.96.2.54


1. 跑完dnsController
@REM chmod 644 /root/workspace2/k8s_group_4/config/nginx.conf
docker stop nginx-ingress
docker rm nginx-ingress
docker run -d --name nginx-ingress \
  -p 80:80 \
  -v  /root/workspace2/k8s_group_4/config/nginx.conf:/etc/nginx/nginx.conf:ro \
  --network bridge \
  nginx:latest

 10.96.188.132

2. attend
sudo vim /etc/hosts
宿主机ip（10.119.15.182） 域名 （<node-ip> example.com）

3. 宿主机测试
curl http://10.96.188.132:80
curl http://example.com
curl http://example.com/app1

4.pods内部测试网络
docker run --rm --net=bridge alpine sh -c "apk add --no-cache curl && curl --max-time 5 --connect-timeout 3 http://10.96.188.132:80"
docker run --rm --net=bridge alpine sh -c "apk add --no-cache curl && curl --max-time 5 --connect-timeout 3 http://example.com"
docker run --rm --net=bridge alpine sh -c "apk add --no-cache curl && curl --max-time 5 --connect-timeout 3 http://example.com/app1"

events {
    worker_connections 1024;
}
http {
    include mime.types;
    default_type application/octet-stream;
    server {
        listen 80;
        server_name example.com;

        location /app1 {
            proxy_pass http://10.96.4.128:80;
            proxy_set_header Host $host;
        }
    }
}