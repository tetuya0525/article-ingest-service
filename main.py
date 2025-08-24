# ==============================================================================
# Memory Library - Article Ingest Service
# main.py (v1.0 Initial Build)
#
# Role:         Gatewayからのリクエストを受け、記事データを検証・初期化し、
#               ステージング用のDBコレクションに保存する。
# Version:      1.0
# Last Updated: 2025-08-24
# ==============================================================================
import os
import json
import logging
from functools import wraps
from flask import Flask, request, jsonify

import firebase_admin
from firebase_admin import firestore
import google.auth.transport.requests
from google.oauth2 import id_token

# --- 初期化 (Initialization) ---
app = Flask(__name__)

# --- ロギング設定 (構造化) ---
def setup_logging():
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)

def log_structured(level, message, **kwargs):
    log_data = {"message": message, "severity": level, **kwargs}
    app.logger.info(json.dumps(log_data))

# --- Firestore 初期化 (シングルトン) ---
db = None
def get_firestore_client():
    global db
    if db is None:
        try:
            if not firebase_admin._apps:
                firebase_admin.initialize_app()
            db = firestore.client()
            log_structured('INFO', "Firebase app initialized successfully.")
        except Exception as e:
            log_structured('CRITICAL', "Firebaseの初期化に失敗しました", error=str(e))
            raise
    return db

# --- サービス間認証デコレーター ---
def service_auth_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"status": "error", "message": "認証が必要です"}), 401
        
        token = auth_header.split('Bearer ')[1]
        try:
            id_token.verify_oauth2_token(token, google.auth.transport.requests.Request())
        except ValueError as e:
            log_structured('WARNING', "無効な認証トークンです", error=str(e))
            return jsonify({"status": "error", "message": "無効な認証トークンです"}), 403
        
        return f(*args, **kwargs)
    return decorated_function

# --- バリデーション関数 ---
def validate_article_data(data):
    """投入される記事データの必須項目を検証する"""
    if not data:
        return False, "リクエストボディにJSONデータが含まれていません。"
    
    required_fields = ['title', 'sourceType', 'content']
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        return False, f"必須フィールドが不足しています: {', '.join(missing_fields)}"
    
    if not isinstance(data.get('content'), dict) or 'rawText' not in data.get('content'):
        return False, "contentフィールドは'rawText'を含むオブジェクトである必要があります。"
        
    if not data.get('title').strip():
        return False, "titleフィールドは空にできません。"

    return True, None

# --- メインロジック ---
@app.route('/', methods=['POST'])
@service_auth_required
def ingest_article():
    """記事データを受け取り、ステージングDBに保存する"""
    try:
        db_client = get_firestore_client()
        data = request.get_json()

        # 入力データの検証
        is_valid, error_message = validate_article_data(data)
        if not is_valid:
            log_structured('WARNING', "無効なデータでの投入リクエスト", error=error_message, received_data=data)
            return jsonify({"status": "error", "message": error_message}), 400

        # Firestoreに保存するドキュメントを作成
        # 建築憲章スキーマをベースに、ワークフロー用のメタデータを付与 [cite: 382-383]
        article_doc = {
            'title': data.get('title'),
            'sourceType': data.get('sourceType'),
            'description': data.get('description', ''),
            'keywords': data.get('keywords', []),
            'content': {
                'rawText': data['content'].get('rawText'),
                'structuredData': data['content'].get('structuredData', {})
            },
            'aiGenerated': {}, # この段階では空
            'status': 'received', # ★ ワークフローの初期ステータス
            'createdAt': firestore.SERVER_TIMESTAMP,
            'updatedAt': firestore.SERVER_TIMESTAMP
        }
        
        # staging_articlesコレクションにドキュメントを追加
        update_time, doc_ref = db_client.collection('staging_articles').add(article_doc)
        doc_id = doc_ref.id
        
        log_structured('INFO', "新しい記事をステージングしました", document_id=doc_id, title=article_doc['title'])

        return jsonify({
            "status": "success",
            "message": "記事データを受け付けました。",
            "documentId": doc_id
        }), 201

    except Exception as e:
        log_structured('ERROR', "記事の投入処理中に予期せぬエラー", error=str(e), exc_info=True)
        return jsonify({"status": "error", "message": "Internal Server Error"}), 500

# --- ヘルスチェック ---
@app.route('/health', methods=['GET'])
def health_check():
    """ヘルスチェックエンドポイント"""
    try:
        # DB接続のみを確認
        get_firestore_client()
        return jsonify({"status": "healthy"}), 200
    except Exception as e:
        log_structured('ERROR', "ヘルスチェック失敗", error=str(e))
        return jsonify({"status": "unhealthy", "error": "Database connection failed"}), 503

# --- 起動 ---
if __name__ == "__main__":
    setup_logging()
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
