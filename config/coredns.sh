docker run -d \
  --name coredns \
  -p 54:53/udp \
  -p 54:53/tcp \
  -v /root/workspace2/k8s_group_4/config/Corefile:/Corefile \
  --network bridge \
  coredns/coredns:latest