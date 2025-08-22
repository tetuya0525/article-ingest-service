import os
import secrets
import hashlib
from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import firestore
import logging

# --- 初期化 (Initialization) ---
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Firestoreクライアントをグローバル変数として保持 (遅延初期化)
db = None

def get_firestore_client():
    """
    Firestoreクライアントをシングルトンとして取得・初期化する。
    他の安定したサービスと同じ、堅牢な方式。
    """
    global db
    if db is None:
        try:
            firebase_admin.initialize_app()
            db = firestore.client()
            app.logger.info("Firebase app initialized successfully.")
        except Exception as e:
            app.logger.error(f"Error initializing Firebase app: {e}")
    return db

# --- メインロジック ---

@app.route('/generate', methods=['POST'])
def generate_api_key():
    """
    新しいAPIキーを生成し、ハッシュ化してDBに保存後、
    平文のキーを一度だけ返す。
    """
    db_client = get_firestore_client()
    if not db_client:
        return jsonify({"status": "error", "message": "データベース接続エラー"}), 500

    data = request.get_json()
    user_id = data.get('userId')
    label = data.get('label')

    if not user_id or not label:
        return jsonify({"status": "error", "message": "userIdとlabelは必須です。"}), 400

    try:
        plaintext_key = f"sk_{secrets.token_urlsafe(36)}"
        hashed_key = hashlib.sha256(plaintext_key.encode('utf-8')).hexdigest()
        key_data = {
            'userId': user_id,
            'label': label,
            'hashedKey': hashed_key,
            'status': 'active',
            'createdAt': firestore.SERVER_TIMESTAMP,
            'lastUsedAt': None
        }
        db_client.collection('api_keys').add(key_data)
        app.logger.info(f"新しいAPIキーを生成しました。 Label: {label}")
        return jsonify({
            "status": "success",
            "apiKey": plaintext_key,
            "message": "このキーは一度しか表示されません。安全な場所に保管してください。"
        }), 201

    except Exception as e:
        app.logger.error(f"APIキーの生成中にエラーが発生しました: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Internal Server Error"}), 500


@app.route('/revoke', methods=['POST'])
def revoke_api_key():
    """
    指定されたAPIキー(のドキュメントID)を無効化する。
    """
    db_client = get_firestore_client()
    if not db_client:
        return jsonify({"status": "error", "message": "データベース接続エラー"}), 500
        
    data = request.get_json()
    key_id = data.get('keyId')
    user_id = data.get('userId')

    if not key_id or not user_id:
        return jsonify({"status": "error", "message": "keyIdとuserIdは必須です。"}), 400

    try:
        key_ref = db_client.collection('api_keys').document(key_id)
        key_doc = key_ref.get()

        if not key_doc.exists:
            return jsonify({"status": "error", "message": "指定されたキーが見つかりません。"}), 404
        
        if key_doc.to_dict().get('userId') != user_id:
            return jsonify({"status": "error", "message": "このキーを無効化する権限がありません。"}), 403

        key_ref.update({'status': 'revoked'})
        app.logger.info(f"APIキーを無効化しました。Key ID: {key_id}")
        return jsonify({"status": "success", "message": "APIキーを無効化しました。"}), 200

    except Exception as e:
        app.logger.error(f"APIキーの無効化中にエラーが発生しました: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Internal Server Error"}), 500


if __name__ == "__main__":
    # This block is for local development and not used in Cloud Run
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
