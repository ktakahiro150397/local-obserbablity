# 2026-09-16 Windows usage 検証記録

非機密の集計結果のみ。実ID、会話、hostname、private address、credential、raw telemetryは含めない。

## 確認済み

- WindowsのCodex App package versionは26.908.4834.0。App本体の新設定反映・対話試験は残る。

- 最新remote mainから独立worktreeを作成。既存の別branchのdirty文書と未公開commit、serverのconfig/SOUL差分を保持した。
- Windows RAM約63.76 GiB/当初available約35.46 GiB。保存用C drive空き約74.2 GiB。Docker Desktop 4.45.0はstale AF_UNIX endpointへのアクセスエラーで起動不能。初期化・削除はせず、portable版を採用した。
- PostgreSQL17.11、Collector0.156.0、Grafana13.2.2の配置・再起動・全healthを確認。全7portが127.0.0.1。匿名dashboard APIは401、認証済みdatasource healthと全dashboard SQLが成功。
- normalizationの7試験。実Collector/PG acceptance: 2人×2threadの期待値303/707（計1,010）、replayと逆順、NULL/0、root除外、queue永続化・強制終了復旧・満杯拒否、canary不在、pg_dump/別DB復元。
- Hermes source/imageの9試験とplugin loaderを実機で実行。Hermes0.20.5の現行imageを基準に追加layerをbuildし、両gatewayへ最終image `sha256:f2f15ff54514fecd84d065fe9c6da0ba5095d64ccf8567e53d347f6d7cd4f015` を適用。両方healthy。model/provider/auth/config/SOULは上書きしない。
- Codex CLI0.153.4の非機密実turnがWindows ledgerへ到達。OTel以外のuser configはTOMLの意味比較で同一。logs/metrics exporter=none、traceだけlocalhostへ設定。App由来のoriginator環境変数がCLIを誤表示し得る点を実測してaudit helperで分離。
- main/owashotaの既存openai-codex providerで、tool/context/historyなしの実requestがWindowsへreportedで到達。管理用CLI試験はunattributed、稼働中cronはsystemとして記録された。real Discord userの操作を代行していない。
- 実機SSH断中もmainのprovider requestが完了。server queueで1,059 bytesの保留を確認し、その後の通常system処理も保留。forwarder再起動後もqueueを保持。再接続後にqueue=0、Windowsに遅延到達を確認。
- 切断後のstale Unix socketで初回再接続が失敗する問題を再現した。sshd全体の設定を変えず、owner・固定path・socket type・接続拒否・同一inodeを検査するprepare-socketで解消。通常file/active socketは消さない。
- Windows stackのstop/start、ledger保持、health復旧、SSH supervisor復旧を確認。本人ログイン時のStartup shortcutを配置。完全なOS rebootは行っていない。
- serverの旧LGTM×2、ledger×2、router、rollup、旧cloudflared×2を停止。container/bind dataを保持し、他のアプリは停止しない。新データを旧公開先へ送らない。
- server available memoryのsnapshotは約3.2→4.35 GiB、新forwarderは約34〜87 MiB / CPU0.04〜0.09%（hard limit192 MiB / CPU0.25）。Windows主要4process working set初回約410 MiB。ただしPG全worker合算や長期peakを測った値ではない。

初回切替中にendpoint未接続の期間があったため、それ以前から連続・完全に計測できたとは扱わない。新ledgerの測定開始/最終受信と状態履歴を表示する。旧履歴の再取込・削除はしない。

## HUMAN ACTION REQUIRED — 残る受入

根拠は [AGENTS.md](../AGENTS.md) と [human-actions.md H7/H8](../docs/human-actions.md)。H7は “A real Discord user must send the test request”、H8は本人によるApp完全終了・再起動後の対話を要求する。実participant操作を合成試験やCLIで代用しない。

1. **Discord**: 参加者に安定したDiscord IDとusage metadataを計測することを周知し、可能なら2人×2threadで「使用量計測の確認です。短くOKと返してください」と送る。同じthreadで別人からも1回送る。`http://127.0.0.1:13002/d/hermes-requests-v1` を今日/JSTへ設定し、user→threadを切り替え、人数・帰属・tokens・system分離を確認する。実ID/本文は返さず、試行時刻と期待どおりかだけ報告する。
2. **Codex App**: この作業終了後にAppを完全終了・再起動し、非機密の短いturnを1回行う。`/d/windows-codex-v1` のclient=desktopと時刻/usageを確認する。CLIの計測成功とは別の受入。
3. **owner画面とOS再起動**: ownerでGrafanaへログインし、今日/7日/30日/任意期間とuser/thread filterを確認する。都合のよいときにWindowsを再起動し、本人サインイン後にhealthとserver queueのdrainを確認する。未ログイン・sleep中はqueue容量/7日retryの範囲だけ保留できる。

外部 `codex exec` の日常利用有無は本人確認待ち。利用している場合、その子processのusageと親Discord turnのcorrelationが追加作業になる。現在のnative provider計測に含まれるとは報告しない。自動retention削除、過去履歴取込、請求額推計、OS全体のhard memory quotaは有効にしていない。

## 同日追加検証 — Allフィルター修正・概要画面

本人の報告を受け、ログイン済みChromeで使用量panelの `SQLSTATE 42703` を再現した。custom All値 `__all` がSQLの列参照になっていた。初回API試験はこの値を手動でquoteしており、ブラウザーの展開を検証できていなかった。上の「全dashboard SQLが成功」は当該試験条件に限った結果で、当時の実UI正常性の証拠とはしない。

- custom AllをSQL literal `'__all'` に変更。Grafanaはcustom Allをescapeしないため、`:sqlstring` だけでは不十分だった（[公式仕様](https://grafana.com/docs/grafana/latest/visualizations/dashboards/variables/add-template-variables/)）。
- verifierはprovision済みのvariable定義からAllをそのまま展開するように変更。修正前のdashboardに対してHTTP400を再現し、修正後に成功した。
- 3画面の全panel/variable queryを、All、単一値、複数値、quoteを含む一致なし、hour、および概要の3追加scopeで検証。実ID・query結果は試験出力へ出さない。datasource healthと匿名401も成功。
- 旧Hermes usage画面の表示設定を再利用し、private ledger用の概要を追加。合計/入力/出力/request stat、ユーザー棒グラフ、モデル円グラフ、時系列、内訳/割合、thread表、曜日×時間、cache割合、品質、計測範囲を表示。初期対象はDiscord利用でsystem/帰属不明を切替可能。
- Chromeの実画面で既存panelのエラー消失、概要の数値・棒/円/時系列描画、対象切替、環境の単一選択と複数選択で集計結果が変わることを確認。API試験だけを実画面確認の代わりにしていない。
- 既存dashboard JSONをprivate backupへ保存した後、file provisioningをreload。新しいデータ収集やpublic経路、DB変更、旧データ取込はない。実UIのスクリーンショットや実IDをrepositoryへ保存していない。

ownerログイン済みの画面確認は実施できた。H7の複数人・複数threadの受入、H8のApp再起動、完全なOS再起動は引き続き別の未完了確認である。
