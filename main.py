# ==============================================================================
# Memory Library - Article Ingest Service
# main.py (v1.2 Production)
#
# Role:         Gatewayからのリクエストを受け、記事データを検証・初期化し、
#               ステージング用のDBコレクションに保存する。
#               ログは中央ログ集約サービスへ送信する。
# Version:      1.2
# Last Updated: 2025-09-02
# ==============================================================================

# --- 標準ライブラリ ---
import json
import logging
import os
import sys
from datetime import datetime
from functools import wraps

# --- サードパーティライブラリ ---
import firebase_admin
import google.auth.transport.requests
import requests
from firebase_admin import firestore
from flask import Flask, jsonify, request
from google.oauth2 import id_token


# ==============================================================================
# Configuration
# ==============================================================================
class Config:
    """アプリケーション設定を環境変数から読み込む"""
    GCP_PROJECT_ID: str = os.environ.get("GCP_PROJECT_ID")
    AUDIENCE: str = os.environ.get("AUDIENCE")
    STAGING_COLLECTION: str = os.environ.get("STAGING_COLLECTION", "staging_articles")
    LOG_AGGREGATOR_URL: str = os.environ.get("LOG_AGGREGATOR_URL")
    SERVICE_NAME: str = os.environ.get("K_SERVICE", "article-ingest-service")


# ==============================================================================
# Centralized Structured Logging
# ==============================================================================
# Gunicornからの起動時に備え、基本的なlogging設定を先に行う
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

def log_structured(level: str, message: str, **kwargs):
    """構造化ログを指定されたURLに送信する。失敗した場合は標準出力にフォールバックする。"""
    log_payload = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "service": Config.SERVICE_NAME,
        "severity": level.upper(),
        "message": message,
        **kwargs,
    }
    
    if Config.LOG_AGGREGATOR_URL:
        try:
            requests.post(Config.LOG_AGGREGATOR_URL, json=log_payload, timeout=2.0)
        except requests.RequestException as e:
            # フォールバック: 集約サービスに失敗した場合は標準出力にログを書き出す
            print(f"Failed to send log to aggregator: {e}", file=sys.stderr)
            print(json.dumps(log_payload), file=sys.stderr)
    else:
        # ローカル開発用: URLが設定されていなければ標準出力に書き出す
        print(json.dumps(log_payload))


# ==============================================================================
# Client Initialization (Lazy Loading)
# ==============================================================================
db_client: firestore.Client = None

def get_firestore_client() -> firestore.Client:
    """Firestoreクライアントをシングルトンとして初期化・取得する"""
    global db_client
    if db_client is None:
        try:
            if not firebase_admin._apps:
                firebase_admin.initialize_app()
            db_client = firestore.client()
            log_structured("INFO", "Firestoreクライアントの初期化に成功しました。")
        except Exception as e:
            log_structured("CRITICAL", "Firebaseの初期化に失敗", error=str(e), exc_info=True)
            raise
    return db_client


# ==============================================================================
# Application Factory
# ==============================================================================
def create_app(config_object: Config) -> Flask:
    """Flaskアプリケーションインスタンスを生成・設定して返す"""
    app = Flask(__name__)

    # --- 設定の読み込みと検証 ---
    try:
        required = ["GCP_PROJECT_ID", "AUDIENCE", "LOG_AGGREGATOR_URL"]
        missing = [v for v in required if not getattr(config_object, v)]
        if missing:
            raise ValueError(f"不足している必須環境変数があります: {', '.join(missing)}")
        
        app.config.from_object(config_object)
        log_structured("INFO", "アプリケーション設定の読み込みが完了しました。")

    except Exception as e:
        log_structured("CRITICAL", "FATAL: 設定読み込み中にエラー", error=str(e), exc_info=True)
        raise
    
    # --- Decorators ---
    def service_auth_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                return jsonify({"status": "error", "message": "認証ヘッダーがありません"}), 401
            
            token = auth_header.split("Bearer ")[1]
            try:
                id_token.verify_oauth2_token(
                    token,
                    google.auth.transport.requests.Request(),
                    audience=app.config["AUDIENCE"],
                )
            except ValueError as e:
                log_structured("WARNING", "無効な認証トークンです", error=str(e))
                return jsonify({"status": "error", "message": "無効な認証トークンです"}), 403
            
            return f(*args, **kwargs)
        return decorated_function

    # --- Validation ---
    def validate_article_data(data):
        if not data: return False, "リクエストボディにJSONデータが含まれていません。"
        required = ["title", "sourceType", "content"]
        missing = [f for f in required if f not in data]
        if missing: return False, f"必須フィールドが不足: {', '.join(missing)}"
        if not isinstance(data.get("content"), dict) or "rawText" not in data.get("content"):
            return False, "contentフィールドは'rawText'を含むオブジェクトである必要があります。"
        if not data.get("title", "").strip(): return False, "titleフィールドは空にできません。"
        return True, None

    # --- API Endpoints ---
    @app.route("/", methods=["POST"])
    @service_auth_required
    def ingest_article():
        data = request.get_json(silent=True)
        try:
            is_valid, error_message = validate_article_data(data)
            if not is_valid:
                log_structured("WARNING", "無効なデータでの投入リクエスト", error=error_message, received_data=data)
                return jsonify({"status": "error", "message": error_message}), 400

            db = get_firestore_client()
            article_doc = {
                "title": data.get("title"), "sourceType": data.get("sourceType"),
                "description": data.get("description", ""), "keywords": data.get("keywords", []),
                "content": {
                    "rawText": data["content"].get("rawText"),
                    "structuredData": data["content"].get("structuredData", {}),
                },
                "aiGenerated": {}, "status": "received",
                "createdAt": firestore.SERVER_TIMESTAMP, "updatedAt": firestore.SERVER_TIMESTAMP,
            }

            _, doc_ref = db.collection(app.config["STAGING_COLLECTION"]).add(article_doc)
            doc_id = doc_ref.id

            log_structured("INFO", "新しい記事をステージングしました", document_id=doc_id, title=article_doc["title"])
            return jsonify({
                "status": "success", "message": "記事データを受け付けました。", "documentId": doc_id,
            }), 201

        except Exception as e:
            log_structured("ERROR", "記事の投入処理中に予期せぬエラー", error=str(e), exc_info=True, request_data=data)
            return jsonify({"status": "error", "message": "Internal Server Error"}), 500

    @app.route("/health", methods=["GET"])
    def health_check():
        return jsonify({"status": "healthy"}), 200

    return app

# ==============================================================================
# Gunicorn Entrypoint
# ==============================================================================
config = Config()
app = create_app(config)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True)

