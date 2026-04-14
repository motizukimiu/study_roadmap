import streamlit as st
from st_supabase_connection import SupabaseConnection
import pandas as pd
import datetime
import streamlit_authenticator as stauth

# ページ基本設定
st.set_page_config(page_title="勉強記録", layout="wide")

# --- 0. データベース接続 ---
try:
    conn = st.connection(
        "supabase",
        type=SupabaseConnection,
        url=st.secrets["connections"]["supabase"]["url"],
        key=st.secrets["connections"]["supabase"]["key"]
    )
except Exception as e:
    st.error(f"データベース接続エラー: {e}")
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
    except Exception:
        return {"usernames": {}}

def get_user_config(username):
    try:
        res = conn.table("config").select("*").eq("username", username).execute()
        if res.data:
            d = res.data[0]
            return str(d["exam_name"]), datetime.date.fromisoformat(str(d["exam_date"])), int(d["goal_hours"])
    except Exception:
        pass
    return "長期目標", datetime.date(2028, 3, 31), 1000

def get_user_subjects(username):
    try:
        res = conn.table("user_subjects").select("id, subject_name, color").eq("username", username).execute()
        if res.data and len(res.data) > 0:
            return pd.DataFrame(res.data)
    except Exception:
        pass
    return pd.DataFrame([
        {"id": 0, "subject_name": "Python", "color": "#c68eff"},
        {"id": 1, "subject_name": "基本情報技術者", "color": "#ff8ec6"}
    ])

# --- 2. 認証処理 ---
credentials = get_all_credentials()
authenticator = stauth.Authenticate(
    credentials, 
    "study_session", 
    st.secrets.get("auth_key", "default_key_1234"), 
    cookie_expiry_days=30
)

authenticator.login("main")

auth_status = st.session_state.get("authentication_status")
name = st.session_state.get("name")
username = st.session_state.get("username")

