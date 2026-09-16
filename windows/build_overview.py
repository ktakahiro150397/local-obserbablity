"""Adapt the previous Hermes usage dashboard's visual panels to the private ledger."""
import copy
import json
from pathlib import Path

from build_dashboards import DS, query_variables, usage_where


def build_overview():
    previous = json.loads((Path(__file__).parents[1] / "grafana/shared/dashboards/hermes-usage-cost.json").read_text(encoding="utf-8"))
    styles = {p["id"]: p for p in previous["panels"]}
    variables = query_variables("hermes")
    labels = {"bucket": "集計単位", "instance": "環境", "model": "モデル", "user": "ユーザー", "thread": "スレッド"}
    for v in variables:
        v["label"] = labels[v["name"]]
    variables.insert(0, dict(name="scope", label="対象", type="custom",
        query="Discord利用 : discord, すべて : all, 自律処理 : system, 帰属不明 : unattributed",
        current={"text": "Discord利用", "value": "discord"}, multi=False, includeAll=False))
    base = usage_where("hermes")
    where = base + " AND (${scope:sqlstring}='all' OR (${scope:sqlstring}='discord' AND user_id LIKE 'discord:%') OR user_id=${scope:sqlstring})"
    user_label = "CASE user_id WHEN 'system' THEN 'system（自律処理）' WHEN 'unattributed' THEN 'unattributed（帰属不明）' ELSE user_id END"
    panels = []

    def panel(style, title, query, x, y, w, h, description="", time_series=False):
        source = styles[style]
        p = {key: copy.deepcopy(source[key]) for key in ("type", "options", "fieldConfig")}
        if "transformations" in source:
            p["transformations"] = copy.deepcopy(source["transformations"])
        p.update(id=len(panels)+1, title=title, description=description, datasource=DS,
            gridPos=dict(x=x, y=y, w=w, h=h), targets=[dict(refId="A", datasource=DS, rawQuery=True,
            rawSql=query, format="time_series" if time_series else "table")])
        p["fieldConfig"]["defaults"]["noValue"] = "未取得"
        if p["type"] == "bargauge":
            p["options"].update(namePlacement="left", sizing="manual", maxVizHeight=48,
                legend=dict(showLegend=True,displayMode="table",placement="bottom",calcs=["lastNotNull"]))
        panels.append(p)
        return p

    description = "選択した期間・対象の既知使用量。cacheは入力、reasoningは出力の内数。未知値を0とみなさず、サブスク残量や料金へ換算しません。"
    for i, (column, title) in enumerate((("total_tokens", "合計トークン"), ("input_tokens", "入力トークン（cache含む）"), ("output_tokens", "出力トークン（reasoning含む）"))):
        panel(1, title, f'SELECT sum({column})::bigint AS "{title}" FROM grafana.requests WHERE {where}', i*6, 0, 6, 4, description)
    panel(1, "LLMリクエスト数", f'SELECT count(*) AS "リクエスト" FROM grafana.requests WHERE {where}', 18, 0, 6, 4,
        "観測したrequest attempt数。retryを含み、ユーザー発言数とは異なります。")
    panel(5, "ユーザー別トークン", f'SELECT {user_label} AS "Metric", sum(total_tokens)::double precision AS "Value" FROM grafana.requests WHERE {where} GROUP BY user_id ORDER BY "Value" DESC NULLS LAST', 0, 4, 12, 9,
        "対象でDiscord利用と自律処理を切替。systemや帰属不明を特定ユーザーへ配分しません。")
    panel(10, "モデル別トークン比率", f"SELECT now() AS time, COALESCE(model,'未取得') AS metric, sum(total_tokens)::double precision AS value FROM grafana.requests WHERE {where} GROUP BY model ORDER BY value DESC NULLS LAST", 12, 4, 12, 9,
        "選択対象の既知トークンをモデル別に集計。", True)
    bucket = "date_trunc(${bucket:sqlstring},occurred_at AT TIME ZONE 'Asia/Tokyo') AT TIME ZONE 'Asia/Tokyo'"
    series = panel(8, "ユーザー別トークン推移（JST）", f"SELECT {bucket} AS time, {user_label} AS metric, sum(total_tokens)::bigint AS value FROM grafana.requests WHERE {where} GROUP BY 1,2 ORDER BY 1", 0, 13, 24, 10,
        "集計単位day/hourで日別・時間帯別を切替。記録のない時間帯を利用0で補完しません。", True)
    series["fieldConfig"]["defaults"]["custom"] = dict(drawStyle="bars", barAlignment=0,
        fillOpacity=65, lineWidth=1, stacking={"mode": "normal", "group": "tokens"}, spanNulls=False)
    series["options"]["legend"] = dict(showLegend=True, displayMode="table", placement="bottom", calcs=["sum"])
    panel(7, "ユーザー別の内訳・割合", f"""WITH u AS (
        SELECT user_id, sum(input_tokens)::bigint AS input, sum(output_tokens)::bigint AS output,
        sum(total_tokens)::bigint AS tokens, count(*) AS attempts,
        count(DISTINCT turn_id) FILTER(WHERE parent_turn_id IS NULL AND user_id LIKE 'discord:%') AS user_turns,
        count(*) FILTER(WHERE quality!='reported') AS incomplete
        FROM grafana.requests WHERE {where} GROUP BY user_id)
        SELECT user_id AS "ユーザー", user_turns AS "入力turn", attempts AS "リクエスト",
        input AS "入力", output AS "出力", tokens AS "合計",
        CASE WHEN user_id LIKE 'discord:%' THEN round(100.0*tokens/NULLIF(sum(tokens) FILTER(WHERE user_id LIKE 'discord:%') OVER(),0),2) END AS "Discord内の割合(%)",
        incomplete AS "usage未取得" FROM u ORDER BY tokens DESC NULLS LAST""", 0, 23, 24, 8,
        "割合は選択中の既知Discord使用量を分母にします。system/帰属不明には割合を付けません。")
    panel(7, "スレッド別トークン・利用者", f'''SELECT COALESCE(thread_id,'なし（channel/DM）') AS "スレッド", user_id AS "ユーザー", instance AS "環境",
        count(*) AS "リクエスト", sum(total_tokens)::bigint AS "合計トークン"
        FROM grafana.requests WHERE {where} GROUP BY 1,2,3 ORDER BY "合計トークン" DESC NULLS LAST''', 0, 31, 24, 8,
        "上部のユーザー・スレッドで絞り込めます。session/turn/requestの識別子は明細画面で確認できます。")
    hours = ",".join(f'''sum(total_tokens) FILTER(WHERE extract(hour FROM occurred_at AT TIME ZONE 'Asia/Tokyo')={h})::bigint AS "{h:02d}"''' for h in range(24))
    heatmap = panel(11, "曜日 × 時間帯のトークン（JST）", f'''SELECT
        (ARRAY['月','火','水','木','金','土','日'])[extract(isodow FROM occurred_at AT TIME ZONE 'Asia/Tokyo')::int] AS "Weekday", {hours}
        FROM grafana.requests WHERE {where}
        GROUP BY extract(isodow FROM occurred_at AT TIME ZONE 'Asia/Tokyo') ORDER BY extract(isodow FROM occurred_at AT TIME ZONE 'Asia/Tokyo')''', 0, 39, 24, 8,
        "選択期間の曜日・時刻別合計。未観測のセルは—で表示し、利用0とは断定しません。")
    heatmap["fieldConfig"]["defaults"].update(unit="short", decimals=1, noValue="—",
        mappings=[dict(type="special",options=dict(match="null",result=dict(text="—",color="transparent")))])
    for override in heatmap["fieldConfig"]["overrides"]:
        for prop in override["properties"]:
            if prop["id"] == "custom.width":
                prop["value"] = 64 if override["matcher"]["id"] == "byName" else 52
    panel(12, "モデル別cache-read割合", f'''SELECT COALESCE(model,'未取得') AS "Metric",
        (100.0*sum(cache_read_tokens)/NULLIF(sum(input_tokens) FILTER(WHERE cache_read_tokens IS NOT NULL),0))::double precision AS "Value"
        FROM grafana.requests WHERE {where} GROUP BY model ORDER BY "Value" DESC NULLS LAST''', 0, 47, 12, 8,
        "cache-readが報告されたrequestの入力tokenを分母にした内数割合。未知cacheを0として扱いません。")
    panel(7, "取得品質・エラー", f'''SELECT quality AS "usage品質", outcome AS "結果", count(*) AS "リクエスト", sum(total_tokens)::bigint AS "既知トークン"
        FROM grafana.requests WHERE {where} GROUP BY quality,outcome ORDER BY quality,outcome''', 12, 47, 12, 8,
        "reported=入力/出力を取得、partial=一部のみ、missing=usage未取得。観測できなかったrequest数は含められません。")
    panel(7, "計測開始・最終受信", '''SELECT instance AS "環境",measurement_start AS "計測開始",last_event AS "最終イベント",last_received AS "最終受信",incomplete_records AS "未取得件数"
        FROM grafana.usage_health WHERE source='hermes' ORDER BY instance''', 0, 55, 24, 5,
        "期間filter外も含む全計測範囲。Windowsの新ledgerのみで、以前の保存データは未取込です。最終受信が古いだけで利用ゼロとは判断しません。")
    return dict(uid="hermes-usage-overview-v1",title="Hermes 使用量の概要",schemaVersion=40,version=1,
        description="以前の使用量画面の棒グラフ・モデル比率・時系列をWindowsのprivate usage ledgerへ適用。初期表示はDiscord利用。料金推計と過去データ取込は含みません。",
        tags=["private","usage"],timezone="Asia/Tokyo",editable=False,refresh="30s",graphTooltip=1,
        time={"from":"now-7d","to":"now"},timepicker={},templating={"list":variables},panels=panels,
        links=[dict(type="link",title="ユーザー・スレッド・request明細",url="/d/hermes-requests-v1",keepTime=True,includeVars=True,targetBlank=False),
               dict(type="link",title="Windows Codex",url="/d/windows-codex-v1",keepTime=True,includeVars=False,targetBlank=False)])


if __name__ == "__main__":
    (Path(__file__).parent/"dashboards/hermes-overview.json").write_text(json.dumps(build_overview(),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
