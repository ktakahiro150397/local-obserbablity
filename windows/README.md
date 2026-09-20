# Windows owner-only AI usage

Windowsに保存・集計・Grafanaを集約する独立構成。今回の新経路にはshared backend、Cloudflare、会話ログ、Tempoの再読込はない。旧履歴は自動取込しない。

```text
Codex CLI / App -- OTLP HTTP (localhost) --+
                                         Windows Collector -> usage.requests -> Grafana
Hermes -> Docker内forwarder -> SSH Unix socket -- OTLP gRPC (localhost)
```

Windowsはportable PostgreSQL + Grafana OSS + Collector + 小さなOTLP JSON receiver。Docker Desktop起動不能を実機で確認したため、WSLやWindows serviceに依存しない構成を採用した。既存ledgerのPostgreSQL・writer/reader分離を再利用し、新しいrequest/turn表を使用する。旧serverのコンテナと保存データは保持する。

## 起動と接続

PowerShell、Python 3.10以降、tar、既存のSSH鍵・接続先を使う。実値はGitの外へ置く。

```powershell
./windows/Install-NativeUsage.ps1
./clients/codex/Install-CodexTelemetry.ps1 -EndpointBase http://127.0.0.1:14318 -UsageOnly
```

保存先は `$env:USERPROFILE\AIUsage`。パッケージ版CodexのLocalAppDataはアプリ専用領域へリダイレクトされ得るため使わない。ACLを本人とSYSTEMへ限定する。既存cluster・credential・archiveを初期化しない。version・URL・checksumの出所は [versions.json](versions.json)。EDB ZIPは公式HTTPS配布から得たhashを固定しており、独立した署名の検証済みとは扱わない。

Python依存は psycopg[binary] 3.3.4 / PyYAML 6.0.3。Collector 0.156.0、PostgreSQL 17.11、Grafana OSS 13.2.2を使用。

[forwarder](../forwarder/README.md) を用意し、保護された `AIUsage/connection.local.json` に次を置く。

```json
{"SshHost":"server-ssh-alias","RemoteSocket":"/home/REMOTE_USER/.local/state/ai-usage/socket/otlp.sock"}
```

```powershell
./windows/Start-UsageSupervisor.ps1 -AtLogin
```

本人のStartupフォルダへショートカットを追加する。Windows service・管理者権限・新しいfirewall規則は不要。サインイン後、backend/SSHを監視・復旧し、30秒間隔で状態を記録する。スリープ・サインアウト・電源断中はWindows側が動かず、serverの永続queueで保留する。実OS再起動・サインイン後の復旧は本人の最終確認事項。

Windowsのportはすべて127.0.0.1のみ: Grafana13002、OTLP HTTP14318/gRPC14317、内部receiver14320、PostgreSQL15432、Collector health14333/内部counter14888。

画面は概要 `/d/hermes-usage-overview-v1`、明細 `/d/hermes-requests-v1`、Windows `/d/windows-codex-v1`（すべて `http://127.0.0.1:13002`）。初期userは `owner`、passwordは `AIUsage/secrets/ui`。本人のPowerShellで `Get-Content "$env:USERPROFILE\AIUsage\secrets\ui" | Set-Clipboard` としてログイン画面へ貼り付けられる。秘密値をチャットへ送らない。匿名アクセス・signupは無効。

概要は以前のHermes usage画面のstat、ユーザー別棒グラフ、モデル比率、時系列、曜日/時間帯表を再利用する。初期表示は「Discord利用」で、上部の「対象」からすべて・自律処理・帰属不明へ切替。環境、モデル、ユーザー、スレッド、期間を絞れ、リンクでrequest明細へ移れる。新ledgerの計測開始以降が対象で、旧履歴の取込や料金推計は追加していない。

dashboardを再生成する場合はrepository内で `python windows/build_dashboards.py` と `python windows/build_overview.py` を実行する。後者は `grafana/shared/dashboards/hermes-usage-cost.json` の表示設定を読み、datasource/queryをWindows用へ置換する。生成JSONに実IDやtelemetryを含めない。

## 計測契約

|producer|唯一の正本|粒度・制限|
|---|---|---|
|Hermes|service `backup-secretary-hermes` / span `gen_ai.request` / contract `hermes.request.v1`|LLM attempt。sender/threadはgateway ContextVars。親・子・retryを一度ずつ加算|
|Codex CLI / App|`session_task.turn` / `codex.turn.token_usage.*`|turn合計。`handle_responses`・session/root累計を併算しない。LLM request/retry数とは区別|
|将来のOTLP client|`gen_ai.request` / `gen_ai.request.v1`|明示したusage属性のみ。合成adapter試験済み。実サービス対応は別途検証|

Codex CLI 0.153.4の実OTLPでturn usageを確認した。App識別子は既存実測の `Codex Desktop` / `codex-app-server`、CLIは `codex_exec`。Appから起動したCLIは `CODEX_INTERNAL_ORIGINATOR_OVERRIDE` を継承しAppを名乗る場合がある。audit helperは子の環境からこの変数だけを除く。通常Appの設定反映には完全再起動が必要で、CLI試験をAppの対話試験の代用にはしない。

