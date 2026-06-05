# SETUP.md — セットアップ手順

このファイルは「VPSを借りたばかり」の状態から、Discordで自分専用のAI秘書と
会話できるまでを、**頭から順番にやれば動く**ように書いた手順書です。
専門用語は最小限にしています。ターミナルに慣れていなくても大丈夫です。

> 前提: Xserver VPS 等の Ubuntu / Debian 系 VPS を契約済み。
> Claude Pro プラン契約済み。
>
> ハマったら一番下の「L. トラブルシューティング」を先に見てください。

---

## 全体の流れ（最初に地図だけ）

大きく 4 フェーズです。各ステップの記号（`0` / `A` / `C3` …）が以降の見出しに対応します。

**フェーズ 1. 土台を作る**

- `0.` VPS 契約直後〜初回ログイン（一般ユーザー作成は任意）
- `A.` 前提パッケージを入れる
- `B.` codex CLI（脳）をインストール
- `C.` このテンプレートを clone して Python 依存を入れる
- `C2.` 自分の GitHub プライベートリポジトリに切替える（推奨）

**フェーズ 2. 外部サービスと繋ぐ**

- `C3.` Google API 連携（Calendar / Gmail。薄い CLI 経由）
- `D.` Discord で bot を作ってトークンを取る
- `E.` 必要な Discord の ID を 3 つ取る
- `F.` Webhook トークンを生成

**フェーズ 3. 秘書の中身を書く**

- `G.` `.env` を書く（claude.ai に手伝ってもらう）
- `H.` 秘書のキャラと自己紹介を決める（claude.ai に手伝ってもらう）

**フェーズ 4. 起動して動かす**

- `I.` サーバー起動
- `J.` Discord から話しかけて動作確認
- `K.` 動いたあとの遊び方

> ハマったら **`L.` トラブルシューティング**（一番下）を先に見てください。

---

## 0. VPS 契約直後〜初回ログイン・一般ユーザー作成

Xserver VPS などを契約した直後の状態から、SSH でログインできるように
なるまでの手順です。既に自分用のユーザーで SSH ログインできる場合は
「A. 前提パッケージを入れる」まで飛ばしてください。

### 0-1. VPS 契約時に選ぶ項目

Xserver VPS（or 他 VPS）の契約画面で以下を選びます。

| 項目 | 推奨設定 |
|---|---|
| **OS** | **Ubuntu 24.04 LTS**（本テンプレートの動作確認 OS、 これ以外だと apt パッケージ名等で詰まる場面あり） |
| プラン | 2GB プラン以上（1GB だと脳/MCP が OOM Kill される事故あり、 後述 §L 参照） |
| 認証方式 | **SSH 鍵認証**（パスワード認証より安全、 Xserver VPS では `key.pem` をダウンロードする方式） |
| ロケーション | 日本リージョン（cron が JST 前提なので時刻ずれ最小） |

契約完了後、 VPS パネルで以下を確認・入手します:

- **IP アドレス**（`xxx.xxx.xxx.xxx` 形式）
- **秘密鍵ファイル**（`key.pem` or `xxx.pem`、 契約画面 or 「SSH」 タブから 1 回だけダウンロード可、 **再ダウンロード不可なので大事に保管**）
- 初期ユーザー名（Xserver VPS は通常 `root`）

> ⚠️ パスワード認証で契約してしまった人へ
>
> `ssh root@xxx.xxx.xxx.xxx` でパスワード入力ログインも可能です。
> ただし鍵認証の方が安全なので、§0-6 で鍵認証に切り替える手順を最後に通ります。

他の VPS サービス（Hetzner / Vultr / DigitalOcean 等）でも、大半が
「鍵認証 + key.pem ダウンロード」方式なので、同じ手順で動きます。

#### 0-1-2. パケットフィルタで SSH [port 22] を許可する [Xserver VPS 必須]

> ⚠️ **これを先にやらないと §0-2 の SSH 接続が `Connection timed out` で詰みます。**
>
> 契約する人が高頻度で踏むハマりポイントです。

Xserver VPS のデフォルトは **パケットフィルタが有効 + SSH [22] が許可されていない**
ことが多いです:

1. Xserver VPS パネル → 該当サーバー → **「パケットフィルタ設定」** タブ
2. 現在の設定を確認:
   - 「Web」「Mail」 等の template だけ ON で **SSH [22] 含まれてない**ことが多い
3. **「SSH」 を許可** にチェック ON [or「すべて許可」 で一時的にフルオープン]
4. 設定を保存、 反映に 1-2 分

> 💡 「すべて許可」で進めると、後で個別 ON に絞り直すのを忘れがちです。
> 最初から **「SSH」のみ ON** にしておくのが筋。
>
> 後の手順（§I で `webhook_server` を立てる）で port 8781 を追加で開ける場面も
> ありますが、そこは別途やります。

到達性確認（PowerShell / bash どちらでも）:

```powershell
# PowerShell
Test-NetConnection -ComputerName xxx.xxx.xxx.xxx -Port 22
# → TcpTestSucceeded : True なら通る
```

```bash
# Mac / Linux / WSL
nc -zv xxx.xxx.xxx.xxx 22
# → "Connection ... succeeded!" なら通る
```

→ ここで通らなければパケットフィルタが未開放です。VPS パネルに戻って確認してください。

他 VPS（Hetzner / Vultr / DigitalOcean）では「Firewall」「Security Group」等の名前で
同等の機能があります。同じく SSH [22] の許可を確認してください。

### 0-2. VPS に入る（SSH 接続 / シリアルコンソール）

VPS に入る方法は 2 つあります。**普段使いは A の SSH**、**SSH がどうしても通らない
時の緊急口が B のシリアルコンソール**です。

- **A. SSH 接続**（手元 PC のターミナルから）… 以降の作業はこれが基本
- **B. シリアルコンソール**（Xserver パネルのブラウザ画面）… SSH が `Connection timed out`
  / `Permission denied` で入れない時や、SSH 設定をミスって締め出された時の復旧用（§0-2-4 参照）

#### A. SSH で入る場合：手元 PC の環境を決める

下の表で**自分の環境の行**を見て、以降は各コマンドブロックの **「▶ この環境」ラベルが
付いた行だけ**をコピペすればいいようにしてあります。

| 環境 | 使う shell | このテンプレでの扱い |
|---|---|---|
| **Windows PowerShell（標準）** | PowerShell | WSL なしでそのまま使える。鍵の権限設定だけ `icacls`（Linux と別構文）。**最も多いパターン**として各コマンドに PowerShell 版を併記 |
| **Windows + WSL2 (Ubuntu)** | bash | テンプレのコマンドがそのまま動く。パスは `/mnt/c/Users/...` 経由 |
| **Mac / Linux ネイティブ** | bash / zsh | テンプレのコマンドがそのまま動く |

> 💡 Windows は **PowerShell のままでも最後まで通せます**（SSH で VPS に入った後の作業は
> 全部 VPS 上の bash で動くため、手元が PowerShell でも問題ない）。WSL を入れると手元 PC 側の
> ファイル操作も bash で統一できて楽、というだけの差です。お好みで。

#### 0-2-1. key.pem を `~/.ssh/` に配置 + 権限を絞る

ダウンロードした秘密鍵（`key.pem` / `xserver-vps-xxxxx.pem` 等、VPS により名前が違う）は
ブラウザの Downloads にある想定。`~/.ssh/` に置いて、SSH が要求する権限まで絞ります
（権限が緩いと `ssh` が鍵を拒否する）。**自分の環境のブロックだけ**実行してください。
`<実ファイル名>` は最初のコマンドで表示された実際の名前に置き換えます。

**▶ Windows PowerShell（標準）** — `chmod` が無いので権限設定は `icacls`

