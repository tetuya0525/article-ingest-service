# ==============================================================================
# Memory Library - Article Ingest Service
# Role:         Accepts new articles and places them in the staging collection.
# Version:      2.0 (Flask Architecture)
# Author:       心理 (Thinking Partner)
# Last Updated: 2025-07-11
# ==============================================================================
import os
from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import firestore
from datetime import datetime, timezone

# Flaskアプリケーションを初期化
app = Flask(__name__)

# Firebaseの初期化
try:
    firebase_admin.initialize_app()
    db = firestore.client()
    print("Firebase app initialized successfully.")
except Exception as e:
    print(f"Error initializing Firebase app: {e}")
    db = None

# ルートURL ('/') へのリクエストを処理するエンドポイント
@app.route('/', methods=['POST', 'OPTIONS'])
def handle_request():
    """
    HTTPリクエストを処理するメイン関数。
    CORSプリフライトリクエストとPOSTリクエストに対応。
    """
    # Firebaseクライアントが初期化されていない場合はエラー
    if not db:
        return jsonify({"status": "error", "message": "Firestore client not initialized."}), 500

    # CORSプリフライトリクエストへの対応
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
            'Access-Control-Max-Age': '3600'
        }
        return ('', 204, headers)

    # CORSヘッダーをレスポンスに追加
    headers = {
        'Access-Control-Allow-Origin': '*'
    }

    # POSTメソッド以外は許可しない
    if request.method != 'POST':
        return jsonify({"status": "error", "message": "Method not allowed"}), 405, headers

    # リクエストボディからJSONデータを取得
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"status": "error", "message": "Invalid JSON"}), 400, headers
    except Exception as e:
        print(f"Error parsing JSON: {e}")
        return jsonify({"status": "error", "message": "Could not parse request body as JSON"}), 400, headers

    # 建築憲章v6.0に基づくバリデーション
    required_fields = ['title', 'sourceType', 'content']
    for field in required_fields:
        if field not in data:
            return jsonify({"status": "error", "message": f"Missing required field: {field}"}), 400, headers

    if not isinstance(data.get('content'), dict) or 'rawText' not in data.get('content'):
         return jsonify({"status": "error", "message": "Field 'content' must be an object with a 'rawText' key"}), 400, headers

    # Firestoreへのデータ保存処理
    try:
        doc_to_add = {
            'title': data.get('title'),
            'sourceType': data.get('sourceType'),
            'description': data.get('description', ''),
            'keywords': data.get('keywords', []),
            'content': {
                'rawText': data['content'].get('rawText', ''),
                'structuredData': data['content'].get('structuredData', {})
            },
            'aiGenerated': {
                'categories': [],
                'tags': []
            },
            'status': 'received',
            'createdAt': datetime.now(timezone.utc),
            'updatedAt': datetime.now(timezone.utc)
        }

        update_time, doc_ref = db.collection('staging_articles').add(doc_to_add)

        print(f"Document {doc_ref.id} added to staging_articles at {update_time}.")
        
        return jsonify({
            "status": "success",
            "message": "Article successfully ingested.",
            "documentId": doc_ref.id
        }), 201, headers

    except Exception as e:
        print(f"Error writing to Firestore: {e}")
        return jsonify({"status": "error", "message": "An internal error occurred while writing to the database."}), 500, headers
