# 0001 テーブル設計(第一版)

状態: maintainer の確認待ち(§3 の論点)。schema と tools は §2 の案で実装済みで、空の DB は検証を通る

計画 0001 の段階 1。計画 §3 の第一案を、ser_dataset_db の道具を引き継いで実装した。
列の語彙(enum)は試作(段階 2)で実データを入れながら直す前提で、ここでは「骨組み」を決めたい。

## 1. ser_dataset_db から変えないもの

- CSV + git、`data/` が正、`views/` は生成物、`schema/` の 3 ファイルで型・欠損・enum を決める
- 欠損の区別(空欄 / `unknown` / `NA` / `none` / `conflicting`)、`;` 区切り、ID の規則
- 根拠の行(`evidence.csv`)の status(current / superseded / conflicting)と、食い違いを選ばない中立
- `checked_by=user` は確認 PR の merge だけ。自由記述の文には出典タグ `[source_id]`
- 出典に辿れないデータセットは入れない(検証で弾く)

変えたもの: `provisional` は最初から無い(古い記録の移行が無いため)。`checked_by` に `script`
(道具が機械可読な一次資料を読んだ)を足した。

## 2. 骨組み

### 2.1 データセットの下に子の行を持つ

SER DB はほぼ `datasets` 1 行で足りたが、EEG は同じデータセット内で計測条件・課題・被験者群が分かれる。
そこで子のテーブルを持つ。子の行の ID はデータセット内で付ける(`main`、`rest`、`patients` など)。

| 子のテーブル | 根拠の付け方 |
|---|---|
| `access_routes`、`acquisition_setups`、`tasks`、`participant_groups` | **セルごと**に `evidence.csv`。field は `<table>:<行ID>.<列>`(例 `acquisition_setups:main.sampling_rate_hz`) |
| `channels`、`task_steps`、`annotations`、`label_counts`、`participant_fields`、`quality_info`、`distributed_versions`、`benchmarks`、`issues` | **行ごと**に `source_id`・`locator`・`checked_on`・`checked_by`(SER DB の annotations と同じ) |

分けた理由: 前者は 1 行の値が別々の資料から来る(装置は論文、サンプリング周波数は `*_eeg.json` など)ので
セルごとに出典が要る。後者は 1 行が 1 つの資料の 1 箇所に対応する(チャネル表の 1 行、論文の表の 1 行)。
1 つの仕組み(evidence)を子のテーブルにも広げただけなので、検証も同じ規則で回る。

### 2.2 入手経路(計画 §4 の実装)

- `access_routes` に経路ごとの `access_method`(8 値)、人がすること(`human_steps`)、資料が示す
  ダウンロード手段(`automation_tool`)、ミラーなら著者の許可の有無、実際に試した結果(`access_observed`)
- `datasets.best_access_method` と `access_tier` は経路から自動で導出(いちばん人手の少ない経路)。
  tier は open / one_time_human / per_dataset_human / approval / unavailable の 5 段
- `views/access_summary.csv` が tier ごとのデータセット数・被験者数・時間を出す

### 2.3 学習に使えるか

`datasets` に `ml_training_terms`・`commercial_use_terms`・`derivative_terms`
(allowed / allowed_with_conditions / prohibited / not_stated)と、条件の引用 `terms_note`。
ライセンスの分類 `license_spdx` とは別に持つ(独自規約が多く、SPDX では学習利用が分からないため)。

### 2.4 規模の 2 本立て

SER DB と同じく、資料の値 `*_reported` と配布物の値 `*_release` を並べる(被験者・セッション・記録・時間・GB)。
`*_release` の出典は、配布物の中のファイル(`release_files`)、リポジトリの記録(`repository_record`、
OpenNeuro のファイル数・容量など)、DB 側の道具で数えた結果(`count_report`、source_type `implementation`)。
→ 論点 3.2

### 2.5 maintainer 指定の 4 項目の行き先