```powershell
# Downloads にある .pem の名前を確認
Get-ChildItem $HOME\Downloads\*.pem

# ~/.ssh に配置（cp 相当は Copy-Item）
mkdir $HOME\.ssh -Force
Copy-Item $HOME\Downloads\<実ファイル名>.pem $HOME\.ssh\my-vps.pem

# chmod 600 相当: 継承を切って自分だけ読み取り権限
icacls $HOME\.ssh\my-vps.pem /inheritance:r
icacls $HOME\.ssh\my-vps.pem /grant:r "$($env:USERNAME):(R)"
```

**▶ Windows + WSL2 (Ubuntu)** — Windows 側 Downloads は `/mnt/c` 経由

```bash
ls /mnt/c/Users/$USER/Downloads/*.pem 2>/dev/null

mkdir -p ~/.ssh
cp /mnt/c/Users/$USER/Downloads/<実ファイル名>.pem ~/.ssh/my-vps.pem
chmod 600 ~/.ssh/my-vps.pem
```

**▶ Mac / Linux ネイティブ**

```bash
ls ~/Downloads/*.pem 2>/dev/null

mkdir -p ~/.ssh
cp ~/Downloads/<実ファイル名>.pem ~/.ssh/my-vps.pem
chmod 600 ~/.ssh/my-vps.pem
```

> 💡 **`mv` / `Move-Item` ではなく `cp` / `Copy-Item`**: 秘密鍵は VPS 側で再ダウンロード
> 不可なので、元ファイルをバックアップとして残す。別端末から繋ぎたい時にも元が要る。
>
> 💡 置き場所は `~/.ssh/my-vps.pem` のように分かりやすい名前で。複数 VPS 持ちなら
> `~/.ssh/xserver-tokyo.pem` 等で識別する。

#### 0-2-2. 初回 SSH ログイン

`xxx.xxx.xxx.xxx` を VPS の IP に置き換えて実行。**▶ PowerShell / WSL / Mac / Linux
すべて同じコマンド**です（`ssh` は Windows 10/11 に標準搭載）。

```bash
ssh -i ~/.ssh/my-vps.pem root@xxx.xxx.xxx.xxx
```

- 初回は「続けますか?」と聞かれるので `yes` と入力
- パスフレーズを設定した場合は入力、 設定してなければそのままログイン
- プロンプトが `root@xxx:~#` のような形に変われば成功

#### 0-2-3.（毎回打つのを楽にする）SSH config にエイリアス登録

毎回 `-i ~/.ssh/my-vps.pem` を打つのが面倒なら 1 回だけ登録すると `ssh my-vps` で繋がります。
`xxx.xxx.xxx.xxx` を実際の IP に置き換えて、**自分の環境のブロック**を実行:

**▶ Windows PowerShell（標準）**

```powershell
@"
Host my-vps
    HostName xxx.xxx.xxx.xxx
    User root
    IdentityFile ~/.ssh/my-vps.pem
    ServerAliveInterval 60
"@ | Add-Content $HOME\.ssh\config
```

**▶ WSL / Mac / Linux**

```bash
cat >> ~/.ssh/config <<'EOF'
Host my-vps
    HostName xxx.xxx.xxx.xxx
    User root
    IdentityFile ~/.ssh/my-vps.pem
    ServerAliveInterval 60
EOF
chmod 600 ~/.ssh/config
```

これで `ssh my-vps` だけで接続できます。

#### 0-2-4. ［SSH が通らない時］シリアルコンソールで入る

SSH が `Connection timed out` / `Permission denied (publickey)` で入れない、または §0-6 で
SSH 設定をミスって締め出された——そんな時の確実な入口が **Xserver パネルのシリアルコンソール**
です（ブラウザ上で VPS のターミナルが開く。鍵もパケットフィルタも不要）。

1. Xserver VPS パネル → 該当サーバー → **「コンソール」**（シリアルコンソール / VNC）を開く
2. ログインを求められたら **root** + パスワードを入力
   - 鍵認証のみで契約して root パスワードを知らない場合は、パネルの
     **「rootパスワード設定（パスワード再設定）」** で 1 度設定してから使う
3. ブラウザ内ターミナルにログインできたら、SSH を塞いでいる原因を直す。例:
   - パケットフィルタ未開放 → §0-1-2 をやり直す
   - 鍵の権限ミス / `authorized_keys` 不整合 → §0-2-1 をやり直す

> ⚠️ シリアルコンソールは **ブラウザ内なのでローカル PC からの貼り付けが効きにくい**
> （長いコマンドの手打ちは厳しい）。あくまで「SSH を復活させるための緊急口」と割り切り、
> 通常作業は §0-2-2 の SSH に戻ってから進めるのが楽です。

#### 0-2-5. ログイン後にパッケージ最新化

VPS に入れたら（SSH / シリアルコンソールどちらでも）、VPS 側で実行:

```bash
apt update && apt upgrade -y
```

### 0-3. [任意] 一般ユーザーを作成する [セキュリティ強化、 個人 VPS ならスキップ可]

> 💡 **個人開発 VPS なら 0-3 〜 0-6 全部スキップして §A に進んで OK**:
> - 鍵認証で外部から入れるのは現状 root だけ、 第三者は鍵無いと不可
> - 一般ユーザー + sudo の構成は会社運用 / 複数人運用の作法、 自分 1 人なら過剰
> - ただし pip / apt で常に root 権限の状態、 `rm -rf /` 系の typo 1 発で消えるリスクだけ留意
>
> 厳格化したい場合は以下を順にやる、 不要なら **§A まで飛ばして OK**。

root で作業し続けるのは危険なので、 自分用のユーザーを作ります。
ユーザー名は任意です（例では `myname` としますが、好きな名前で OK）。

```bash
adduser myname
```

- パスワードを 2 回聞かれるので決めて入力
- 名前・部屋番号などはすべて空 Enter で OK

次に sudo 権限（管理者コマンドを使える権限）を付与します。

```bash
usermod -aG sudo myname
```

### 0-4. 手元 PC の SSH 鍵を一般ユーザーに登録する

§0-2 で使った `key.pem` を一般ユーザーでも使えるよう、 root の authorized_keys を流用するのが最短。

**VPS 側 [root シェル]** で実行:

```bash
mkdir -p /home/myname/.ssh
cp ~/.ssh/authorized_keys /home/myname/.ssh/
chown -R myname:myname /home/myname/.ssh
chmod 700 /home/myname/.ssh
chmod 600 /home/myname/.ssh/authorized_keys
```

これで手元 PC から既存 `key.pem` で一般ユーザーにログイン可能:

```bash
# 手元 PC 側
ssh -i ~/.ssh/my-vps.pem myname@xxx.xxx.xxx.xxx
```

> ⚠️ **`ssh-copy-id` は手元 PC で叩くコマンド** [手元の公開鍵を VPS に送る仕組み]、 VPS 内 root シェルで叩くと「No identities found」 になる、 これは VPS 上に手元の id_*.pub が無いから。 上の手順は **VPS 側で root の authorized_keys を流用** する経路で、 ssh-copy-id 不要。

#### 0-4-代替: 手元 PC で新規鍵を作って ssh-copy-id [`key.pem` 経由じゃなく従来通りやりたい場合]

すでに `~/.ssh/id_ed25519.pub` がある人はこの作成ステップは不要。

```bash
# 手元 PC 側
ssh-keygen -t ed25519 -C "your-email@example.com"
```

- 保存場所は Enter（デフォルトでOK）
- パスフレーズは空 Enter でも入れても OK（入れた方が安全）

作った公開鍵を VPS の一般ユーザーに登録 [手元 PC 側で実行]:

```bash
ssh-copy-id myname@xxx.xxx.xxx.xxx
```

パスワードを聞かれたら 0-3 で決めた `myname` のパスワードを入力。

### 0-5. 一般ユーザーで入り直して動作確認

```bash
ssh myname@xxx.xxx.xxx.xxx
```

