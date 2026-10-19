# Linux 版

対象は Ubuntu 24.04 LTS x86_64 GNOME。一般ユーザーとして導入します。

1. [公式手順](https://docs.astral.sh/uv/getting-started/installation/)に従い uv を導入します。
2. 信頼できる配布元から取得したアーカイブと .sha256 を確認し、空の作業フォルダーに展開します。
3. 展開先で `bash Setup-Linux.sh` を実行します。
4. アプリ一覧の Use-LLLM を開きます。

配置先は `~/Use-LLLM-Linux`、各版の `.venv` は releases 配下に生成されます。
通常起動には uv やネット接続による依存取得を必要としません。

導入に sudo は付けません。uv がなければ導入手順を案内して停止します。
初回と更新には Python 配布元（GitHub）、PyPI と配布ファイルホストへの HTTPS 接続が必要です。
組織のプロキシは HTTP_PROXY／HTTPS_PROXY を設定してください。
チェックサムは破損の検出用です。配布元の真正性は配布経路で確認します。

## 設定・データ

- 設定・初回設定: ~/.config/use-lllm/
- 会話・成果物: ~/.local/share/use-lllm/data/
- ログ・更新前バックアップ: ~/.local/state/use-lllm/
- 起動情報: $XDG_RUNTIME_DIR/use-lllm/（なければ専用 state/runtime）。

XDG_CONFIG_HOME／XDG_DATA_HOME／XDG_STATE_HOME に対応します。
USE_LLLM_DATA_DIR を指定した場合は既存互換で設定とデータをその配下にまとめます。
仮想環境は各リリースの最終パスで生成し、別の PC やフォルダーからコピーしません。

## 接続

Ollama とモデルは別途導入し、「接続と設定」から選びます。
Azure は endpoint、deployment、API key を設定します。キーは Secret Service に保管します。
GNOME の Passwords and Keys（seahorse）などで既定のキーリングを用意して解除してください。
OS パッケージが不足する場合は管理者へ gnome-keyring／D-Bus／必要に応じて seahorse の導入を依頼します。

キー保管のロック・停止時も WebUI と Ollama は利用可能です。Azure は解除か再入力が必要です。
キー保管不能時に平文へ切り替えません。Windows の保護済み設定を持ち込んだ場合も Azure キーは再入力します。
MCP には Linux 上のコマンド・パスを設定します。Windows の .exe／Scripts/python.exe は使えません。
MCP の任意入力 env／headers は従来どおり設定ファイルに保存されるため、共有用の設定へ秘密を含めないでください。

## 起動・停止・診断

通常起動で依存パッケージをダウンロードしません。二度起動すると既存の画面を開きます。
8765 が使用中なら別の空きポートを選択します。ブラウザーを閉じてもサーバーは継続します。

```bash
~/Use-LLLM-Linux/Start-WebUI.sh
~/Use-LLLM-Linux/Start-WebUI.sh status
~/Use-LLLM-Linux/Start-WebUI.sh stop
~/Use-LLLM-Linux/Start-WebUI.sh start --no-browser
```

ログは ~/.local/state/use-lllm/logs/server.log（最大5MiB・3世代）です。
通知が見えない場合は端末から起動してエラーを確認してください。
ブラウザーだけ開けない場合は表示された URL を手動で開きます。

## 更新・削除

停止後、新版アーカイブを指定して更新します。起動中の更新は中止されます。

```bash
~/Use-LLLM-Linux/Update-Linux.sh /絶対パス/Use-LLLM-Linux-新版.tar.gz
~/Use-LLLM-Linux/Uninstall-Linux.sh
```

更新は旧版と別の仮想環境を作り、確認後に current を切り替えます。設定と SQLite は退避します。
キー自体はバックアップへ書き出しません。失敗版は .incomplete を記録し、旧版を維持します。
同一版名での再導入は拒否するため、失敗後は新しい版名の配布物を使ってください。

通常の削除はアプリ・ショートカットのみで、会話・設定・キーを残します。
Uninstall-Linux.sh に --purge-data を追加した場合だけ会話・設定・アプリ所有キーも削除します。
キーリングの解除が必要です。USE_LLLM_DATA_DIR が指定されていれば完全削除は手動整理を案内します。
共有の uv／Python キャッシュ、Ollama、モデル、外部 MCP は削除しません。

## 配布作成・検証範囲

開発チェックアウトで `uv run --frozen python tools/linux/release.py 一意の版名` を実行します。
dist 配下に tar.gz と .sha256 を生成します。個人設定・履歴・.venv・Windows EXE は含めません。
Linux コンテナーの検証と Ubuntu GNOME の実画面での受入確認を区別します。
詳細は [検証記録](../superpowers/verification/2026-10-19-linux-edition.md) を参照してください。
