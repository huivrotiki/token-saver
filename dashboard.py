#!/usr/bin/env python3
"""
TokenSaver Dashboard v4.0
Metrics: Auto Compact + Sessions + Cost + Routing + Quality
Run: python3 dashboard.py [--port 8050] [--host 127.0.0.1]
Requires: pip install dash plotly
"""
import time, sqlite3, re, os
from pathlib import Path
from dash import Dash, html, dcc, callback, Output, Input
import plotly.graph_objects as go

# ── DB ───────────────────────────────────────────────────────
TS_DIR  = Path.home() / ".tokensaver"
DB_PATH = str(TS_DIR / "tokensaver.db")
LOG_PATH = TS_DIR / "tokensaver.log"

def db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def get_db_stats() -> dict:
    try:
        c = db()
        cache_total  = c.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        cache_vecs   = c.execute("SELECT COUNT(*) FROM cache WHERE vec IS NOT NULL").fetchone()[0]
        cache_recent = c.execute("SELECT COUNT(*) FROM cache WHERE ts>?",
                                 (time.time()-3600,)).fetchone()[0]
        sess = c.execute(
            "SELECT COUNT(*), COALESCE(SUM(msg_count),0), COALESCE(SUM(cost_total),0) "
            "FROM sessions WHERE updated_at>?", (time.time()-86400,)
        ).fetchone()
        sess_rows = c.execute(
            "SELECT session_id, msg_count, cost_total, updated_at "
            "FROM sessions WHERE updated_at>? ORDER BY updated_at DESC LIMIT 20",
            (time.time()-86400,)
        ).fetchall()
        c.close()
        return {
            "cache_total":  cache_total,
            "cache_vecs":   cache_vecs,
            "cache_recent": cache_recent,
            "sess_active":  sess[0],
            "sess_msgs":    sess[1],
            "sess_cost":    round(sess[2], 5),
            "sess_rows":    sess_rows,
        }
    except Exception:
        return {"cache_total":0,"cache_vecs":0,"cache_recent":0,
                "sess_active":0,"sess_msgs":0,"sess_cost":0.0,"sess_rows":[]}

def get_log_metrics() -> dict:
    m = {
        "compact_count":0, "compact_fallback":0,
        "compact_quality_sum":0.0, "compact_quality_n":0,
        "local_count":0, "cloud_count":0, "cache_hits":0,
        "cost_total":0.0, "req_total":0,
        "hist_times":[], "hist_cost":[], "hist_local_pct":[],
    }
    if not LOG_PATH.exists(): return m
    lines = LOG_PATH.read_text(errors="ignore").splitlines()[-3000:]
    w_cost=0.0; w_reqs=0; w_local=0; last_ts=None
    for line in lines:
        if "COMPACT_DONE" in line:
            m["compact_count"] += 1
            q = re.search(r"quality=([\d.]+)", line)
            if q:
                m["compact_quality_sum"] += float(q.group(1))
                m["compact_quality_n"]   += 1
        if "COMPACT_FALLBACK" in line: m["compact_fallback"] += 1
        if "CACHE_HIT" in line or "FUZZY_HIT" in line: m["cache_hits"] += 1
        if line[:2].isdigit() and " OK " in line:
            m["req_total"] += 1
            c = re.search(r"cost=([\d.]+)", line)
            l = re.search(r"local=(True|False)", line)
            if c: v=float(c.group(1)); m["cost_total"]+=v; w_cost+=v; w_reqs+=1
            if l:
                if l.group(1)=="True": m["local_count"]+=1; w_local+=1
                else: m["cloud_count"]+=1
            try:
                ts=time.mktime(time.strptime(line[:19],"%Y-%m-%d %H:%M:%S"))
            except: ts=time.time()
            if last_ts is None or ts-last_ts>300:
                if w_reqs>0:
                    m["hist_times"].append(time.strftime("%H:%M",time.localtime(ts)))
                    m["hist_cost"].append(round(w_cost,5))
                    m["hist_local_pct"].append(round(w_local/w_reqs*100,1))
                w_cost=0.0; w_reqs=0; w_local=0; last_ts=ts
    return m

# ── App ───────────────────────────────────────────────────────
app = Dash(__name__, title="TokenSaver Dashboard")

