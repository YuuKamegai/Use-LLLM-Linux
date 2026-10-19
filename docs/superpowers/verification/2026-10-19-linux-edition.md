# Linux 版 検証記録

日付: 2026-10-19（日本時間）
状態: 実装済み。Windows／Linux コンテナー自動検証済み。Ubuntu GNOME 実画面の受入検証待ち。

## 環境

- Windows: 専用 worktree／venv、Python 3.12.13、uv.lock 固定。
- Linux: WSL コンテナー（Debian trixie）、専用 Python 3.12.13／venv、同じ uv.lock。
- Linux 導入検証: 専用の一般ユーザー linuxqa、HOME=/home/linuxqa、ホストの個人データなし。
- Windows 本体の既存設定・キー・会話を移行・変更せず検証した。

## 結果

| 検証 | 結果 |
|---|---|
| Windows pytest 全体 | 295 passed、7 POSIX 専用 skip、14 subtests |
| Linux pytest 全体 | 301 passed、1 DPAPI 専用 skip、14 subtests |
| Ruff src/tests/tools | PASS |
| Node の非ブラウザー General UI テスト | 6ファイル PASS |
| Windows Edge／Linux Chromium ブラウザー試験 | 日英・履歴・モバイル幅・オフライン HTML／画像／数式／プロット PASS |
| Linux 実子プロセス start→二重起動→status→stop | PASS |
| Linux 配布・導入・更新失敗時の旧版維持・既定削除 | 自動テスト PASS |
| 一般ユーザーで配布アーカイブからオンライン導入 | PASS、~/Use-LLLM-Linux/releases/0.1.0-linux-preview.1/.venv を作成 |
| 導入した Start-WebUI.sh start --no-browser／status／stop | PASS、ready=true |
| desktop-file-validate | エラーなし。カテゴリーが2つある旨の hint のみ |
| 実 D-Bus／gnome-keyring の保存・読出し・削除・ロック時拒否 | PASS、隔離したテストキーのみ使用 |
| Linux の同時起動と起動中の更新拒否 | 実子プロセスで PASS |

FastAPI／Starlette の httpx TestClient 非推奨警告が1件ある。現行依存の既知警告でテスト失敗ではない。
Linux で既存テストが発見した Windows 専用 PNG パス検出を POSIX 対応した。
既存 Azure API テストは Linux では隔離した Secret Service fake を使用し、実 Secret Service は別途検証した。

## 実行コマンド

```text
uv run --frozen python -m pytest -q
uv run --frozen ruff check src tests tools
node tests/test_general_<各非ブラウザー項目>.cjs
Linux: /tmp/validation/.venv/bin/python -m pytest /work/tests -q -p no:cacheprovider
Linux: dbus-run-session -- <venv-python> <isolated-secret-service-check>
Linux: bash Setup-Linux.sh <release.tar.gz>（一般ユーザー）
Linux: bash ~/Use-LLLM-Linux/Start-WebUI.sh start --no-browser
Linux: bash ~/Use-LLLM-Linux/Start-WebUI.sh status
Linux: bash ~/Use-LLLM-Linux/Start-WebUI.sh stop
desktop-file-validate <generated.desktop>
```

## 未実施の受入項目

- Ubuntu 24.04 GNOME のアプリ一覧から実際にブラウザーを開く操作。
- GNOME ログイン時のキーリング自動解除との連携。
- 実 Ollama／実 Azure に接続した Linux からの会話。API mock の成功と区別する。
- 利用者が使用する実 MCP サーバーとの Linux 接続。既存 fixture の接続試験とは区別する。
- Ubuntu GNOME の実セッション上でのブラウザー表示確認（Linux Chromium 自動試験とは別）。

このため、配布物は preview として扱い、Ubuntu デスクトップでの受入完了とは報告しない。
成果物のハッシュは配布時に生成する .tar.gz.sha256 に記録する。

## 独立レビューと修正

c4db421..a71cb96 を独立したレビュー担当が確認した。重要指摘5件を再現テストで
RED→GREEN とし、831f7c7 で修正した。修正後の全体テスト件数は上表のとおり。

1. 起動後にキーリングをロックした場合も、未変更キーを再保存せず Ollama へ切替可能にした。
2. XDG_STATE_HOME 指定時の管理ロック保存先を、起動・更新・削除で一致させた。
3. 安定した起動入口は原子的に初回作成し、更新では保持する。容量不足で旧入口を切り詰めない。
4. USE_LLLM_DATA_DIR 指定先の設定・SQLite を更新前バックアップに含めた。
5. 起動情報の保存が失敗した場合、正常応答する子でも回収し、管理不能なサーバーを残さない。

追加で、配布手順から参照する検証記録の同梱を確認するテストを RED→GREEN とした。

## 実装上の判断と限界

- Bash の補助スクリプト相当の進捗記録を PowerShell で保存した。製品動作への影響はない。
- テスト・呼出し側から SessionStore を注入する場合は、従来の setup.json の位置を維持した。
- キー保管は keyring の自動解除を伴うラッパーを使わず SecretStorage を直接利用した。
  GNOME Secret Service が対象であり、他デスクトップのキー保管への互換性は保証しない。
- Setup-Linux.sh は検証済みアーカイブに加え、展開済みの配布フォルダーも受け取る。
  チェックサム検査は真正性を保証しないため、信頼した配布元の利用が前提。
- Windows にシンボリックリンク作成権限がないため、実導入試験は Linux で実行した。
- 画像取込は既存の書込みツール判定を維持して POSIX パスへ対応した。
- ホーム直下の起動入口は更新時に保持し、実装は current 配下で切り替える。
  将来、入口の契約を変更する更新では別途マイグレーションが必要。
- PID 再利用への pidfd 対応と同時起動のテストを行ったが、長期ストレス検証は未実施。
  同一ユーザーが管理領域を悪意をもって同時変更する状況の完全な耐性は保証しない。

レビューで保留した実デスクトップ・実モデル・実 MCP 項目は上記の未実施一覧に残した。