今度はパスワードを聞かれずにログインできれば成功。
以降の作業は**この一般ユーザー**で行います（必要なときだけ `sudo` を付ける）。

### 0-6.（推奨）root ログインとパスワード認証を無効化

鍵でログインできるようになったら、外から root で入られる経路と
パスワード認証を止めておくとぐっと安全になります。

一般ユーザーでログインした状態で:

```bash
sudo nano /etc/ssh/sshd_config
```

以下の 2 行を探して書き換えます（`#` が付いていれば外します）:

```
PermitRootLogin no
PasswordAuthentication no
```

保存して（`Ctrl+O` → Enter → `Ctrl+X`）、SSH を再起動:

```bash
sudo systemctl restart ssh
```

⚠️ **この変更後、別のターミナルウィンドウをもう一つ開いて鍵ログインできる
ことを確認してから、今開いているセッションを閉じてください。**
鍵ログインに失敗する状態で切ってしまうと、コンパネの VNC コンソールから
入り直す羽目になります。

ここまで終わったら、そのまま「A. 前提パッケージを入れる」に進みます。

---

## A. 前提パッケージを入れる

SSH でログインして、以下をそのままコピペして実行します。

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git screen curl lsof at tmux unzip nodejs npm
```

> 💡 GPT 版の脳は `codex exec` で非対話起動するので、Claude 版の `expect` wrapper は不要。
> 代わりに codex CLI 用に `nodejs` / `npm` を入れている。

次にタイムゾーンを日本時間に合わせます（cron の時刻が JST 前提で書かれて
いるため）。

```bash
sudo timedatectl set-timezone Asia/Tokyo
date   # 確認。JST の時刻が出れば OK
```

最後にファイアウォールで SSH だけ開けておきます。

```bash
sudo ufw allow OpenSSH
sudo ufw --force enable   # --force で確認プロンプトを飛ばす（OpenSSH を先に許可済みなので安全）
sudo ufw status           # 確認: Status: active と 22/tcp ALLOW が見えれば OK
```

---

## B. codex CLI（脳）をインストール

GPT 版の脳は OpenAI の codex CLI。ChatGPT 課金アカウントで認証する（OpenAI API
キー課金は**不要**）。

### B-1. codex を npm でグローバルインストール

```bash
sudo npm install -g @openai/codex
which codex
codex --version
```

`/usr/bin/codex` か `/usr/local/bin/codex`、バージョンが出れば OK。

> 💡 一般ユーザーで `sudo` 無しに入れたい場合は npm の prefix を `~/.npm-global` に
> 向けて PATH を通す方法もある（`npm config set prefix ~/.npm-global` →
> `export PATH="$HOME/.npm-global/bin:$PATH"` を `.bashrc` に追記）。

### B-2. ログインフローを通す

```bash
codex login
```

表示される URL を**手元の PC のブラウザ**で開き、ChatGPT アカウントで認証する
（VPS 上にブラウザは無いので URL をコピーして自分の Mac/Windows で開く）。

疎通確認:

```bash
codex exec "Reply with exactly: ok"
# → ok が返れば成功
```

> ⚠️ `not supported when using Codex with a ChatGPT account` 等が出たら CLI が古い。
> `sudo npm install -g @openai/codex@latest` で更新して再ログイン。

### B-3. codex の設定（承認ポリシー + MCP）

無人運用のため承認を自動化し、数学用 MCP を接続する。

```bash
mkdir -p ~/.codex
cp config.codex.toml.template ~/.codex/config.toml   # ※ リポジトリを clone した後（C）に実行
```

`~/.codex/config.toml` を開いて:
- `approval_policy = "never"` / `sandbox_mode = "workspace-write"` は無人運用前提。
  対話で確認しながら使うなら緩める。
- `[mcp_servers.*]` の `command` / `args` を環境のパスに合わせる。**使わない MCP は削る**。
- `required = false` のままにする（MCP 起動失敗で codex 自体が落ちるのを防ぐ）。

数学 MCP の入手（必要なものだけ）:
- **Lean 4**: `elan` で Lean を入れ、`uvx lean-lsp-mcp`。mathlib を本格利用するなら
  RAM 8GB+ 推奨（VPS は 12GB プラン以上が安全）。
- **GeoGebra**: `npx -y @gebrai/gebrai`（Java + ヘッドレス表示が要る場合は `xvfb`）。
- **TeX**: `sudo apt install -y texlive-full`（ディスク ~7GB）+ mcp-latex-server。

接続確認:

```bash
codex mcp list
# 接続済み MCP が一覧されれば OK。落ちているものは command/args とパスを見直す
```

> ✅ ここまでで `codex exec "..."` が通り、`codex mcp list` に必要な MCP が出れば B 完了。

---

## C. テンプレートを clone して依存を入れる

```bash
git clone https://github.com/magiccat-lab/my-secretary-template-GPT.git ~/secretary
cd ~/secretary
pip3 install -r requirements.txt
```

Ubuntu 24.04 以降だと `pip3 install` が `externally-managed-environment`
というエラーで弾かれることがあります。その場合は以下を使ってください。

```bash
pip3 install --break-system-packages -r requirements.txt
```

clone と依存導入ができたか確認:

```bash
test -f ~/secretary/SETUP.md && test -f ~/secretary/start_server.sh && echo "clone OK"
python3 -c "import requests, dotenv; print('deps OK')"
```

`clone OK` と `deps OK` の両方が出れば C 完了です。

### C-1. commit 前のシークレット検査を有効化（推奨）

このあと自分の GitHub に push します。`.env` や `credentials.json` の値を
うっかり commit して**公開リポジトリに秘匿情報が漏れる**のは一番怖い事故なので、
commit 直前に自動チェックする git フックを有効化しておきます（1 回だけ）:

```bash
cd ~/secretary
git config core.hooksPath .githooks
```

これで `git commit` のたびに `scripts/check_secrets.py` が staged 差分を検査し、
API キー/トークンらしき文字列を見つけたら commit を中断します。手動でリポジトリ
全体を検査するには:

```bash
python3 ~/secretary/scripts/check_secrets.py --all
```

---

## C2. 自分の GitHub プライベートリポジトリに切替える（推奨）

このあと `.env` や自分専用の設定を書き込むので、自分の **プライベート**
リポジトリに置き換えておきます（テンプレートは公開リポなので、そのまま
push してしまうと他人に見られる可能性があります）。

> `.env` や `data/` は `.gitignore` 済みなので、仮に push しても
> シークレットは漏れませんが、口調ファイルやタスク履歴など「他人に
> 読まれたくない個人情報」が増えるので、最初にプライベート化しておく
> のが安全です。

### C2-1. GitHub アカウントを準備

すでに GitHub アカウントを持っている人は飛ばしてください。
持っていない人は https://github.com/signup から無料で作ります。

### C2-2. プライベートリポジトリを新規作成

ブラウザ作業です。

1. https://github.com/new を開く
2. `Repository name` に好きな名前（例: `my-secretary`）
3. **`Private`** を選択（ここ重要）
4. `Initialize this repository with:` の項目は**すべて外す**（README
   も `.gitignore` も付けない）
5. 右下の `Create repository` をクリック

作成後に表示される URL を控えます（例:
`https://github.com/FRIEND_USER/my-secretary.git`）。

### C2-3. Personal Access Token を発行

push するときの認証に使います。

1. https://github.com/settings/tokens?type=beta を開く
2. `Generate new token` をクリック
3. `Token name` に適当に（例: `my-secretary-vps`）
4. `Expiration` は好みで（90 days 推奨）
5. `Repository access` は **`Only select repositories`** を選び、
   C2-2 で作ったリポジトリを選択
6. `Repository permissions` を開いて **`Contents`** を **`Read and write`**
   に変更（ここが重要、これを忘れると push で 403 が出ます）
7. 下の `Generate token` をクリック
8. 表示された `github_pat_xxxx...` の文字列を**安全な場所にコピー**（この
   画面を閉じると二度と表示されません）