| 指定 | 行き先 |
|---|---|
| チャネル配置 | `acquisition_setups`(配置方式・参照・接地・電極の種類・座標の有無)+ `channels`(チャネル名、標準名、順番) |
| タスクシーケンスの詳細 | `tasks`(パラダイム・刺激・試行数・run の長さ)+ `task_steps`(1 試行・ブロック・run の中の順番と長さ、イベントコード) |
| 個人特性の詳細 | `participant_groups`(資料の要約値: 人数・年齢・性別・利き手・経験)+ `participant_fields`(配布物にある項目と人数。体重・BCI 経験など) |
| 計測者側の品質情報 | `quality_info`(インピーダンス値・閾値、悪いチャネル、悪い区間、アーチファクト注釈、品質評価、除外試行、記録ノート) |

Excel の列の行き先は計画 0001 の付録 A のとおり(`Task_Definition` → `benchmarks`、
`Provider_Master` → `providers`、`Provider_Preprocessing` の提供者側の処理 → `distributed_versions`)。

## 3. 論点(maintainer に決めてほしいこと)

### 3.1 子のテーブルを最初から全部持つか

案 A(今の実装): 13 の子のテーブルを全部用意し、試作で使わないものは空のまま。
案 B: 試作では `access_routes`・`acquisition_setups`・`tasks`・`participant_groups` だけにして、残りは必要になったら足す。

A のほうが Excel と指定の 4 項目を最初から全部受けられる。空のテーブルは検証の負担にならない。**A を推す**。

### 3.2 `*_release` を DB 側で数えてよいか(計画 §8 Q5)

SER DB では配布物を数えた値は recipe の readme だけが出典になれた(研究の成果物を通す)。
EEG にはまだ recipe が無い。案:

- 案 A(今の実装): DB 側の道具で数えた結果を `count_report` という出典として登録できる。
  道具・実行日・スナップショットを出典の行に書く。OpenNeuro のように数える必要がなく記録にある値は `repository_record`
- 案 B: `*_release` は当面、リポジトリの記録と配布物内のファイルだけ。数えるのは学習パイプラインができてから

foundation model の学習では配布物を全部落とすので、そのときに数えた値を戻せる A が自然。
ただし数えた値の信頼性は道具しだい(SER DB の readme と同じ限界)。

### 3.3 チャネル名の標準化の範囲

`channels.standard_name` は 10-05 の位置名と同じ電極のとき、**表記の揺れだけ**を直す(`FP1`→`Fp1`、`EEG Fp1-REF`→`Fp1`)。
旧名(T3→T7)の読み替えも入れるか? 入れると学習には便利だが「意味の対応づけ」になる。
SER DB はラベルの意味を変える対応づけを DB に入れない決まり(label_normalization)。案: 旧名の読み替えは
決まった対応(T3/T7、T4/T8、T5/P7、T6/P8)だけ enum 的に許し、それ以外の対応づけは `local/`。

### 3.4 `participant_fields` で値の分布まで持つか

今は「項目名・意味・単位・何人分あるか」まで。年齢の分布などは `participant_groups` の要約値(資料が書いたもの)だけ。
配布物から計算した分布(例: 体重の平均)を DB に入れるかは 3.2 と同じ問題で、`count_report` を認めるなら入れられる。
当面は入れない案。

### 3.5 OpenNeuro の 1 accession = 1 データセットでよいか

OpenNeuro は 1 つの accession(ds00xxxx)に複数の実験が入っていることがある。案: 原則 1 accession = 1 行、
著者が別のデータセットとして紹介しているときだけ分ける。TUH は配布元が別コーパスとして出しているので、
TUEG と各サブコーパス(TUAB・TUSZ など)を別行にして `subset_of` でつなぐ。

## 4. 先送りにしたもの

- 参加者 1 人 1 行の表(計画 §8 Q3 で入れないと決めた)
- 論文 DB(計画 §8 Q4)
- DB 管理の skill(`.claude/skills/`)。試作で手順が固まってから書く
- `access_observed` を確かめる道具。ファイルを落とすので、対象をまとめて maintainer の了承を取ってから作る
- ライセンス(DB 自体の)。非公開のうちは決めない

## 5. 次にやること(論点が決まったら)

段階 2 の試作: 性質の違う 10 件程度を手で入れて列を直す(計画 §6)。候補: TUAB、TUSZ(申請制・臨床)、
SEED(申請制・感情)、DEAP、DREAMER、BCI2020-3(OSF で公開)、OpenNeuro の BIDS 2–3 件、BNCI の MI 1 件、
Sleep-EDF(PhysioNet open)。経路の分類が全部の段階に出るように選ぶ。
