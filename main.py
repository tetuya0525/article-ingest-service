# main.py (Simplest Flask App Test)
# ==============================================================================
# このサービスが正しく起動し、ゲートウェイから到達可能かを確認するための、
# 世界で最もシンプルなテスト用プログラムです。
# ==============================================================================
import os
from flask import Flask, jsonify

# Flaskアプリケーションを「app」という名前で作成
app = Flask(__name__)

# ルートパス("/")へのリクエストを処理する関数
@app.route("/", methods=['GET', 'POST'])
def hello_world():
    """
    呼び出されたら、挨拶を返すだけの、非常にシンプルな関数。
    """
    print("Simplest Flask app was called successfully!")
    return jsonify({"message": "Success from the simplest Flask app!"}), 200

# ローカルテスト用の起動設定
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
