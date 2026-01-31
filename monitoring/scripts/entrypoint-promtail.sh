#!/bin/sh
# Генерирует config.yaml: локальный Loki + опционально Grafana Cloud при наличии LOKI_API_TOKEN

CONFIG_OUT="/tmp/promtail-config.yaml"

cat > "$CONFIG_OUT" << 'BASE'
server:
  http_listen_port: 9080

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push
BASE

if [ -n "$LOKI_API_TOKEN" ] && [ -n "$LOKI_URL" ]; then
  cat >> "$CONFIG_OUT" << CLOUD

  - url: $LOKI_URL
    bearer_token: $LOKI_API_TOKEN
CLOUD
fi

cat >> "$CONFIG_OUT" << 'BASE'

scrape_configs:
  - job_name: docker
    docker_sd_configs:
      - host: unix:///var/run/docker.sock
        refresh_interval: 5s
    relabel_configs:
      - source_labels: ["__meta_docker_container_id"]
        regex: "(.+)"
        target_label: "__path__"
        replacement: "/var/lib/docker/containers/$1/*-json.log"
      - source_labels: ["__meta_docker_container_name"]
        regex: "/(.*)"
        target_label: "container"
    pipeline_stages:
      - docker: {}
BASE

exec /usr/bin/promtail -config.file="$CONFIG_OUT" "$@"
