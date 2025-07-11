import os
import functions_framework
from flask import request, jsonify
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timezone

# Firebaseの初期化
# Initialize Firebase
# GOOGLE_APPLICATION_CREDENTIALS環境変数が設定されていれば、それが自動的に使用される
# If the GOOGLE_APPLICATION_CREDENTIALS environment variable is set, it will be used automatically.
try:
    firebase_admin.initialize_app()
    db = firestore.client()
    print("Firebase app initialized successfully.")
except Exception as e:
    print(f"Error initializing Firebase app: {e}")
    db = None

@functions_framework.http
def http_entry(req):
    """
    HTTP Cloud Function.
    Args:
        req (flask.Request): The request object.
    Returns:
        The response text, or any set of values that can be turned into a
        Response object using `make_response`.
    """
    # Firebaseクライアントが初期化されていない場合はエラーを返す
    if not db:
        return jsonify({"status": "error", "message": "Firestore client not initialized."}), 500

    # CORSプリフライトリクエストへの対応
    # Handle CORS preflight requests
    if req.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
            'Access-Control-Max-Age': '3600'
        }
        return ('', 204, headers)

    # CORSヘッダーをレスポンスに追加
    # Add CORS headers to the response
    headers = {
        'Access-Control-Allow-Origin': '*'
    }

    # POSTメソッド以外は許可しない
    # Disallow methods other than POST
    if req.method != 'POST':
        return jsonify({"status": "error", "message": "Method not allowed"}), 405, headers

    # リクエストボディからJSONデータを取得
    # Get JSON data from the request body
    try:
        data = req.get_json()
        if data is None:
            return jsonify({"status": "error", "message": "Invalid JSON"}), 400, headers
    except Exception as e:
        print(f"Error parsing JSON: {e}")
        return jsonify({"status": "error", "message": "Could not parse request body as JSON"}), 400, headers

    # --- 建築憲章v6.0に基づくバリデーション ---
    # --- Validation based on Architectural Charter v6.0 ---
    required_fields = ['title', 'sourceType', 'content']
    for field in required_fields:
        if field not in data:
            return jsonify({"status": "error", "message": f"Missing required field: {field}"}), 400, headers

    if not isinstance(data.get('content'), dict) or 'rawText' not in data.get('content'):
         return jsonify({"status": "error", "message": "Field 'content' must be an object with a 'rawText' key"}), 400, headers

    # --- Firestoreへのデータ保存処理 ---
    # --- Data saving process to Firestore ---
    try:
        # 建築憲章v6.0のスキーマに準拠したドキュメントを作成
        # Create a document compliant with the Architectural Charter v6.0 schema
        doc_to_add = {
            'title': data.get('title'),
            'sourceType': data.get('sourceType'),
            'description': data.get('description', ''), # オプショナル
            'keywords': data.get('keywords', []), # オプショナル
            'content': {
                'rawText': data['content'].get('rawText', ''),
                'structuredData': data['content'].get('structuredData', {})
            },
            'aiGenerated': { # AI処理用のプレースホルダ
                'categories': [],
                'tags': []
            },
            'status': 'received', # 初期ステータス
            'createdAt': datetime.now(timezone.utc),
            'updatedAt': datetime.now(timezone.utc)
        }

        # 'staging_articles'コレクションにドキュメントを追加
        # Add the document to the 'staging_articles' collection
        update_time, doc_ref = db.collection('staging_articles').add(doc_to_add)

        print(f"Document {doc_ref.id} added to staging_articles at {update_time}.")
        
        # 成功レスポンスを返す
        # Return a success response
        return jsonify({
            "status": "success",
            "message": "Article successfully ingested.",
            "documentId": doc_ref.id
        }), 201, headers

    except Exception as e:
        print(f"Error writing to Firestore: {e}")
        # エラーログ収集APIへの報告処理をここに追加することも可能
        # It's also possible to add error reporting to a central logging API here
        return jsonify({"status": "error", "message": "An internal error occurred while writing to the database."}), 500, headers