# --- 3. メイン処理 ---
if auth_status:
    st.title("勉強記録")

    # データの最新化
    EX_NAME, EX_DATE, GOAL_H = get_user_config(username)
    df_subjects = get_user_subjects(username)
    subject_colors = dict(zip(df_subjects["subject_name"], df_subjects["color"]))
    
    log_res = conn.table("logs").select("*").eq("username", username).execute()
    df_log = pd.DataFrame(log_res.data)
    
    event_res = conn.table("events").select("*").eq("username", username).order("event_date").execute()
    df_events = pd.DataFrame(event_res.data)

    # --- サイドバー設定 ---
    st.sidebar.subheader(f"ユーザー: {name}")
    authenticator.logout("ログアウト", "sidebar")

    # A. 教科の編集（追加・削除）
    with st.sidebar.expander("教科の編集"):
        st.write("新規教科を追加")
        new_sub = st.text_input("教科名を入力")
        new_color = st.color_picker("ラベルの色を選択", "#00f900")
        if st.button("追加実行"):
            if new_sub:
                conn.table("user_subjects").insert({
                    "username": username, "subject_name": new_sub, "color": new_color
                }).execute()
                st.rerun()

        st.divider()
        st.write("既存教科の削除")
        for _, row in df_subjects.iterrows():
            c1, c2 = st.columns([3, 1])
            c1.caption(row["subject_name"])
            if c2.button("削", key=f"sub_del_{row['id']}"):
                conn.table("user_subjects").delete().eq("id", row["id"]).execute()
                st.rerun()

    # B. 全体の目標設定
    with st.sidebar.expander("全体の目標設定"):
        new_name = st.text_input("目標の名前", EX_NAME)
        new_date = st.date_input("最終目標日", EX_DATE)
        new_goal = st.number_input("目標総時間(h)", value=int(GOAL_H), min_value=1)
        if st.button("全体目標を更新"):
            conn.table("config").upsert({
                "username": username, "exam_name": new_name,
                "exam_date": str(new_date), "goal_hours": new_goal
            }).execute()
            st.rerun()

    # C. 検定イベント管理
    with st.sidebar.expander("検定・イベント管理"):
        ev_name = st.text_input("検定名")
        ev_date = st.date_input("試験予定日", datetime.date.today())
        if st.button("イベント登録"):
            if ev_name:
                conn.table("events").insert({"username": username, "event_name": ev_name, "event_date": str(ev_date)}).execute()
                st.rerun()
        
        if not df_events.empty:
            for _, ev in df_events.iterrows():
                ec1, ec2 = st.columns([3, 1])
                ec1.caption(f"{ev['event_name']}")
                if ec2.button("×", key=f"ev_del_{ev['id']}"):
                    conn.table("events").delete().eq("id", ev['id']).execute()
                    st.rerun()

    # D. 学習記録入力
    st.sidebar.divider()
    st.sidebar.subheader("学習記録の入力")
    in_date = st.sidebar.date_input("実施日", datetime.date.today())
    # 取得した教科データからプルダウンを作成
    in_sub = st.sidebar.selectbox("教科", df_subjects["subject_name"].tolist())
    in_hour = st.sidebar.number_input("時間(h)", min_value=0.1, max_value=24.0, step=0.5)
    in_note = st.sidebar.text_area("内容メモ")
    
    if st.sidebar.button("記録を保存"):
        conn.table("logs").insert({
            "username": username, "date": str(in_date), 
            "hours": in_hour, "subject": in_sub, "content": in_note
        }).execute()
        st.toast("記録しました")
        st.rerun()

    # --- メインエリア：進捗状況 ---
    st.header(f"目標: {EX_NAME}")
    
    m1, m2, m3 = st.columns(3)
    total_h = df_log["hours"].sum() if not df_log.empty else 0
    days_left = (EX_DATE - datetime.date.today()).days
    prog = min(100, int((total_h / GOAL_H) * 100)) if GOAL_H > 0 else 0
    
    m1.metric("期限まで", f"{max(0, days_left)} 日")
    m2.metric("総勉強時間", f"{total_h:.1f} / {GOAL_H}h")
    m3.metric("進捗率", f"{prog}%")
    st.progress(prog / 100)

    # 検定カウントダウン表示
    if not df_events.empty:
        st.subheader("検定カウントダウン")
        ev_cols = st.columns(len(df_events[:4]))
        for i, (_, ev) in enumerate(df_events[:4].iterrows()):
            d_left = (datetime.date.fromisoformat(ev['event_date']) - datetime.date.today()).days
            ev_cols[i].metric(ev['event_name'], f"{max(0, d_left)} 日")

    st.divider()

    # タブエリア
    tab1, tab2, tab3 = st.tabs(["学習推移", "履歴編集", "教科別詳細"])
    
    with tab1:
        if not df_log.empty:
            chart_data = df_log.groupby(["date", "subject"])["hours"].sum().unstack().fillna(0)
            # 各教科の色をリスト化して適用
            colors = [subject_colors.get(s, "#cccccc") for s in chart_data.columns]
            st.bar_chart(chart_data, color=colors)
        else:
            st.info("データがありません")

    with tab2:
        if not df_log.empty:
            sorted_log = df_log.sort_values("date", ascending=False)
            for _, row in sorted_log.iterrows():
                with st.expander(f"{row['date']} | {row['subject']} | {row['hours']}h"):
                    c1, c2 = st.columns([4, 1])
                    with c1:
                        edit_c = st.text_input("内容編集", value=row["content"], key=f"c_{row['id']}")
                        edit_h = st.number_input("時間編集", value=float(row["hours"]), min_value=0.1, key=f"h_{row['id']}")
                    with c2:
                        if st.button("更新", key=f"upd_{row['id']}"):
                            conn.table("logs").update({"content": edit_c, "hours": edit_h}).eq("id", row["id"]).execute()
                            st.rerun()
                        if st.button("削除", key=f"del_{row['id']}"):
                            conn.table("logs").delete().eq("id", row["id"]).execute()
                            st.rerun()

    with tab3:
        if not df_log.empty:
            target = st.selectbox("分析する教科を選択", df_subjects["subject_name"].tolist())
            sub_df = df_log[df_log["subject"] == target]
            if not sub_df.empty:
                st.line_chart(sub_df.set_index("date")["hours"])
                st.write(f"{target} の合計学習時間: {sub_df['hours'].sum():.1f} 時間")

elif auth_status is False:
    st.error("ユーザー名またはパスワードが正しくありません")
elif auth_status is None:
    st.warning("ログインしてください")