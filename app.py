import streamlit as st
from st_supabase_connection import SupabaseConnection
import pandas as pd
import datetime
import streamlit_authenticator as stauth

# ページ基本設定
st.set_page_config(page_title="勉強管理システム", layout="wide")

# Supabase接続
try:
    conn = st.connection("supabase", type=SupabaseConnection)
except:
    st.error("データベース接続エラー。secrets.tomlを確認してください。")
    st.stop()

# --- 1. データ取得関数 ---
@st.cache_data(ttl=60)
def get_all_credentials():
    try:
        res = conn.table("users").select("username, name, password").execute()
        credentials = {"usernames": {}}
        for row in res.data:
            credentials["usernames"][row["username"]] = {
                "name": row["name"],
                "password": row["password"]
            }
        return credentials
    except: return {"usernames": {}}

def get_user_config(username):
    try:
        res = conn.table("config").select("*").eq("username", username).execute()
        if res.data:
            d = res.data[0]
            return str(d["exam_name"]), datetime.date.fromisoformat(str(d["exam_date"])), int(d["goal_hours"])
    except: pass
    return "長期目標", datetime.date(2028, 3, 31), 1000

def get_user_subjects(username):
    try:
        res = conn.table("user_subjects").select("subject_name, color").eq("username", username).execute()
        if res.data:
            return {r["subject_name"]: r["color"] for r in res.data}
    except: pass
    return {"Python": "#c68eff", "基本情報技術者": "#ff8ec6", "その他": "#ffc68e"}

# --- 2. 認証 ---
credentials = get_all_credentials()
authenticator = stauth.Authenticate(
    credentials, 
    "study_session", 
    st.secrets.get("auth_key", "default"), 
    cookie_expiry_days=30
)

# --- 3. メイン処理 ---
name, auth_status, username = authenticator.login("main")

if auth_status:
    # 冒頭にタイトルを表示
    st.title("勉強管理")

    # データ同期
    EX_NAME, EX_DATE, GOAL_H = get_user_config(username)
    SUBJECTS = get_user_subjects(username)
    
    # 勉強記録とイベントの読み取り
    log_res = conn.table("logs").select("*").eq("username", username).execute()
    df_log = pd.DataFrame(log_res.data)
    
    event_res = conn.table("events").select("*").eq("username", username).order("event_date").execute()
    df_events = pd.DataFrame(event_res.data)

    st.sidebar.write(f"ユーザー: {name}")
    authenticator.logout("ログアウト", "sidebar")

    # サイドバー：総合的な勉強目標の設定
    with st.sidebar.expander("全体の目標設定"):
        new_name = st.text_input("目標の名前", EX_NAME)
        new_date = st.date_input("最終目標日", EX_DATE)
        new_goal = st.number_input("目標総時間(h)", value=int(GOAL_H))
        if st.button("全体目標を更新"):
            conn.table("config").upsert({
                "username": username, "exam_name": new_name,
                "exam_date": str(new_date), "goal_hours": new_goal
            }).execute()
            st.rerun()

    # サイドバー：個別の検定イベント管理
    with st.sidebar.expander("検定予定の追加・管理"):
        ev_name = st.text_input("検定名")
        ev_date = st.date_input("試験予定日", datetime.date.today())
        if st.button("イベント登録"):
            if ev_name:
                conn.table("events").insert({"username": username, "event_name": ev_name, "event_date": str(ev_date)}).execute()
                st.rerun()
        
        if not df_events.empty:
            st.divider()
            for _, ev in df_events.iterrows():
                ec1, ec2 = st.columns([3, 1])
                ec1.write(f"{ev['event_name']}")
                if ec2.button("削除", key=f"ev_del_{ev['id']}"):
                    conn.table("events").delete().eq("id", ev['id']).execute()
                    st.rerun()

    # サイドバー：新規学習記録
    st.sidebar.divider()
    in_date = st.sidebar.date_input("実施日", datetime.date.today())
    in_sub = st.sidebar.selectbox("教科", list(SUBJECTS.keys()))
    in_hour = st.sidebar.number_input("学習時間(h)", min_value=0.1, step=0.5)
    in_note = st.sidebar.text_area("内容メモ")
    if st.sidebar.button("記録を保存"):
        conn.table("logs").insert({"username": username, "date": str(in_date), "hours": in_hour, "subject": in_sub, "content": in_note}).execute()
        st.rerun()

    # --- メインエリア：進捗状況 ---
    st.header(EX_NAME)
    
    # 総合進捗メトリクス
    m1, m2, m3 = st.columns(3)
    total_h = df_log["hours"].sum() if not df_log.empty else 0
    days_left = (EX_DATE - datetime.date.today()).days
    prog = min(100, int((total_h / GOAL_H) * 100)) if GOAL_H > 0 else 0
    
    m1.metric("最終期限まで", f"{max(0, days_left)} 日")
    m2.metric("総勉強時間", f"{total_h:.1f} / {GOAL_H}h")
    m3.metric("進捗率", f"{prog}%")
    st.progress(prog / 100)

    st.divider()

    # 個別検定のカウントダウン
    st.subheader("検定カウントダウン")
    if not df_events.empty:
        # 登録順に表示
        ev_cols = st.columns(len(df_events[:4]))
        for i, (_, ev) in enumerate(df_events[:4].iterrows()):
            d_left = (datetime.date.fromisoformat(ev['event_date']) - datetime.date.today()).days
            ev_cols[i].metric(ev['event_name'], f"{max(0, d_left)} 日")
    else:
        st.caption("サイドバーから検定予定を追加すると、ここにカウントダウンが表示されます。")

    st.divider()

    # グラフと管理
    tab1, tab2, tab3 = st.tabs(["学習推移グラフ", "履歴の編集・削除", "教科別詳細"])
    
    with tab1:
        if not df_log.empty:
            chart_data = df_log.groupby(["date", "subject"])["hours"].sum().unstack().fillna(0)
            colors = [SUBJECTS.get(s, "#cccccc") for s in chart_data.columns]
            st.bar_chart(chart_data, color=colors)
        else:
            st.info("まだ学習記録がありません。")

    with tab2:
        if not df_log.empty:
            sorted_log = df_log.sort_values("date", ascending=False)
            for _, row in sorted_log.iterrows():
                with st.expander(f"{row['date']} | {row['subject']} | {row['hours']}h"):
                    c1, c2 = st.columns([4, 1])
                    with c1:
                        edit_c = st.text_input("内容編集", value=row["content"], key=f"c_{row['id']}")
                        edit_h = st.number_input("時間編集", value=float(row["hours"]), step=0.5, key=f"h_{row['id']}")
                    with c2:
                        if st.button("更新", key=f"upd_{row['id']}"):
                            conn.table("logs").update({"content": edit_c, "hours": edit_h}).eq("id", row["id"]).execute()
                            st.rerun()
                        if st.button("削除", key=f"del_{row['id']}"):
                            conn.table("logs").delete().eq("id", row["id"]).execute()
                            st.rerun()

    with tab3:
        if not df_log.empty:
            target = st.selectbox("分析する教科を選択", list(SUBJECTS.keys()))
            sub_df = df_log[df_log["subject"] == target]
            if not sub_df.empty:
                st.line_chart(sub_df.set_index("date")["hours"])
            else:
                st.write("この教科の記録はありません。")

elif auth_status is False:
    st.error("ユーザー名またはパスワードが正しくありません")