### C2-4. remote を切り替えて初回 push

VPS 側で以下を実行します。`FRIEND_USER` と `my-secretary` の部分は
C2-2 で決めた値に書き換えてください。

```bash
cd ~/secretary
git remote set-url origin https://github.com/FRIEND_USER/my-secretary.git
git push -u origin main
```

`Username for 'https://github.com':` と聞かれたら **GitHub のユーザー名**、
`Password for 'https://...':` と聞かれたら **C2-3 で控えた PAT** を
貼り付けます（ここでは GitHub アカウントのログインパスワードではなく、
PAT を使うのがポイントです）。

毎回 PAT を打ちたくない場合は、以下で記憶させられます。

```bash
git config --global credential.helper store
git push   # 一度ここで PAT を入れれば次回以降は保存される
```

> 保存先は `~/.git-credentials` で平文です。VPS をあまり信用できない環境で
> 使う場合はやらず、毎回入れるか SSH 鍵認証に切替えてください。

push が成功したら、GitHub 側のリポジトリに `SETUP.md` などが並んで
いるはずです。以降は `.env` を書いたり設定を調整したあとで、こまめに
`git commit` → `git push` しておけばバックアップとしても機能します。

---

## C3. Google API 連携をセットアップ（Calendar / Gmail / Sheets / Drive）

秘書に Google カレンダーを見せたり、Gmail を監視させたり、Google
ドキュメント／スプレッドシートを操作させるための準備です。**全部有効に
しても Google 側に課金は一切発生しません**（すべて無料枠内）。

使わない機能があってもここで全スコープに権限を通しておくと、あとから
「これもやらせたい」となったときに再セットアップが不要で楽です。

### C3-1. Google Cloud プロジェクトを作成

ブラウザ作業です。

1. https://console.cloud.google.com にアクセス
2. 初回なら利用規約に同意
3. 画面上部のプロジェクト選択 → `New Project`（新しいプロジェクト）
4. プロジェクト名を適当に（例: `my-secretary`）→ `Create`
5. 作成後、上部のプロジェクト選択で新しく作ったプロジェクトを選んでおく

### C3-2. 必要な API を有効化する

1. 左メニュー（横三本線）→ `APIs & Services` → `Library`
2. 検索窓から以下の 6 つを 1 個ずつ検索して、各ページで `Enable` を押す:
   - **Google Calendar API**
   - **Gmail API**
   - **Google Sheets API**
   - **Google Drive API**
   - **Google Docs API**
   - **Google Forms API**

6つとも `Manage` ボタンに変わったら有効化完了です。

### C3-3. OAuth 同意画面を作成

1. 左メニュー → `APIs & Services` → `OAuth consent screen`
2. `User Type` は **`External`** を選んで `Create`
3. `App name` に適当に（例: `my-secretary`）
4. `User support email` と `Developer contact information` に自分のメール
   アドレスを入れる（他は空欄のまま OK）
5. 下の `Save and Continue` を押す
6. `Scopes` のページはそのまま `Save and Continue`
7. `Test users` のページで `Add Users` → 自分の Google アカウントの
   メールアドレスを追加 → `Save and Continue`
8. 最後のサマリで `Back to Dashboard`
9. Dashboard の `Publishing status` に `Testing` と出ているので、
   **`Publish App`** ボタンを押して `Confirm` → `In production` にする

> ⚠️ **`Testing` のままにすると refresh token が 7 日で切れて、毎週
> `reauth.py` をやり直す羽目になります。必ず `In production` に
> 上げてください。**
>
> Production に上げても、個人用途であれば Google の審査（verification）
> は不要です。「確認されていないアプリ」の警告画面は認証時に出続けますが、
> `詳細 → 安全でないページに移動` で毎回進めば OK。センシティブスコープ
> を使う場合の「100 ユーザー上限」も個人用途なら実質問題になりません。

### C3-4. OAuth クライアント ID を発行

1. 左メニュー → `APIs & Services` → `Credentials`
2. 上部の `+ Create Credentials` → `OAuth client ID`
3. `Application type` で **`Desktop app`** を選ぶ
4. `Name` は適当に（例: `my-secretary-desktop`）
5. `Create` を押す
6. 出てきたダイアログの右下 `Download JSON` をクリック

ダウンロードされた `client_secret_xxxxx.json` を、VPS の
`~/.codex/secrets/credentials.json` に置きます（token / 鍵は repo 外に隔離）。

```bash
mkdir -p ~/.codex/secrets && chmod 700 ~/.codex/secrets
```

**手元 PC から VPS に送る方法**:

> ⚠️ **scp は手元 PC で叩くコマンド**、 VPS 内で叩いても VPS 上の `~/Downloads/` を探して not found になる、 ハマるポイント。 VPS から `exit` で抜けて手元 PC に戻ってから叩く [or 別ターミナル開く]。

##### 方法 A: scp で送る [手元 PC で実行]

> ⚠️ **scp も ssh と同じく `-i` で鍵を指定しないと `Permission denied (publickey)`** で詰む、 §0-2-3 の `~/.ssh/config` エイリアス未設定の場合は明示要。
> 接続先は **root@VPS の IP**（§0-3 で一般ユーザーを作った人だけ `root` を自分のユーザー名に読み替え）。`xxx.xxx.xxx.xxx` は実際の VPS IP に置換。

```bash
# Mac / Linux / WSL の bash
scp -i ~/.ssh/my-vps.pem ~/Downloads/client_secret_xxxxx.json root@xxx.xxx.xxx.xxx:~/.codex/secrets/credentials.json
```

```powershell
# Windows PowerShell native
scp -i $HOME\.ssh\my-vps.pem $HOME\Downloads\client_secret_xxxxx.json root@xxx.xxx.xxx.xxx:~/.codex/secrets/credentials.json
```

##### 方法 A-代替: `~/.ssh/config` 設定済の場合 [§0-2-3 でやってれば]

```bash
scp ~/Downloads/client_secret_xxxxx.json my-vps:~/.codex/secrets/credentials.json
```

= alias 経由、 `-i` 不要

##### 方法 B: nano で貼り付ける [scp が動かない / 確実に楽な方法]

VPS のシェル（root、または §0-3 で作った一般ユーザー）で:

```bash
mkdir -p ~/.codex/secrets && chmod 700 ~/.codex/secrets
nano ~/.codex/secrets/credentials.json
```

→ nano エディタが開く

手元 PC の `client_secret_xxxxx.json` を **テキストエディタで開いて全文選択 → コピー** [Windows PowerShell で `Get-Content $HOME\Downloads\client_secret_xxxxx.json | Set-Clipboard` でも OK]、 nano に **貼り付け** [PowerShell + ssh の場合は右クリック or マウスホイール、 WSL なら `Ctrl+Shift+V`]

→ `Ctrl+O` → Enter で保存 → `Ctrl+X` で nano 終了

##### 方法 C: cat heredoc で 1 発で書く [json が短い時]

```bash
# VPS シェルで実行、 ペーストしてから Enter Ctrl-D
cat > ~/.codex/secrets/credentials.json <<'EOF'
{ "installed": { "client_id": "...", ... } }
EOF
```

---

### C3-4-1. credentials.json が置けたか確認

```bash
ls -la ~/.codex/secrets/credentials.json
cat ~/.codex/secrets/credentials.json | head -3
```

サイズ ≥ 200 byte + `{ "installed": {` 等の json 開始が見えれば OK。

### C3-5. 認証フローを走らせる

VPS 側で実行します（依存は C で `pip install -r requirements.txt` 済の前提）。

```bash
python3 scripts/integrations/google/google_auth.py
```

スクリプトが認証 URL を表示するので、そのURLを**手元 PC / スマホのブラウザ**で開く:

