# Dockerfile
# ------------------------------------------------------------------------------
# このサービスをどのように組み立てるかの「建築手順書」です。
# 憲章2.3【改訂】に基づき、安定したPython 3.12をベースとします。
# ------------------------------------------------------------------------------

# ベースイメージとして、公式のPython 3.12安定版を使用します。
FROM python:3.12-slim

# コンテナ内の作業ディレクトリを設定します。
WORKDIR /app

# まず、依存関係ファイル(部品リスト)をコピーします。
COPY requirements.txt .

# 部品リストに基づいて、必要なライブラリをインストールします。
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションの本体であるソースコードをコピーします。
COPY main.py .

# このサービスがリクエストを待ち受けるポートを8080に設定します。
ENV PORT=8080

# functions-frameworkを使い、main.py内の「article_ingest_service」関数を起動します。
CMD ["functions-framework", "--target=article_ingest_service", "--port=8080"]
```python