BG=     "#0f1117"
CARD=   "#1a1d27"
GREEN=  "#00d26a"
BLUE=   "#4f8ef7"
GOLD=   "#f7c94f"
RED=    "#f74f4f"
PURPLE= "#b46ef7"
TEAL=   "#4ff7e0"

def kpi(title, val, sub="", color=GREEN):
    return html.Div([
        html.P(title, style={"color":"#888","margin":"0","fontSize":"11px"}),
        html.H2(val,  style={"color":color,"margin":"4px 0","fontSize":"26px","fontWeight":"bold"}),
        html.P(sub,   style={"color":"#555","margin":"0","fontSize":"10px"}),
    ], style={"background":CARD,"borderRadius":"12px","padding":"16px 20px",
              "borderLeft":f"3px solid {color}"})

def dark():
    return dict(paper_bgcolor=CARD, plot_bgcolor=CARD,
                font=dict(color="#aaa",family="monospace",size=11),
                margin=dict(l=40,r=20,t=40,b=40))

app.layout = html.Div([
    html.Div([
        html.H1("⚡ TokenSaver v5",
                style={"color":GREEN,"margin":"0","fontSize":"26px"}),
        html.P("Real-time · Auto Compact · Fuzzy Cache · Sessions · Cost",
               style={"color":"#555","margin":"4px 0 0","fontSize":"12px"}),
    ], style={"padding":"20px 28px 12px","borderBottom":"1px solid #222"}),

    # KPI row 1 — основные
    html.Div(id="kpi-main", style={
        "display":"grid","gridTemplateColumns":"repeat(6,1fr)",
        "gap":"10px","padding":"16px 20px 8px"}),

    # KPI row 2 — compact + sessions
    html.Div(id="kpi-compact", style={
        "display":"grid","gridTemplateColumns":"repeat(6,1fr)",
        "gap":"10px","padding":"0 20px 16px"}),

    # Графики 2×3
    html.Div([
        html.Div([dcc.Graph(id="cost-line",     config={"displayModeBar":False})],
                 style={"background":CARD,"borderRadius":"12px","padding":"12px"}),
        html.Div([dcc.Graph(id="route-donut",   config={"displayModeBar":False})],
                 style={"background":CARD,"borderRadius":"12px","padding":"12px"}),
        html.Div([dcc.Graph(id="saving-gauge",  config={"displayModeBar":False})],
                 style={"background":CARD,"borderRadius":"12px","padding":"12px"}),
        html.Div([dcc.Graph(id="compact-bar",   config={"displayModeBar":False})],
                 style={"background":CARD,"borderRadius":"12px","padding":"12px"}),
        html.Div([dcc.Graph(id="sessions-chart",config={"displayModeBar":False})],
                 style={"background":CARD,"borderRadius":"12px","padding":"12px"}),
        html.Div([dcc.Graph(id="quality-gauge", config={"displayModeBar":False})],
                 style={"background":CARD,"borderRadius":"12px","padding":"12px"}),
    ], style={"display":"grid","gridTemplateColumns":"1fr 1fr 1fr",
              "gap":"12px","padding":"0 20px 20px"}),

    dcc.Interval(id="tick", interval=5000),
    html.Div(id="ts", style={"textAlign":"right","color":"#333",
                              "fontSize":"10px","padding":"0 24px 12px"}),
], style={"background":BG,"minHeight":"100vh","fontFamily":"monospace"})


