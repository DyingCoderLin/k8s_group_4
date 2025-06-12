conda activate k8s
cd E:\本科学习\大三下\Cloud-OS\k8s_group_4
$env:PYTHONPATH="E:\本科学习\大三下\Cloud-OS\k8s_group_4"
python .\pkg\apiServer\apiServer.py

export PYTHONPATH=/root/workspace2/k8s_group_4:$PYTHONPATH

$env:PYTHONPATH="E:\本科学习\大三下\Cloud-OS\k8s_group_4"
python .\pkg\apiServer\apiServer.py


$env:PYTHONPATH="E:\本科学习\大三下\Cloud-OS\k8s_group_4"
python .\pkg\controller\dnsController.py


export PYTHONPATH=/root/workspace2/k8s_group_4:$PYTHONPATH

docker ps
docker ps -a 
docker rm -f $(docker ps -aq)
docker start $(docker ps -aq)

docker rm -f test-server-container-1  pause_default_test-server-1


ps aux | grep kubectl
kill -9 <第一行第二个参数>

./start.sh --stop
cd ./yamls
docker compose down
rm -rf zookeeper-log zookeeper-data kafka
mkdir zookeeper-data zookeeper-log kafka
mkdir kafka/data
chmod -R 777 ./kafka zookeeper-data zookeeper-log
docker compose up -d
cd ../

docker exec -it etcd /bin/sh
etcdctl put /coreos.com/network/config '{ "Network": "10.5.0.0/16", "Backend": {"Type": "vxlan"}}'
etcdctl put /skydns/com/example/www '{"host":"10.5.53.7","ttl":60}'
systemctl restart flanneld.service （三个都要）


docker exec -it pause_default_test-server-1 /bin/sh

./start.sh
@REM ./kubectl add node ./testFile/node-2.yaml
./kubectl apply -f ./testFile/test-pod-server-1.yaml
./kubectl apply -f ./testFile/dns-service-1.yaml
@REM test-dns-cloud.yaml




./kubectl apply -f ./testFile/test-pod-security-context.yaml



python ./pkg/controller/dnsController.py
cat ./config/nginx.conf

./kubectl get nodes
./kubectl get pods
./kubectl get services

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