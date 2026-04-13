import streamlit as st
from st_supabase_connection import SupabaseConnection
import pandas as pd

# --- ページ設定 ---
st.set_page_config(page_title="学習進捗管理アプリ", layout="centered")

# --- 1. データベース接続 (Secretsから読み込み) ---
# Secrets側の [connections.supabase] という名前と一致させています
try:
    conn = st.connection("supabase", type=SupabaseConnection)
except Exception as e:
    st.error("データベース接続エラー。Secretsの設定を確認してください。")
    st.stop()

# --- 2. 認証機能 (auth_key) ---
# Secrets側に書いた auth_key = "hama1_D2_4231" を読み込みます
def check_password():
    """認証に成功したら True を返す"""
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if st.session_state["password_correct"]:
        return True

    st.title("🛡️ セキュリティログイン")
    password = st.text_input("認証キーを入力してください", type="password")
    
    # Secretsからauth_keyを取得
    correct_password = st.secrets.get("auth_key")

    if st.button("ログイン"):
        if password == correct_password:
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("認証キーが正しくありません")
    return False

# 認証チェックの実行
if not check_password():
    st.stop()

# --- 3. メインコンテンツ (ログイン後) ---
st.title("📚 学習ロードマップ管理")
st.write("ログインに成功しました！ここに学習記録のグラフやヒートマップを表示します。")

# テストとしてSupabaseからデータを取得してみる（テーブル名が 'study_logs' の場合）
try:
    df = conn.query("*", table="study_logs", ttl="0").execute()
    if df.data:
        st.write("### 現在の学習ログ")
        st.dataframe(pd.DataFrame(df.data))
    else:
        st.info("まだデータがありません。")
except Exception as e:
    st.warning("データの取得には失敗しました（テーブルが未作成の可能性があります）が、接続自体は成功しています！")

# --- ログアウトボタン ---
if st.sidebar.button("ログアウト"):
    st.session_state["password_correct"] = False
    st.rerun()