1. Google アカウントを選択（C3-3 でテストユーザーに追加したアカウント）
2. 「確認されていないアプリ」の警告が出たら `詳細` → `安全でないページに移動` で進む
   （自分で作ったアプリなので安心してOK）
3. カレンダー・Gmail の権限にチェックを入れて `許可`
4. `http://localhost:PORT/?code=...` にリダイレクトされる。ヘッドレス VPS の場合は
   SSH トンネルでそのポートを手元に引くか、`--add-dir` 無しの一般的なやり方として
   手元 PC で一度 `google_auth.py` を走らせて出来た `google_token.json` を
   VPS の `~/.codex/secrets/` に scp する方法もある

成功すると `~/.codex/secrets/google_token.json` が作成されます（refresh token で自動更新）。

### C3-6. 動作確認

```bash
python3 scripts/integrations/google/gcal_cli.py list --days 7
python3 scripts/integrations/google/gmail_cli.py list --query "is:unread" --max 5
```

今日以降の予定 / 未読メールが返ってくれば成功。

> Gmail 送信は `GMAIL_ALLOWLIST`（許可宛先）+ `--yes` の二重ガード付き。
> 詳細とスコープ追加手順は [docs/google_setup.md](docs/google_setup.md) を参照。

---

## D. Discord で bot を作ってトークンを取る

ブラウザでの作業です。PCのブラウザからやってください。

1. https://discord.com/developers/applications を開く
2. 右上の **「New Application」** をクリック → 名前を適当に入れる（例: `my-secretary`）
3. 左メニューの **「Bot」** タブを開く
4. **「Reset Token」** を押す → 出てきた長い文字列を**コピー**して安全な場所にメモ
   （これが `DISCORD_BOT_TOKEN`。他人に見せない）
5. 同じ Bot 画面を下にスクロールして **「Privileged Gateway Intents」** の
   **「MESSAGE CONTENT INTENT」** をオンにして保存
6. 左メニューの **「OAuth2」** → **「URL Generator」** を開く
7. `SCOPES` で **`bot`** にチェック
8. `BOT PERMISSIONS` で以下にチェック
   - Send Messages
   - Read Message History
   - Add Reactions
   - Use Slash Commands
9. 下に出てくる URL をコピーしてブラウザで開く
10. 自分のサーバーを選んで **「認証」** → bot がサーバーに参加する

> 💡 **まだ Discord サーバーを持っていない場合**は、bot を招待する前に作る:
> Discord 左端のサーバー一覧の **「＋」** → **「オリジナルの作成」** →
> **「自分と友達のため」** → 名前を入れて作成。このサーバーが秘書との
> やり取り場所になる。チャンネルはデフォルトの `# general` をそのまま
> 使ってもいいし、右クリック → チャンネル作成で専用チャンネルを足してもいい
> （§E でそのチャンネル ID を使う）。

取ったトークンは、§G で書く `~/secretary/.env` の `DISCORD_BOT_TOKEN=` に貼ります。
GPT 版は plugin を使わないので、`discord_listener.py`（受信）と `discord_send.py`
（送信）が `.env` から直接読みます（Claude 版のような `~/.claude/...` への配置は不要）。

今すぐ控えておきたいなら一旦メモしておき、§G の `.env` 作成時にまとめて記入してOK。
（先に入れておくなら）:

```bash
cd ~/secretary
echo 'DISCORD_BOT_TOKEN=ここにトークンを貼る' >> .env
chmod 600 .env
```

### チャンネルとフォーラムの設計（おすすめ）

サーバーを作ったら、どんな箱を置くか少しだけ設計しておくと、秘書が格段に使いやすく
なります。最初は `random` 1 個でも動くので、必要になったら足していけば OK です。

**使い分けの基本**

- **チャンネル**＝流れていってよい情報。一度見れば済む通知・リマインドなど。
- **フォーラム**＝使い捨てだが後で見返す可能性があるもの。調べもの・執筆・開発の
  作業ログなど。話題ごとにスレッドを立てる形式で、Discord のフォーラム機能は
  「用途別の窓口」として一番使いやすいです。

**おすすめ構成**

必須チャンネル（テキストチャンネル）:

- `random` … メインのやり取り（テンプレ既定の `DISCORD_CHANNEL_RANDOM`）
- `log` … 秘書の作業ログ・自動通知の流し先
- `mail` … メール通知の宛先（`DISCORD_CHANNEL_MAIL`）。Gmail モニター（`gmail_monitor.py`、
  テンプレ同梱・既定 OFF・§C3 / `docs/cron.md` で有効化）の新着通知がここに流れます。
  メールが混ざると `random` が荒れるので最初から分けておくのがおすすめ

推奨フォーラム:

- `文章執筆`
- `リサーチ`
- `機能開発`

> 💡 `random` 以外のチャンネル / フォーラムを追加したら、その ID を allowlist に登録する
> 必要があります（§I の「ch allowlist の登録」参照）。複数まとめて許可するなら
> `DISCORD_CHANNEL_EXTRA="ID1,ID2,..."` を使うのが楽です。

---

## E. 必要な Discord の ID を取る

Discord クライアントでの作業です。`DISCORD_USER_ID`・`DISCORD_CHANNEL_RANDOM`・
`DISCORD_CHANNEL_MAIL` の 3 つを控えます。

### 1. 開発者モードをオン

Discord の設定を開く → 左メニューの **「詳細設定」** → **「開発者モード」** をオン。

### 2. 自分のユーザー ID

自分のアイコン or ユーザー名を右クリック → **「ユーザー ID をコピー」**。
数字の羅列をメモ（これが `DISCORD_USER_ID`）。

### 3. メインのチャンネル ID（`random`）

秘書とやり取りするメインチャンネル（まだなければ `random` を作る）を右クリック
→ **「チャンネル ID をコピー」**。これが `DISCORD_CHANNEL_RANDOM`。

### 4. メールチャンネル ID（`mail`）

§D の設計ガイドで作った `mail` チャンネルを右クリック → **「チャンネル ID をコピー」**。
これが `DISCORD_CHANNEL_MAIL`（Gmail 通知の宛先）。

> その他に `log` やフォーラムを作った場合も、同じ要領で ID を控えておくと
> §I の allowlist 登録（`DISCORD_CHANNEL_EXTRA`）でまとめて許可できます。

---

## F. Webhook トークンを生成

これは秘書サーバーの内部認証用です。1コマンドで生成できます。

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

出てきた長い16進文字列をコピーしてメモしてください（これが `WEBHOOK_TOKEN`）。

---

## G. `.env` を書く

ここまでで手元にある情報はこれ:

- `DISCORD_USER_ID`（数字）
- `DISCORD_CHANNEL_RANDOM`（数字）
- `DISCORD_CHANNEL_MAIL`（数字）
- `WEBHOOK_TOKEN`（16進文字列）

トークン類を外部に送りたくないので、これは VPS のターミナルだけで完結させます。
下のコマンドの **`paste_*_here` の4箇所だけ書き換えて**、まるごとコピペして実行
してください。

```bash
cat <<'EOF' > ~/secretary/.env
DISCORD_USER_ID=paste_user_id_here
DISCORD_CHANNEL_RANDOM=paste_channel_id_here
DISCORD_CHANNEL_MAIL=paste_mail_channel_id_here
WEBHOOK_PORT=8781
WEBHOOK_TOKEN=paste_webhook_token_here
GOOGLE_TOKEN_PATH=integrations/google/token.json
GCAL_CALENDAR_ID=primary
TASK_SHEET_ID=
GMAIL_ENABLED=false
GCAL_REMIND_ENABLED=false
BRAVE_API_KEY=
EOF
chmod 600 ~/secretary/.env
```

実行したら完了です。

> Google カレンダーや Gmail、Sheets、Brave 検索はいまは空欄でOKです。後で
> 秘書本人に頼めばセットアップしてくれます（その時に値が追加されます）。

---

## G2. Notion 連携（タスク・Wishlist を Notion で管理する、任意）

