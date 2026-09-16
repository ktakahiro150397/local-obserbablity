"""Reproducible PostgreSQL dashboards; no runtime data or identity aliases."""
import json
from pathlib import Path

OUT = Path(__file__).parent / "dashboards"
DS = {"type": "postgres", "uid": "private-usage"}


def variable(name, query=None, values=None):
    if values:
        return dict(name=name, label=name, type="custom", query=values,
                    current={"text": "day", "value": "day"})
    return dict(name=name, label=name, type="query", datasource=DS, query=query,
                definition=query, includeAll=True, allValue="__all", multi=True,
                refresh=2, current={"text": "All", "value": ["$__all"]})


def build(source, title, uid):
    variables = [variable("bucket", values="day,hour")]
    variables += [variable(k, f"SELECT DISTINCT COALESCE({col}, 'none') FROM grafana.requests WHERE source='{source}' ORDER BY 1")
                  for k, col in [("instance", "instance"), ("model", "model")]]
    if source == "hermes":
        variables += [variable("user", "SELECT DISTINCT user_id FROM grafana.requests WHERE source='hermes' ORDER BY 1"),
                      variable("thread", "SELECT DISTINCT COALESCE(thread_id, 'none') FROM grafana.requests WHERE source='hermes' ORDER BY 1")]
    where = f"source='{source}' AND $__timeFilter(occurred_at)"
    for key, col in [("instance", "instance"), ("model", "model")] + (
            [("user", "user_id"), ("thread", "thread_id")] if source == "hermes" else []):
        var = "${" + key + ":sqlstring}"
        where += f" AND ('__all' IN ({var}) OR COALESCE({col},'none') IN ({var}))"
    panels = []

    def panel(name, sql, kind="table", height=8, description=""):
        i = len(panels) + 1
        panels.append(dict(id=i, title=name, type=kind, datasource=DS,
            description=description, gridPos={"x": 0, "y": sum(p["gridPos"]["h"] for p in panels), "w": 24, "h": height},
            fieldConfig={"defaults": {"unit": "locale", "decimals": 0, "noValue": "未取得"}, "overrides": []},
            targets=[dict(refId="A", datasource=DS, rawQuery=True, rawSql=sql, format="time_series" if kind == "timeseries" else "table")],
            options={"showHeader": True, "tooltip": {"mode": "multi"}, "legend": {"displayMode": "list", "placement": "bottom"}}))

    panel("計測状況・最終受信（停止中や未取得を未使用と解釈しない）",
          f"SELECT source, instance, measurement_start, last_event, last_received, now()-last_received AS receive_age, incomplete_records, unattributed_records FROM grafana.usage_health WHERE source='{source}'",
          height=5, description="この新規ledgerへの計測範囲。過去履歴は未取込。受信停止時のゼロ利用は保証しません。queue/dropは運用statusコマンドで確認。")
    panel("収集経路の状態・queue・失敗（再起動時にcounterはreset）",
          "SELECT DISTINCT ON (component) component,observed_at,healthy,queue_bytes,failures FROM grafana.pipeline_health ORDER BY component,observed_at DESC",
          height=5,description="毎分の確認。観測時刻が古い／履歴がない期間は稼働不明です。forwarderの失敗counterはretryを含み、永久欠測件数とは一致しません。")
    panel("経路状態の履歴（最新500件・観測なしは未使用とみなさない）",
          "SELECT * FROM grafana.pipeline_health WHERE $__timeFilter(observed_at) ORDER BY observed_at DESC LIMIT 500",height=5)
    panel("使用量内訳・粒度・失敗・未取得",
          f"SELECT client,granularity, count(*) AS observed_records, count(*) FILTER(WHERE granularity='request') AS llm_attempts, count(DISTINCT turn_id) AS turns_with_id, count(*) FILTER(WHERE outcome='error') AS errors, count(*) FILTER(WHERE quality!='reported') AS incomplete, sum(input_tokens) AS input_including_cache, sum(output_tokens) AS output_including_reasoning, sum(cache_read_tokens) AS cached_input_subset, sum(reasoning_tokens) AS reasoning_output_subset, sum(total_tokens) AS known_total FROM grafana.requests WHERE {where} GROUP BY client,granularity",
          height=6, description="cacheはinputの内数、reasoningはoutputの内数。CLI turn数はLLM request数ではありません。token数はサブスク残量や確定請求額ではありません。")
    if source == "hermes":
        panel("Discordユーザー別ランキング・既知使用量に対する割合",
              f"WITH u AS (SELECT user_id,sum(total_tokens) AS tokens,count(*) AS attempts,count(*) FILTER(WHERE quality!='reported') AS missing FROM grafana.requests WHERE {where} GROUP BY user_id) SELECT user_id,tokens,attempts,missing,CASE WHEN user_id LIKE 'discord:%' THEN round(100.0*tokens/NULLIF(sum(tokens) FILTER(WHERE user_id LIKE 'discord:%') OVER(),0),2) END AS known_discord_share_pct FROM u ORDER BY tokens DESC NULLS LAST",
              description="system/unattributedは別枠。割合の分母は既知のDiscordユーザー使用量だけです。未取得usageはゼロへ変換しません。")
        panel("ユーザー → Discordスレッド（通常channel/DMはnone）",
              f"SELECT user_id,COALESCE(thread_id,'none') AS discord_thread,channel_id,instance,profile,model,count(DISTINCT turn_id) FILTER(WHERE parent_turn_id IS NULL AND user_id LIKE 'discord:%') AS user_input_turns,count(DISTINCT turn_id) FILTER(WHERE parent_turn_id IS NOT NULL) AS delegated_turns,count(*) AS attempts,sum(total_tokens) AS known_tokens FROM grafana.requests WHERE {where} GROUP BY 1,2,3,4,5,6 ORDER BY known_tokens DESC NULLS LAST")
    bucket = "date_trunc(${bucket:sqlstring},occurred_at AT TIME ZONE 'Asia/Tokyo') AT TIME ZONE 'Asia/Tokyo'"
    series = "user_id" if source == "hermes" else "client"
    panel("日別／時間帯別の既知トークン（JST境界）",
          f"SELECT {bucket} AS time,{series} AS metric,sum(total_tokens) AS tokens FROM grafana.requests WHERE {where} GROUP BY 1,2 ORDER BY 1", "timeseries",
          description="bucketでday/hour。欠測をゼロで埋めません。期間は右上で今日・7日・30日・任意期間へ変更できます。")
    panel("instance・profile・model・provider別",
          f"SELECT instance,profile,model,provider,quality,sum(total_tokens) AS known_tokens,count(*) AS records FROM grafana.requests WHERE {where} GROUP BY 1,2,3,4,5 ORDER BY known_tokens DESC NULLS LAST")
    panel("turn/request明細（最新500件）",
          f"SELECT occurred_at,received_at,user_id,thread_id,channel_id,session_id,turn_id,parent_turn_id,request_id,retry,granularity,outcome,quality,model,input_tokens,output_tokens,cache_read_tokens,reasoning_tokens,total_tokens FROM grafana.requests WHERE {where} ORDER BY occurred_at DESC LIMIT 500",
          height=12, description="Discord threadとHermes/Codex sessionは別識別子です。requestとturn累計を同時加算しません。")
    return dict(uid=uid,title=title,tags=["private","usage"],schemaVersion=40,version=1,
                timezone="Asia/Tokyo",editable=False,refresh="30s",time={"from":"now-7d","to":"now"},
                timepicker={},templating={"list":variables},panels=panels)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for source,title,uid in [("hermes","Hermes ユーザー別利用量","hermes-requests-v1"),
                             ("codex","Windows Codex 利用量","windows-codex-v1")]:
        (OUT / f"{source}.json").write_text(json.dumps(build(source,title,uid),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
