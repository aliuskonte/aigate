#!/bin/sh
# Генерирует prometheus.yml: база + remote_write при наличии PROMETHEUS_API_TOKEN

CONFIG_OUT="/tmp/prometheus.yml"
cp /etc/prometheus/prometheus.yml "$CONFIG_OUT"

if [ -n "$PROMETHEUS_API_TOKEN" ] && [ -n "$PROMETHEUS_REMOTE_WRITE_URL" ]; then
  cat >> "$CONFIG_OUT" << EOF

remote_write:
  - url: $PROMETHEUS_REMOTE_WRITE_URL
    bearer_token: $PROMETHEUS_API_TOKEN
EOF
fi

exec /bin/prometheus \
  --config.file="$CONFIG_OUT" \
  --storage.tsdb.path=/prometheus \
  --web.enable-lifecycle \
  "$@"