`usage.requests`へ保存し、Grafanaはread-onlyの `grafana.*` viewを読む。UTCのevent時刻とreceived時刻を分離し、画面・日/時間バケットはJST。keyはsource+instance+trace ID+span IDのSHA256。transaction内 `ON CONFLICT DO NOTHING`、commit後だけACKする。replay・ACK消失・順序逆転で増えない。累計差分への変換や古い会話の再解釈はしない。

inputはcache、outputはreasoningを含み、totalはinput+outputだけ。HermesはCanonicalUsageの `prompt_tokens`（uncached+cache read+cache write）を優先する。未知値はNULL、既知0は0。partial/missing、error、system、unattributedを残し、人物へ推測配賦しない。Discord threadとHermes/Codex sessionは別列。ユーザー割合の分母は既知のDiscord usageだけ。サブスク残量・確定請求額ではない。

producerがspanを完了・送信する前に強制終了したusageは取得できない。Hermes accounting stateは4,096件・24時間で制限し、途中終了はunknown/missing。補助LLMや外部 `codex exec` がnative hookを通らない場合は対象外。外部CLIの利用有無・correlationは確認が必要で、未使用と推定して網羅を主張しない。

## Privacy・容量・欠測

Hermesは既存hermes-otelに追加したUsageProcessorで、SDK batch queueより前にallowlist spanを作る。本文、tool引数/出力、raw error、events、links、parent、trace state、不要なresource/scopeを捨てる。Collectorも永続queueより前にfilterする。logs/metrics pipeline、一般ログreceiver、debug exporterはない。Codexのlogs/metrics exporterもnone。Codex tracesは受信直後に対象turnと属性だけへ絞り、元payloadを保存しない。`log_user_prompt=false`単独をprivacyの根拠にはしない。

Collector 0.156.0の `set(links, [])` は実行時に失敗するため、linksのあるspan自体をdropする。Hermes sourceはlinksを除去済み。Codexの実測対象turnはlinks=0。将来link付きusageが現れたらfilter counterとschemaを再検証する。

|component|設定|
|---|---|
|server forwarder|memory hard limit192 MiB、CPU0.25、Go soft heap160 MiB|
|両Collector queue|論理64 MiB、bbolt128 MiB/DB、fsync有効。compaction一時領域は別。filesystem全体のquotaではない|
|export retry|timeout3秒、1〜30秒間隔、最大7日。満杯は拒否。retry期限・disk障害・SDK queue枯渇では欠測し得る|
|Hermes SDK|非同期256 span、batch64、1秒間隔、HTTP timeout3秒。session-end同期flushなし|
|Windows|Collector limiter128 MiB/Go soft heap160 MiB。receiver body1 MiB・逐次処理。PG shared_buffers64 MiB/max_connections30。OS全体のhard memory quotaなし|
|新DB|2 GiB到達で新規batchを503にしqueueへ保留。WAL・binary・backup・compactionは別容量。自動削除なし|

明細30日・日次180日は初期検討案。今回の「既存データを削除しない」に合わせ自動retention purgeは無効。期間確定後に別途設計する。空の期間や古いlast_receivedを利用ゼロとは扱わない。画面に最終受信、計測開始、未取得、経路状態履歴を表示し、状態観測が途切れた期間も不明として扱う。counterの失敗数はretryを含み、永久欠測数そのものではない。

## 日常操作・復旧

```powershell
& "$env:USERPROFILE/AIUsage/python/Scripts/python.exe" ./windows/status.py
& "$env:USERPROFILE/AIUsage/python/Scripts/python.exe" ./windows/backup.py
./windows/Stop-NativeUsage.ps1
./windows/Start-NativeUsage.ps1
./windows/Start-UsageSupervisor.ps1
```

StopはPID・実行file・開始時刻を照合し、この構成だけを止める。queue/DBは保持。起動は別processのportを奪わない。自動起動の解除は本人のStartupフォルダの `Private AI Usage.lnk` だけを外す。

backupは保護された `AIUsage/backups/*.dump`。`backup.py --restore <dump> --new-database usage_restore_TEST` は未使用の別DBへだけ復元する。既存DBへの `--clean` はない。件数・合計確認後のdatasource切替は別判断。別PCへの完全復旧にはsecret files、Grafana data/config、pin済みsourceも私的backupへ含める。稼働中queueの単純copyは復旧用backupとみなさない。

切戻しはproducer送信を無効にし新stackを停止する。Codex設定にはtimestamp付きbackupがあるが、OTel以外の変更を巻き戻さず、旧公開経路へは戻さない。旧server volume/DBは保持したまま。旧Cloudflare/sharedへの自動fallbackはない。

## 検証

```powershell
& "$env:USERPROFILE/AIUsage/python/Scripts/python.exe" ./windows/tests/test_normalize.py -v
& "$env:USERPROFILE/AIUsage/python/Scripts/python.exe" ./windows/tests/acceptance.py
& "$env:USERPROFILE/AIUsage/python/Scripts/python.exe" ./windows/tests/verify_grafana.py
```

acceptanceは専用DB/port/queueを作り、2人×2thread=1,010 tokens（303/707）、replay/逆順、NULL、root除外、queue永続化と強制終了からの復旧、満杯拒否、canary不在、別DBへのrestoreを確認する。試験データは削除せず本番dashboardにも混ぜない。実機結果・残る本人操作は [verification.md](verification.md)。