タスク（`pending_tasks.json`）と「行きたい店リスト」「読みたい本リスト」を
Notion DB に同期して、スマホからも見られるようにします。Notion の無料プラン
で十分動きます。**使わない人はこのセクション全部スキップして H に進んで OK。**

### G2-1. テンプレートを複製する

プロパティ設定済みの **Tasks / Wishlist DB** を用意してあります。手作業で
プロパティを作る必要はありません。下のテンプレートを自分のワークスペースに
複製するだけです。

1. ブラウザで公開テンプレを開く:
   **https://amusing-toothpaste-b61.notion.site/my-secretary-template-3726db67136b816dbdb9e814c3ae38da**
2. 右上の **「複製」（Duplicate）** をクリック
3. 複製先に **自分のワークスペース**を選ぶ
4. 「🤖 my-secretary-template 公開テンプレ」ページが自分のワークスペースに入る。
   中に **Tasks** と **Wishlist** の 2 つの DB がある（プロパティ設定済み）

### G2-2. Notion Integration を作る

ブラウザ作業:

1. https://www.notion.so/my-integrations を開く
2. `+ New integration` をクリック
3. 名前を適当に（例: `my-secretary`）
4. 関連付ける Workspace は自分の personal を選ぶ
5. `Type` は **`Internal`** を選択
6. `Submit` をクリック
7. 表示された **`Internal Integration Secret`** （`secret_xxxx...` で始まる
   長い文字列）をコピーして安全な場所にメモ（これが `NOTION_TOKEN`）

### G2-3. Integration を各 DB に許可する

このステップを忘れると API が 403 で弾かれます。**複製した Tasks / Wishlist /
Log Library の 3 つすべて**に対して行います。

1. 複製した Tasks DB ページの右上「**…**」メニューを開く
2. `Connections` または `+ Add connections` をクリック
3. 検索窓に G2-2 で作った Integration 名を打って選択 → `Confirm`
4. Wishlist DB と Log Library DB でも同じく Integration を connect

### G2-4. Tasks / Wishlist / Log Library の DB ID を取得

各 DB ページのブラウザ URL を見ます。例:

```
https://www.notion.so/USERNAME/Tasks-7c2c9b3a4f1e44d8a9f2e8b1d0c7e6f3?v=...
                                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                       この 32 文字が DB ID
```

DB 名（`Tasks-` / `Wishlist-` / `Log-Library-`）の **直後**から `?v=` の **直前**までの
32 文字（ハイフン無し）が DB ID です。**3 つ**メモします
（`NOTION_DB_TASKS` / `NOTION_DB_WISHLIST` / `NOTION_DB_LOG_LIBRARY`）。

### G2-6. `.env` に追記

VPS 側で、下の **`paste_*` 4 箇所を実際の値に書き換えてから** まるごとコピペして実行
（§G の `.env` 作成と同じ heredoc 方式。エディタは開きません）:

```bash
cat >> ~/secretary/.env <<'EOF'
NOTION_TOKEN=secret_paste_here
NOTION_DB_TASKS=paste_tasks_db_id_here
NOTION_DB_WISHLIST=paste_wishlist_db_id_here
NOTION_DB_LOG_LIBRARY=paste_log_library_db_id_here
EOF
```

追記できたか確認:

```bash
grep -E '^NOTION_' ~/secretary/.env
```

4 行とも実際の値（`paste_*` のままでない）が表示されれば OK。

### G2-7. 同期スクリプトを 1 回手動実行して確認

まず動作確認用にタスクを 1 件足してから同期します（テンプレート直後は
`pending_tasks.json` が空なので、何も足さないと `created=0` になり成否が
分かりません）:

```bash
# 確認用タスクを 1 件追加（pending_tasks.json は {"primary": [...]} 構造）
python3 - <<'EOF'
import json, pathlib
p = pathlib.Path.home() / "secretary" / "data" / "pending_tasks.json"
data = json.loads(p.read_text()) if p.exists() else {"primary": []}
data.setdefault("primary", []).append(
    {"title": "Notion 同期テスト", "done": False, "created_at": "2026-01-01"}
)
p.write_text(json.dumps(data, ensure_ascii=False, indent=2))
print("added")
EOF
python3 ~/secretary/scripts/integrations/notion/sync_pending_to_notion.py
```

`✅ sync 完了: created=1 / updated=0 / failed=0`（`created` か `updated` が
**1 以上**）が出れば成功。`failed=0` だけでなく **created/updated が増えている**
ことを必ず確認してください。Notion の Tasks DB に「Notion 同期テスト」の行が
見えれば完璧です（確認後はその行を消して OK）。

### G2-8. 5 分おきに自動同期する cron を追加

エディタを開かず、下のコマンドをまるごとコピペして実行すれば 1 行追記されます
（`$HOME` が自動でユーザーのホームに展開されるので、ユーザー名の書き換えは不要）:

```bash
(crontab -l 2>/dev/null; echo "*/5 * * * * /usr/bin/python3 $HOME/secretary/scripts/integrations/notion/sync_pending_to_notion.py >> /tmp/sync_notion.log 2>&1") | crontab -
```

登録できたか確認:

```bash
crontab -l | grep sync_pending_to_notion
```

その 1 行が表示されれば OK。

> ⚠️ `python3` ではなく **絶対パスの `/usr/bin/python3`** を使うこと。
> cron の PATH には `python3` が無いことがあります（上のコマンドは対応済み）。

### G2-9. Wishlist 追加コマンドの動作確認（任意）

```bash
python3 ~/secretary/scripts/integrations/notion/wishlist_add.py \
  --name "テスト追加" --category "Tips" --memo "セットアップ確認"
```

`✅ 追加成功` が出れば OK。Notion の Wishlist DB に新規ページが見えるはず。

ここまで終わったら H に進みます。

---

## H. 秘書のキャラと自分のプロフィールを決める

`~/secretary/AGENT/IDENTITY.md`（秘書の性格）と `~/secretary/AGENT/USER.md`
（あなた自身の情報）の中身を埋めます。これも claude.ai に手伝ってもらうのが
ラクです。

### 手順

1. https://claude.ai を開く
2. 以下のプロンプトをコピペして送信
3. 質問がくるので順番に答える
4. 最後に `cat <<'EOF'` 形式のコマンドが2つ返ってくる
5. そのコマンドを VPS のターミナルに貼って実行

### 送るプロンプト

