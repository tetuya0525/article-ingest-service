# ==============================================================================
# Memory Library - Article Ingest Service
# Role:         Accepts new articles and places them in the staging collection.
# Version:      2.1 (Enhanced Logging / Debugging Version)
# Author:       心理 (Thinking Partner)
# Last Updated: 2025-07-11
# ==============================================================================
import os
from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import firestore
from datetime import datetime, timezone
import logging

# Pythonの標準ロギングを設定
# This allows logs to be clearly visible in Google Cloud Logging
logging.basicConfig(level=logging.INFO)

# Flaskアプリケーションを初期化
app = Flask(__name__)

# Firebaseの初期化
try:
    firebase_admin.initialize_app()
    db = firestore.client()
    app.logger.info("Firebase app initialized successfully.")
except Exception as e:
    app.logger.error(f"Error initializing Firebase app: {e}")
    db = None

# --- メインの処理関数 (再利用のため分離) ---
def process_ingestion_request(data):
    """
    データ投入リクエストの本体処理。バリデーションとFirestoreへの書き込みを行う。
    """
    # 建築憲章v6.0に基づくバリデーション
    required_fields = ['title', 'sourceType', 'content']
    for field in required_fields:
        if field not in data:
            return jsonify({"status": "error", "message": f"Missing required field: {field}"}), 400

    if not isinstance(data.get('content'), dict) or 'rawText' not in data.get('content'):
         return jsonify({"status": "error", "message": "Field 'content' must be an object with a 'rawText' key"}), 400

    # Firestoreへのデータ保存処理
    try:
        doc_to_add = {
            'title': data.get('title'), 'sourceType': data.get('sourceType'),
            'description': data.get('description', ''), 'keywords': data.get('keywords', []),
            'content': {
                'rawText': data['content'].get('rawText', ''),
                'structuredData': data['content'].get('structuredData', {})
            },
            'aiGenerated': {'categories': [], 'tags': []}, 'status': 'received',
            'createdAt': datetime.now(timezone.utc), 'updatedAt': datetime.now(timezone.utc)
        }
        update_time, doc_ref = db.collection('staging_articles').add(doc_to_add)
        app.logger.info(f"SUCCESS: Document {doc_ref.id} added to staging_articles.")
        return jsonify({
            "status": "success", "message": "Article successfully ingested.", "documentId": doc_ref.id
        }), 201
    except Exception as e:
        app.logger.error(f"FATAL: Error writing to Firestore: {e}")
        return jsonify({"status": "error", "message": "An internal error occurred while writing to the database."}), 500

# --- ルーティング ---

def handle_cors_and_preflight():
    """CORSとプリフライトリクエストを処理する共通関数"""
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization', 'Access-Control-Max-Age': '3600'
        }
        return ('', 204, headers)
    return None

def get_request_data():
    """リクエストからJSONデータを安全に取得する共通関数"""
    try:
        data = request.get_json()
        if data is None:
            return None, (jsonify({"status": "error", "message": "Invalid JSON"}), 400)
        return data, None
    except Exception as e:
        app.logger.error(f"Error parsing JSON: {e}")
        return None, (jsonify({"status": "error", "message": "Could not parse request body as JSON"}), 400)

@app.route('/', defaults={'path': ''}, methods=['POST', 'OPTIONS'])
@app.route('/<path:path>', methods=['POST', 'OPTIONS'])
def catch_all(path):
    """
    全てのパスへのリクエストをキャッチし、そのパスをログに出力する。
    これにより、API Gatewayが実際にどのURLを呼び出しているのかを特定する。
    """
    # ★★★ 最重要ログ ★★★
    # 実際にリクエストが来たパスをログに出力
    full_path = f"/{path}" if path else "/"
    app.logger.info(f"DIAGNOSTIC_LOG: Request received at path: '{full_path}'")

    # CORSプリフライトの処理
    preflight_response = handle_cors_and_preflight()
    if preflight_response:
        return preflight_response

    # Firebaseクライアントのチェック
    if not db:
        return jsonify({"status": "error", "message": "Firestore client not initialized."}), 500

    # データ取得
    data, error_response = get_request_data()
    if error_response:
        return error_response

    # 本体処理の呼び出し
    response, status_code = process_ingestion_request(data)
    
    # レスポンスにCORSヘッダーを追加
    response.headers.add('Access-Control-Allow-Origin', '*')
    
    return response, status_code
