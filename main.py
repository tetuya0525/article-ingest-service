# ==============================================================================
# Memory Library - Article Ingest Service
# main.py (v1.3 Production)
#
# Role:         Gatewayからのリクエストを受け、記事データを検証・初期化し、
#               ステージング用のDBコレクションに保存する。
#               ログは中央ログ集約サービスへ送信し、起動時の堅牢性を確保。
# Version:      1.3
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
from flask import Flask, jsonify, request, current_app
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
# Centralized Structured Logging
# ==============================================================================
def log_structured(level: str, message: str, **kwargs):
    """構造化ログを生成し、ロギングを行う"""
    log_payload = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "service": Config.SERVICE_NAME,
        "severity": level.upper(),
        "message": message,
        **kwargs,
    }
    
    # Gunicorn/FlaskのロガーにJSONとして出力する
    # これによりCloud Runのログに確実に記録される
    log_level_map = {
        "INFO": current_app.logger.info,
        "WARNING": current_app.logger.warning,
        "ERROR": current_app.logger.error,
        "CRITICAL": current_app.logger.critical,
    }
    logger_func = log_level_map.get(level.upper(), current_app.logger.info)
    logger_func(json.dumps(log_payload, default=str))

    # 追加で中央ログ集約サービスへも送信を試みる
    if Config.LOG_AGGREGATOR_URL:
        try:
            requests.post(Config.LOG_AGGREGATOR_URL, json=log_payload, timeout=2.0)
        except requests.RequestException as e:
            # 送信失敗は警告として記録するが、処理は続行する
            current_app.logger.warning(
                f"Failed to send log to aggregator: {e}",
                extra={"aggregator_url": Config.LOG_AGGREGATOR_URL}
            )


# ==============================================================================
# Application Factory
# ==============================================================================
def create_app(config_object: Config) -> Flask:
    """Flaskアプリケーションインスタンスを生成・設定して返す"""
    app = Flask(__name__)

    # --- 1. Gunicornロガーとの統合を最初に設定 ---
    gunicorn_logger = logging.getLogger("gunicorn.error")
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)

    # --- 2. 設定の読み込みと検証 ---
    try:
        required = ["GCP_PROJECT_ID", "AUDIENCE", "LOG_AGGREGATOR_URL"]
        missing = [v for v in required if not getattr(config_object, v)]
        if missing:
            raise ValueError(f"不足している必須環境変数があります: {', '.join(missing)}")
        
        app.config.from_object(config_object)
        
        # appコンテキスト内でロギング
        with app.app_context():
            log_structured("INFO", "アプリケーション設定の読み込みが完了しました。")

    except Exception as e:
        # このログが今度こそCloud Runに表示されるはず
        app.logger.critical(f"FATAL: 設定読み込み中にエラー: {e}", exc_info=True)
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
                "content": { "rawText": data["content"].get("rawText"), "structuredData": data["content"].get("structuredData", {}), },
                "aiGenerated": {}, "status": "received",
                "createdAt": firestore.SERVER_TIMESTAMP, "updatedAt": firestore.SERVER_TIMESTAMP,
            }
            _, doc_ref = db.collection(app.config["STAGING_COLLECTION"]).add(article_doc)
            doc_id = doc_ref.id

            log_structured("INFO", "新しい記事をステージングしました", document_id=doc_id, title=article_doc["title"])
            return jsonify({ "status": "success", "message": "記事データを受け付けました。", "documentId": doc_id, }), 201

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
    # ローカル実行時はGunicornロガーが存在しないため、基本的なハンドラを設定
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)
    app.run(host="0.0.0.0", port=port, debug=True)