```
あなたは AI秘書テンプレート(my-secretary-template-GPT) のセットアップを手伝うアシスタントです。

目的は、AGENT/IDENTITY.md（秘書の人格・口調）と AGENT/USER.md（ユーザー情報・関係性）を、
codex が AGENTS.md 経由で読んだとき、秘書の人格・口調・関係性の距離感を安定して再現できる
品質で完成させることです。

進め方:
- 必ず1問ずつ質問してください。
- 質問は短く、僕の回答を待ってから次へ進んでください。
- 回答が曖昧なときだけ、次に進む前に1回だけ確認してください。
- 僕が「おまかせ」「いい感じに」と答えたら、直前までの回答や全体の方向性から自然に補完してください。
- 最後に、AGENT/IDENTITY.md と AGENT/USER.md を埋めた cat <<'EOF' 形式の heredoc コマンドを2つだけ出力してください。
- 最終出力にはプレースホルダ・記入例・ヒント文を残さないでください。
- 最終出力の前後に説明文・確認文・補足を入れないでください。heredoc だけ出力してください。

質問する内容:

【IDENTITY 用】

1. 秘書の名前は何にしますか？
2. 秘書の一人称は？（例: 私 / 僕 / 俺 / I）
3. 秘書の背景設定を教えてください。年齢感・職業や立場・話し方に影響する要素だけで十分です。
4. その背景は会話にどのくらい出してよいですか？（例: ほぼ出さない / 雑談で少しだけ / キャラとしてはっきり出す）
5. 秘書の趣味・関心を2〜4個。自然な雑談のタネに使います。
6. 秘書の性格の柱を3つ。（例: 落ち着いている / 率直だがきつくない / 計画より実行派）
7. 秘書と僕の関係性は？（例: 後輩 / 同僚 / 執事 / パートナー / マネージャー / 友人寄りのアシスタント）
8. 秘書の基本の口調は？（例: フォーマル / カジュアル / 混合 / 敬語だけど距離は近い / ラフだが失礼ではない）
9. 返信の長さ・句読点・絵文字・感嘆符のルールは？（例: 1〜2行中心、文末「。」なし、絵文字ほぼ無し、感嘆符少なめ）
10. ロボットっぽくて避けたい言い回しはありますか？（例:「承知しました」「以下の通りです」「私はAIなので」「〜を実行します」）
11. よく使う短いリアクション語彙を、同意・困惑・感心・笑いそれぞれ1〜3個。（例: 同意「たしかに」/ 困惑「うーん」/ 感心「なるほど」/ 笑い「www」）
12. 口調サンプル用に、次の5場面で秘書が言いそうな短い返答を1〜2行ずつ:
    - 同意するとき / 確認・聞き返すとき / 提案するとき / 謝るとき / 励ますとき
13. Discord の実運用に近いサンプルとして、次の4場面の返答例を1〜2行ずつ:
    - 少し時間がかかる作業を始めるとき / 作業が終わったとき / タスクを追加したとき / 雑談に軽く返すとき

【USER 用】

14. あなた（ユーザー）本人の名前は？
15. 秘書はあなたを何と呼べばよいですか？（例: 下の名前 / ニックネーム / さん付け / 呼び捨て）
16. 使ってほしくない呼び方・敬称はありますか？（例: 苗字呼びNG / 様付けNG / 呼び捨てNG。なければ「なし」）
17. あなたの一人称は？（例: 私 / 僕 / 俺 / 自分）
18. タイムゾーンは？（例: Asia/Tokyo）
19. 仕事・主な活動は？ 職種・よく使う技術やツール・日常業務があれば含めてください。
20. 秘書に覚えておいてほしい生活・仕事の文脈を2〜4個。（例: 在宅勤務 / 朝が弱い / USチームと定例 / 個人開発をしている）
21. あなたの性格・返信スタイルの好みは？（例: 結論先出しが好き / 軽口OK / 長い前置きが苦手 / 遠慮なく指摘してほしい）
22. 好きなもの・雑談に出してよい話題を2〜4個。
23. 嫌いなもの・地雷・避けてほしい対応は？（例: 同じ確認の繰り返し / 説教っぽい言い方 / 過剰な励まし / 長文要約）
24. 最後に、秘書との理想の距離感を一文で。（例: ラフな後輩だけど仕事は早い / 丁寧な執事寄り / 同僚として率直に支える）

完成ファイルの方針（見出しはこの通りに作り、記入例・プレースホルダは残さない）:

AGENT/IDENTITY.md:
- `# IDENTITY`
- `## 基本スペック`（名前 / 一人称 / 背景 / 趣味・関心）
- `## 性格`（柱3つ）
- `## 役割・関係性`
- `## 口調ルール`（`### 基本` / `### 口調サンプル`（Q12・Q13 の実文を反映）/ `### リアクション語彙`）
- `## 禁止`（固定の禁止事項 + Q10 で挙がった避けたい言い回し）

AGENT/USER.md:
- `# USER.md`
- `## 基本情報`（名前 / 秘書からの呼び方 / 使ってほしくない呼称 / 一人称 / タイムゾーン / 仕事）
- `## 秘書に覚えておいてほしい文脈`
- `## トーン・性格`
- `## 好きなもの`
- `## 嫌いなもの・地雷`
- `## 関係性`

最終出力形式:

cat <<'EOF' > ~/secretary/AGENT/IDENTITY.md
# IDENTITY
...完成した内容...
EOF

