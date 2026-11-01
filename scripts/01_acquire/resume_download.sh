#!/usr/bin/env bash
# hf-mirror 连接被临时阻断后的自动续传：每 5 分钟重新解析真实 IP 并探测连通性，
# 恢复后以 4 连接续传 val.tar（download_sportsmot_hf.py 自带分段断点续传，
# 已完成的分段会自动跳过）。最多尝试 24 轮（约 2 小时）。
#
# 背景：train.tar 下载完成后，val.tar 下到 78/100 段时触发了动态 RST 阻断
# （TCP 能握手、发数据即被重置），此类阻断通常几分钟到几小时自动解除。
set -u
cd "$(dirname "$0")/../.." || exit 1
LOG=download_retry.log

probe() {  # 用给定 IP 探测 hf-mirror 可达性
  curl -s --max-time 10 --resolve "hf-mirror.com:443:$1" -o /dev/null https://hf-mirror.com/
}

for round in $(seq 1 24); do
  ts=$(date +%H:%M:%S)
  ip=$(curl -s --max-time 8 "https://223.5.5.5/resolve?name=hf-mirror.com&type=A" \
       | grep -o '"data":"[^"]*"' | head -1 | cut -d'"' -f4)
  ip=${ip:-160.16.86.14}
  if probe "$ip"; then
    echo "[$ts] round $round: 连通(IP=$ip)，续传" | tee -a "$LOG"
    if .venv/Scripts/python.exe scripts/01_acquire/download_sportsmot_hf.py \
         --parts val --workers 4 --chunk-mb 64 --hf-ip "$ip" >> "$LOG" 2>&1; then
      echo "[$ts] round $round: val.tar 下载完成" | tee -a "$LOG"
      exit 0
    fi
    echo "[$ts] round $round: 续传未完成，5 分钟后重试" | tee -a "$LOG"
  else
    echo "[$ts] round $round: 仍被阻断(IP=$ip)" | tee -a "$LOG"
  fi
  sleep 300
done
echo "重试窗口（2 小时）用尽仍未完成，请手动处理" | tee -a "$LOG"
exit 1
