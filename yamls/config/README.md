
1. 跑完dnsController
<!-- @REM chmod 644 /root/workspace2/k8s_group_4/config/nginx.conf -->
docker stop nginx-ingress
docker rm nginx-ingress
docker run -d --name nginx-ingress \
  -p 80:80 \
  -v  /root/workspace2/k8s_group_4/config/nginx.conf:/etc/nginx/nginx.conf:ro \
  --network bridge \
  nginx:latest


<!-- 还有配置那个 -->

或者
docker cp /root/workspace2/k8s_group_4/config/nginx.conf nginx-ingress:/etc/nginx/nginx.conf
docker exec nginx-ingress nginx -s reload

2. attend
sudo vim /etc/hosts
宿主机ip（10.119.15.182） 域名 （<node-ip> example.com）

仅一次，nginx可以不用重启，coredns也不用重启（故只需要生成nginx的配置文件和attend/etc/hosts）
docker exec -it etcd sh
etcdctl put /skydns/com/example/www '{"host":"<nginx-ip>","ttl":60}'
exit
etcdctl put /skydns/com/example/www '{"host":"10.5.53.7","ttl":60}'

3. 宿主机测试
curl http://10.96.112.32:80
curl http://example.com
curl http://example.com/app1

4.pods内部测试网络
docker run --rm --net=bridge alpine sh -c "apk add --no-cache curl && curl --max-time 5 --connect-timeout 3 http://10.96.112.32:80"
docker run --rm --net=bridge alpine sh -c "apk add --no-cache curl && curl --max-time 5 --connect-timeout 3 http://example.com"
docker run --rm --dns 10.5.53.3 --net=bridge alpine sh -c "apk add --no-cache curl && curl --max-time 5 --connect-timeout 3 http://example.com/app1"