@callback(
    Output("kpi-main",       "children"),
    Output("kpi-compact",    "children"),
    Output("cost-line",      "figure"),
    Output("route-donut",    "figure"),
    Output("saving-gauge",   "figure"),
    Output("compact-bar",    "figure"),
    Output("sessions-chart", "figure"),
    Output("quality-gauge",  "figure"),
    Output("ts",             "children"),
    Input("tick", "n_intervals")
)
def update(n):
    n  = n or 0
    db = get_db_stats()
    lm = get_log_metrics()

    total = max(lm["req_total"], 1)
    local_pct = round(lm["local_count"] / total * 100, 1)
    cache_pct = round(lm["cache_hits"]  / total * 100, 1)
    saved_pct = min(round((lm["local_count"]+lm["cache_hits"]) / total * 90, 1), 99.0)
    cost      = lm["cost_total"] or db["sess_cost"]
    quality   = round(lm["compact_quality_sum"] / max(lm["compact_quality_n"],1), 2) \
                if lm["compact_quality_n"] else 0.0
    fb_pct    = round(lm["compact_fallback"] / max(lm["compact_count"],1)*100, 1) \
                if lm["compact_count"] else 0

    # ── KPI row 1 ──
    kpi_main = html.Div([
        kpi("Запросов",     f"{total:,}",               "всего",                BLUE),
        kpi("Local %",       f"{local_pct}%",            "Ollama / бесплатно",    GREEN),
        kpi("Cache hits",    f"{cache_pct}%",            f"{lm['cache_hits']} hits",   TEAL),
        kpi("Сэкономлено",  f"{saved_pct:.0f}%",          "vs cloud-only",            GREEN),
        kpi("Расходы $",     f"${cost:.4f}",             "с начала сессии",      GOLD),
        kpi("Cache",         f"{db['cache_total']}",
            f"{db['cache_vecs']} векторов · +{db['cache_recent']}/h", BLUE),
    ], style={"display":"contents"})

    # ── KPI row 2 ──
    kpi_compact = html.Div([
        kpi("Compact runs",   f"{lm['compact_count']}",  "авто-сжатий",         PURPLE),
        kpi("Quality avg",
            f"{quality:.2f}" if quality else "—",
            "keyword_hit_rate",
            GREEN if quality >= 0.82 else RED),
        kpi("Fallback %",     f"{fb_pct}%",
            "gemini-flash upgrades",
            GOLD if fb_pct > 20 else GREEN),
        kpi("Сессий активно", f"{db['sess_active']}",     "за 24ч в SQLite",      TEAL),
        kpi("Msgs total",     f"{db['sess_msgs']}",      "сообщений в сессиях",   BLUE),
        kpi("Session cost",   f"${db['sess_cost']:.4f}", "суммарно",             GOLD),
    ], style={"display":"contents"})

    # ── Cost line ──
    times = lm["hist_times"] or [f"{i}:00" for i in range(8,18)]
    costs = lm["hist_cost"]  or [round(0.001+i*0.0004,4) for i in range(len(times))]
    fig_cost = go.Figure(go.Scatter(
        x=times, y=costs, mode="lines+markers",
        line=dict(color=BLUE,width=2), marker=dict(size=5,color=BLUE),
        fill="tozeroy", fillcolor="rgba(79,142,247,0.08)"
    ))
    fig_cost.update_layout(title="💰 Расходы по времени",
                           xaxis_title="Time",yaxis_title="$",**dark())

    # ── Routing donut ──
    ln = lm["local_count"] or 65
    cn = lm["cloud_count"] or 25
    hn = lm["cache_hits"]  or 10
    fig_route = go.Figure(go.Pie(
        labels=["🏠 Local (free)","☁️ Cloud ($)","💾 Cache (free)"],
        values=[ln,cn,hn], hole=0.55,
        marker_colors=[GREEN,BLUE,TEAL], textfont=dict(size=11)
    ))
    fig_route.update_layout(title="🔀 Routing mix",**dark())
    fig_route.add_annotation(
        text=f"{local_pct+cache_pct:.0f}%<br>FREE",
        x=0.5,y=0.5,showarrow=False,
        font=dict(size=16,color=GREEN,family="monospace")
    )

    # ── Saving gauge ──
    fig_save = go.Figure(go.Indicator(
        mode="gauge+number+delta", value=saved_pct,
        title={"text":"💪 Экономия %","font":{"color":"#aaa","size":13}},
        delta={"reference":90,"valueformat":".1f"},
        gauge={"axis":{"range":[0,100],"tickcolor":"#444"},
               "bar":{"color":GREEN,"thickness":0.25},"bgcolor":BG,
               "steps":[{"range":[0,50],"color":"#1a1a2e"},
                         {"range":[50,80],"color":"#1a2e1a"},
                         {"range":[80,100],"color":"#0d2e1a"}],
               "threshold":{"line":{"color":GOLD,"width":3},"value":90}},
        number={"suffix":"%","font":{"size":36,"color":GREEN}}
    ))
    fig_save.update_layout(paper_bgcolor=CARD,font=dict(color="#aaa"),
                           margin=dict(l=30,r=30,t=50,b=20))

    # ── Compact bar ──
    loc_c = lm["compact_count"] - lm["compact_fallback"]
    fb_c  = lm["compact_fallback"]
    fig_compact = go.Figure()
    fig_compact.add_trace(go.Bar(
        name="🏠 Local compact",x=["Auto Compact"],y=[loc_c],
        marker_color=GREEN,width=0.4))
    fig_compact.add_trace(go.Bar(
        name="⚡ Fallback→gemini",x=["Auto Compact"],y=[fb_c],
        marker_color=GOLD,width=0.4))
    if quality:
        fig_compact.add_trace(go.Scatter(
            name="Quality",x=["Auto Compact"],y=[quality*max(lm["compact_count"],1)],
            mode="markers",marker=dict(symbol="diamond",size=14,color=TEAL),yaxis="y2"))
    fig_compact.update_layout(
        title=f"🗜️ Auto Compact ({lm['compact_count']} total | q={quality:.2f})",
        barmode="stack",
        yaxis=dict(title="Runs"),
        yaxis2=dict(title="Quality",overlaying="y",side="right",range=[0,1]),
        legend=dict(orientation="h",y=-0.2), **dark()
    )

    # ── Sessions timeline ──
    rows = db["sess_rows"]
    if rows:
        s_ids  = [r[0][:8]+"…" for r in rows]
        s_msgs = [r[1] for r in rows]
        s_cost = [round(r[2]*1000,3) for r in rows]
        s_ago  = [f"{int((time.time()-r[3])//60)}m" if time.time()-r[3]<3600
                  else f"{int((time.time()-r[3])//3600)}h" for r in rows]
    else:
        s_ids=["demo-1","demo-2","demo-3"]; s_msgs=[24,8,41]
        s_cost=[0.12,0.04,0.31]; s_ago=["2m","15m","1h"]
    fig_sess = go.Figure()
    fig_sess.add_trace(go.Bar(
        name="Messages",x=s_ids,y=s_msgs,marker_color=BLUE,opacity=0.85,
        text=s_ago,textposition="outside",textfont=dict(size=9,color="#555")))
    fig_sess.add_trace(go.Scatter(
        name="Cost m$",x=s_ids,y=s_cost,mode="lines+markers",
        marker=dict(size=6,color=GOLD),line=dict(color=GOLD,width=1.5,dash="dot"),
        yaxis="y2"))
    fig_sess.update_layout(
        title=f"💬 Sessions (active={db['sess_active']} | avg={round(db['sess_msgs']/max(db['sess_active'],1),1)} msgs)",
        xaxis=dict(tickfont=dict(size=9)),
        yaxis=dict(title="Messages"),
        yaxis2=dict(title="Cost m$",overlaying="y",side="right"),
        legend=dict(orientation="h",y=-0.25), **dark()
    )

    # ── Quality gauge ──
    qv = quality*100
    qc = GREEN if qv>=82 else (GOLD if qv>=65 else RED)
    fig_q = go.Figure(go.Indicator(
        mode="gauge+number", value=qv,
        title={"text":f"🎯 Compact Quality<br>"
               f"<span style='font-size:10px;color:#555'>fallback: {fb_pct}%</span>",
               "font":{"color":"#aaa","size":12}},
        gauge={"axis":{"range":[0,100],"tickcolor":"#444"},
               "bar":{"color":qc,"thickness":0.28},"bgcolor":BG,
               "steps":[{"range":[0,65],"color":"#2e1a1a"},
                         {"range":[65,82],"color":"#2e2a1a"},
                         {"range":[82,100],"color":"#1a2e1a"}],
               "threshold":{"line":{"color":GREEN,"width":3},"value":82}},
        number={"suffix":"%","font":{"size":32,"color":qc}}
    ))
    fig_q.update_layout(paper_bgcolor=CARD,font=dict(color="#aaa"),
                        margin=dict(l=30,r=30,t=70,b=20))

    ts = f"Updated: {time.strftime('%H:%M:%S')}"
    return (kpi_main, kpi_compact, fig_cost, fig_route,
            fig_save, fig_compact, fig_sess, fig_q, ts)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8050)
    p.add_argument("--host", default="127.0.0.1")
    a = p.parse_args()
    print(f"⚡ TokenSaver Dashboard v5.0 → http://{a.host}:{a.port}")
    print(f"   DB: {DB_PATH}")
    print(f"   Log: {LOG_PATH}")
    app.run(host=a.host, port=a.port, debug=False)
