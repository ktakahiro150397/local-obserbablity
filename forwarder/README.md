# Hermes用の軽量forwarder

[Windows集約](../windows/README.md) のserver側。Hermesの既存Docker専用networkへCollectorを1個置く。Grafana、DB、Tempo、一般ログ、Docker API socketは持たない。digest固定image、read-only filesystem、capability全削除、memory192 MiB、CPU0.25。

pluginの送信先は `http://usage-forwarder:14319/v1/traces`。receiverにhost portはない。ownerのSSHが作る600のUnix socketを同じUIDのforwarderへread-only bind mountし、gRPCでWindows localhostへ送る。socketの接続権はUIDと親directory700で限定する。Dockerからhost bridgeへのHTTPがUFWで遮断された実機で、firewall変更を避けるためこの経路を採用した。

## 配置

ownerで次を作り、`compose.yaml` / `collector.yaml` / `prepare-socket.py` をconfig directoryへ配置する。既存stackは上書きしない。

```sh
umask 077
mkdir -p "$HOME/.config/ai-usage/docker" \
  "$HOME/.local/state/ai-usage/docker-queue" \
  "$HOME/.local/state/ai-usage/socket"
```

同じdirectoryの `.env`（Git管理外）へ実機で確認した値を指定する。

```dotenv
USAGE_UID=OWNER_NUMERIC_UID
USAGE_GID=OWNER_NUMERIC_GID
USAGE_QUEUE_DIR=/home/REMOTE_USER/.local/state/ai-usage/docker-queue
USAGE_SOCKET_DIR=/home/REMOTE_USER/.local/state/ai-usage/socket
HERMES_NETWORK=EXISTING_HERMES_NETWORK
```

```sh
docker compose config --quiet
docker compose up -d
curl -fsS http://127.0.0.1:14334/
```

WindowsからSSHを接続する。常用はWindows supervisorの `connection.local.json` を使う。

```powershell
./windows/Start-UsageTunnel.ps1 -SshHost server-ssh-alias -RemoteSocket /home/REMOTE_USER/.local/state/ai-usage/socket/otlp.sock
```

再接続時の `prepare-socket.py` は固定path・所有者・file type・接続拒否を検証し、使用中でない専用socketだけを作り直す。通常fileと使用中socketは保持して停止する。clientの `StreamLocalBindUnlink` だけではremote sshdのstale socketを解消できないため、この限定処理を使う。telemetry DB/queueは削除しない。serverへのTCP受信口は既存SSHだけ。新しい公開、router forwarding、firewall変更、host networkモードはない。

Hermes overlayに `usage-forwarder` のextra_hostsを書かずDocker DNSを使う。両gatewayがforwarderと同じ既存networkへ参加していることを確認する。計装imageの適用はbackup-secretaryのusage手順に従う。

## 停止・復旧

- contract/nameと属性をfilterした後に永続queueへ入れる。logs/metricsは受けない。ユーザーIDはspanだけに持ち、Prometheus labelへ追加しない。
- 論理queue64 MiB、bbolt128 MiB/DB、fsync有効。compaction用directoryを明示。filesystem quotaではなく一時領域が別途必要。
- timeout3秒、最大7日retry。Windows不在時もHermesは256 spanの非同期queueで応答経路を分離。容量・retry期限・disk障害・producer終了による欠測は保証対象外。
- `127.0.0.1:14889/metrics` のqueue size / enqueue_failed / send_failedを監視。counterはretryを含み、再起動でresetするのでWindowsの状態履歴と併せて読む。
- `docker compose stop` はqueueを保持し、`up -d` で同じdirectoryから復旧。`down -v`、queue削除、旧公開stackへのfallbackは使わない。
- `unless-stopped` でDocker daemon再起動後に復旧。Windowsは本人のログイン後にSSHが戻るまでbufferする。実OS rebootは本人確認事項。