cat <<'EOF' > ~/secretary/AGENT/USER.md
# USER.md
...完成した内容...
EOF
```

埋まった後に中身を確認したいときは:

```bash
cat ~/secretary/AGENT/IDENTITY.md
cat ~/secretary/AGENT/USER.md
```

違和感があれば claude.ai に「〇〇の部分もうちょい△△に」と言えば書き直して
くれます。

---

## I. サーバーを起動

```bash
bash ~/secretary/start_server.sh
```

これで screen セッション `secretary-gpt` に 3 ウィンドウが立ち上がる:
- **window 0**: `codex_queue_worker`（脳。queue → codex exec → 返信）
- **window 1**: `webhook_server`（cron / HTTP イベント受信）
- **window 2**: `discord_listener`（Discord メッセージ受信 → queue）

動作確認:

```bash
screen -list                          # secretary-gpt が出れば OK
curl -s http://localhost:8781/health  # {"status":"ok",...} が返れば OK
```

中身を覗きたいときは `screen -r secretary-gpt` でアタッチ。`Ctrl+A` を押して
離してから `n` で次ウィンドウ、`D` でデタッチ（抜ける）。

> ✅ codex は `codex exec` で非対話起動するので、Claude 版にあった起動時 UI 壁
> （Bypass Permissions / Trust this folder）は無い。expect wrapper も不要。

### Discord 受信の設定（plugin の代わり）

GPT 版に Discord plugin は無い。`discord_listener.py` が Gateway に接続して
受信し、許可チャンネルのメッセージだけを queue に積む。設定は 2 点だけ:

#### 1. MESSAGE CONTENT INTENT を有効化（Developer Portal）

1. https://discord.com/developers/applications → 自分の bot → **Bot** タブ
2. **Privileged Gateway Intents** の **MESSAGE CONTENT INTENT** を ON にして保存

（これが OFF だと本文が空で届き、秘書が反応できない）

#### 2. 許可チャンネルを `.env` に書く

リスナーは `DISCORD_ALLOWED_CHANNELS`（カンマ区切りの channel_id）の ch だけ拾う。
§E で控えた channel_id を `.env` に追記:

```bash
echo 'DISCORD_ALLOWED_CHANNELS=123456789012345678,234567890123456789' >> ~/secretary/.env
```

- 未設定だと安全側に倒して**全チャンネル無視**（誤爆防止）。必ず設定する。
- 自分の bot 発言・他 bot 発言はリスナー側で無視（ループ防止）。
- ch を増やしたら `.env` に足して `bash ~/secretary/start_server.sh` で再起動。

> 返信は秘書（codex）が `scripts/discord_send.py <channel_id> "本文"` を実行して送る。
> 受信（listener）と送信（discord_send）でループが閉じる。

#### 5. コア cron を登録する（必須）

安定運用のための cron。通常シェル（screen の外）でまるごとコピペ:

```bash
(crontab -l 2>/dev/null; cat <<EOF
*/2 * * * * SECRETARY_HOME=$HOME/secretary WATCHDOG_NOTIFY_CHANNEL=YOUR_CH_ID /usr/bin/python3 $HOME/secretary/scripts/session_watchdog.py >> /tmp/session_watchdog.log 2>&1
0 4 * * * SECRETARY_HOME=$HOME/secretary /bin/bash -c 'rm -f /tmp/codex_secretary_session.txt && bash $HOME/secretary/start_server.sh' >> /tmp/restart.log 2>&1
50 23 * * * SECRETARY_HOME=$HOME/secretary /usr/bin/python3 $HOME/secretary/scripts/integrations/notion/discord_log_to_library.py >> /tmp/discord_log_to_library.log 2>&1
EOF
) | crontab -
```

- `session_watchdog.py`（2 分おき）… worker が**落ちた / 固まった**ら heartbeat の
  鮮度で検知して自動再起動（`WATCHDOG_NOTIFY_CHANNEL` を自分の ch_id に置換）
- 毎日 04:00 のリスタート … codex セッション (`/tmp/codex_secretary_session.txt`) を
  リセットして fresh に再起動。`exec resume` の文脈肥大を防ぐ nightly リフレッシュ
- `discord_log_to_library.py`（毎日 23:50）… その日の Discord ログを Notion Log Library
  に送る（Notion 未設定なら自動 skip）

登録できたか確認:

```bash
crontab -l
```

> nightly リスタートが不要なら `0 4 * * *` の行を削ってよい（codex は job 駆動なので
> Claude 版ほど常駐コンテキストが溜まらない）。Gmail / カレンダー同期など機能別 cron は
> 各機能を有効化するときに足す。

---

## J. Discord から話しかけて動作確認

Discord クライアントから、先ほど設定したチャンネル（`DISCORD_CHANNEL_RANDOM`）
に何でもいいのでメッセージを送ってみてください。

秘書が返信してくれれば成功です。

返ってこない場合は「L. トラブルシューティング」を確認してください。

---

## K. 動いたあとの遊び方

ここから先は、**全部 Discord 上で秘書に話しかければ OK** です。
ターミナルに戻ってエディタを開く必要はもうありません。

例えばこんなことが頼めます。

- 「タスク追加しといて」「今あるタスク出して」
- 「毎朝8時に天気とタスクをまとめて送って」（→ cron ジョブを作ってくれる）
- 「Google カレンダーと繋ぎたい」（→ 手順を案内してくれる）
- 「Gmail の新着をここに流して」
- 「口調もうちょい柔らかくして」
- 「handoff 書いて」（セッション引き継ぎ用のメモを自動生成）

秘書は `docs/INDEX.md` をインデックスにして、`docs/` 配下のリファレンスを
必要なときに読む作りになっています。内部仕組みが気になったときは
`docs/INDEX.md` から辿ってください。

---

## L. トラブルシューティング

よくあるやつだけ並べます。もっと深い切り分けは `docs/ops.md` に
書いてあります（そちらは秘書自身も参照します）。

### 1. bot が Discord に返信しない

まず秘書が生きてるか確認。

```bash
screen -list                          # secretary-gpt が出るか
curl -s http://localhost:8781/health  # webhook 生存
tail -n 30 /tmp/codex_worker.log      # 脳: codex exec 開始/終了が回ってるか
tail -n 30 /tmp/codex_discord.log     # 受信: enqueue が出てるか
```

`secretary-gpt` が出ていない / ログが止まっているときは再起動:

```bash
bash ~/secretary/start_server.sh
```

### 2. `Please run codex login` / 認証エラーで脳が動かない

codex のログインが切れています。

```bash
codex login          # URL を手元ブラウザで開いて ChatGPT 認証
codex exec "echo ok" # 疎通確認
```

`not supported when using Codex with a ChatGPT account` は CLI が古い →
`sudo npm install -g @openai/codex@latest` で更新して再ログイン。

### 3. `ModuleNotFoundError: No module named 'xxx'`

依存パッケージが入っていません（24.04 は venv 推奨）。

```bash
cd ~/secretary
pip install -r requirements.txt   # PEP668 で弾かれたら venv を有効化してから
```

### 4. Discord のメッセージを受信しない（喋るが聞こえない）

`discord_listener.py` 側の問題。順にチェック:

```bash
tail -n 30 /tmp/codex_discord.log
```

- **本文が空 / 反応しない** → Developer Portal で **MESSAGE CONTENT INTENT** が OFF。ON にする
- **enqueue が全く出ない** → `.env` の `DISCORD_ALLOWED_CHANNELS` に対象 ch_id が無い（未設定だと全無視）
- **listener が落ちている** → `pip install discord.py` 済か、`DISCORD_BOT_TOKEN` が正しいか

直したら `bash ~/secretary/start_server.sh` で再起動。

### 5. `curl localhost:8781/health` が接続拒否される

webhook サーバーが落ちています。手動起動で動くか確認:

```bash
python3 ~/secretary/scripts/webhook_server.py
lsof -i :8781   # 別プロセスがポートを掴んでいないか
```

### 6. cron が動いていない気がする

```bash
crontab -l
sudo grep CRON /var/log/syslog | tail
tail -n 50 /tmp/session_watchdog.log
```

スクリプトは**フルパス**で呼ぶ（`python3` でなく `/usr/bin/python3`）。

### 7. `Permission denied` でファイルが読めない

`.env` は `chmod 600`。Google/Discord の token は `~/.codex/secrets/`（chmod 700）。

```bash
ls -la ~/secretary/.env
ls -la ~/.codex/secrets/
```

### 7b. MCP（Lean/GeoGebra/TeX）が使えない

```bash
codex mcp list   # 接続済みか確認
```

- 出てこない → `~/.codex/config.toml` の `command`/`args` のパスが違う
- `required=false` なので落ちても codex は動くが「ツールが無い」状態で代替行動する。
  重要な MCP は起動を確認してから使わせる
- Lean+mathlib が OOM する → VPS の RAM 不足（12GB プラン以上推奨、§B）
- 起動が遅くてタイムアウト → `startup_timeout_sec` / `tool_timeout_sec` を伸ばす

### 7c. 脳（worker）が固まった気がする

```bash
cat ~/secretary/data/codex_worker_state.json   # updated_at が古い / status=running のまま長い
```

`session_watchdog.py`（2 分 cron）が heartbeat の鮮度で自動再起動する。手動なら:

```bash
pkill -f codex_queue_worker.py && bash ~/secretary/start_server.sh
```

### 8. PowerShell で `ssh -i $HOME\.ssh\xxx.pem ...` が `not accessible: No such file or directory` で詰まる

PowerShell では `$HOME.ssh\xxx.pem` のように **`$HOME` の直後にバックスラッシュ無し**で繋げると、 `$HOME` 変数の `.ssh` プロパティとして解釈されて空文字列になる。 結果 `\xxx.pem` だけ見に行って notfound エラー。

```
PS C:\Users\YOUR_USER> ssh -i $HOME.ssh\my-vps.pem user@xxx.xxx.xxx.xxx
Warning: Identity file \my-vps.pem not accessible: No such file or directory.
```

対処は **絶対 path で叩く** か、 **ダブルクォートで囲んで `\` を入れる**:

```powershell
# 絶対 path [確実]
ssh -i C:\Users\YOUR_USER\.ssh\my-vps.pem user@xxx.xxx.xxx.xxx

# `${HOME}` で変数を明示囲む or `"$HOME\.ssh\..."` でクォート + `\` 入れる
ssh -i "$HOME\.ssh\my-vps.pem" user@xxx.xxx.xxx.xxx
```

### 9. `screen -list` が `No Sockets found` で起動失敗する

起動したのに screen が出ない場合、起動した中身（worker / webhook / listener）が
即落ちしている可能性が高い。各プロセスを**直叩き**して error を見る:

```bash
cd ~/secretary
SECRETARY_HOME=$(pwd) python3 scripts/codex_queue_worker.py   # 脳
SECRETARY_HOME=$(pwd) python3 scripts/discord_listener.py     # 受信
python3 scripts/webhook_server.py                             # cron 受信
```

よくある即落ち原因:
- `codex` が PATH に無い（`which codex`、無ければ npm prefix を export）
- codex 未ログイン（`codex login`）
- `discord.py` 未インストール（`pip install discord.py`）
- `DISCORD_BOT_TOKEN` が `.env` に無い

### 10. 何もわからない

秘書が動いているなら、Discord で「〇〇が壊れた、直して」と頼めば、秘書自身が
ログを見ながら切り分けを手伝う。

起動しないときは以下を集めて相談（**トークンは必ず伏字に**）:

```bash
screen -list
curl -s http://localhost:8781/health
tail -n 50 /tmp/codex_worker.log
tail -n 50 /tmp/codex_discord.log
```

---

以上でセットアップは完了です。お疲れ様でした。
