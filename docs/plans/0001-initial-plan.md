# 0001 EEG データセット DB の立ち上げ計画

状態: 資料調査中(段階の順番と出典の扱いは discussions/0002 で直した。この計画の §3.3・§4.1・§6 の古い記述は 0002 が優先)

## 1. 目的

大規模な EEG foundation model を学習するために、ネット上に情報のある EEG データセットを
できるだけ全部集めて、1 つの DB に登録する。DB は「真実」ではなく一次資料への道を示す
三次資料とし、設計は `ser_dataset_db` を引き継ぐ。

引き継ぐもの(ser_dataset_db の README・docs の決定):

- CSV + 独立 git、`data/*.csv` が正、`views/` は生成物
- すべての値に根拠の行(`evidence.csv`)と出典(`sources.csv`)。根拠のない値は入れない
- 欠損の区別: 空欄=未確認、`unknown`=全文を読んだが書いていない、`NA`、`none`、`conflicting`
- `status`(current / superseded / conflicting)、`checked_on`・`checked_by`(claude / user)、
  `checked_by=user` は maintainer が merge した確認 PR だけ
- 中立: DB は「使うべきか」を書かない。プロジェクトの判断(使う・使わない、自分たちの前処理、
  ダウンロード先)は git 無視の `local/` に置く
- 1 行 = 最初に公開されたデータセット。再アップロードは aliases、サブセットや再分割は別行 + relations
- `schema/`(columns・enums・tables)と `tools/`(validate・views・db.py・fmt)、pre-commit で検証
- 議論 `docs/discussions/`・計画 `docs/plans/` は日本語、リポジトリの中身は英語

## 2. 音声との違い(設計に効くもの)

| 観点 | SER DB | EEG DB で起きること |
|---|---|---|
| 規模 | 318 件 | OpenNeuro だけで EEG/iEEG が数百件。全体で 1000 件を超える見込み → 手作業だけでは回らない |
| 機械可読な一次資料 | ほぼ無い | BIDS(`dataset_description.json`・`participants.tsv`・`channels.tsv`・`electrodes.tsv`・`*_eeg.json`・`events.tsv`)は著者が出す一次資料で、自動で読める |
| 粒度 | データセット単位でほぼ足りる | 同じデータセット内で装置・チャネル数・サンプリング周波数・課題が混在する(TUEG は 250–1024 Hz、課題が複数など) → データセットの下に「計測条件」「課題」の行が要る |
| ラベル | 感情ラベル | 課題のイベント、臨床診断、睡眠段階、アーチファクト注釈など種類が多い |
| 個人特性 | 話者数程度 | 年齢・性別・利き手・体重・診断・服薬・BCI 経験(初回か)など。参加者ごとの表が配布物に入っていることが多い |
| 「タスク」の意味 | — | ①実験の課題(安静開眼、運動想起、P300…)と ②ML の評価課題(異常検出 AUROC など、Excel の Task_Definition)が別物。名前を分ける |

## 3. 登録する情報(第一案。作りながら直す)

maintainer の指定(チャネル配置・課題の流れ・個人特性・計測者側の品質情報)と Excel の列を
全部入れる。Excel 列の行き先は付録 A。

### 3.1 テーブル案

ser_dataset_db と同じもの: `datasets`, `evidence`, `sources`, `dataset_sources`, `aliases`,
`relations`(Excel の `Palent_Dataset_ID` → `subset_of` など), `issues`, `label_counts`。

EEG で新しく足すもの:

| テーブル | 1 行 | 主な列 |
|---|---|---|
| `providers` | 提供機関 1 つ | 名前、種類(hospital / university / company …)、国 |
| `acquisition_setups` | データセット内の計測条件 1 つ | 装置(アンプ)、電極の種類(wet/gel/saline/dry)、チャネル数(EEG と EEG 以外を分ける)、配置方式(10-20 / 10-10 / EGI HydroCel …)、参照・接地電極、サンプリング周波数、電源周波数、ハードウェアフィルタ、電極座標の有無、同時計測(EOG・ECG・EMG・眼球運動・fMRI …)、ファイル形式 |
| `channels` | 計測条件 × チャネル 1 つ | チャネル名(資料の表記のまま)、種類(EEG/EOG/…)、標準名への対応、座標の有無。配置の詳細はここで持つ |
| `tasks` | データセット内の実験課題 1 つ | 課題名(資料の表記)、パラダイムの分類(resting / motor imagery / P300 / SSVEP / emotion induction / sleep / clinical routine …)、刺激の種類、応答の有無、1 回の長さ |
| `task_steps` | 課題の手順 1 段 | 順番、内容(固視・提示・想起・休憩 …)、長さ、試行数・ブロック数、イベントコード。「タスクシーケンスの詳細」はここ |
| `annotations` | ラベル集合・注釈 1 つ | 種類(イベント・臨床ラベル・睡眠段階・アーチファクト・自己評価(valence 等))、ラベル一覧、尺度、誰が付けたか、単位(試行・区間・記録・被験者) |
| `participant_groups` | データセット内の被験者群 1 つ | 群(患者/健常 …)、人数、年齢(範囲・平均・SD)、性別の内訳、利き手、診断。資料が書いている要約値 |
| `participant_fields` | 配布物の参加者表にある項目 1 つ | 項目名(age, weight, bci_experience …)、意味、単位、何人分あるか。「何が分かるか」をデータセットをまたいで探せるようにする |
| `quality_info` | 計測者側の品質情報 1 つ | 種類(インピーダンスの記録、悪いチャネルの印、アーチファクト注釈、品質評価、除外試行、計測ノート)、範囲、形式、出典 |
| `distributed_versions` | 配布されているデータの形 1 つ | raw / 前処理済み(再サンプリング・フィルタ・区切り・正規化・アーチファクト除去)、提供者がやった処理の内容 |
| `benchmarks` | 論文がそのデータで定義した評価課題 1 つ | 課題名、種類、クラス数・クラス、評価指標、報告値、どの論文か(Excel の Task_Definition) |

参加者 1 人 1 行の表は DB の本体に入れない案(§8 Q3)。理由: TUEG だけで 1.5 万人、合計で数十万行になり、
配布物から機械的に作れる(生成物か `local/` で十分)。DB は「どの項目が何人分あるか」と資料の要約値を持つ。

### 3.2 datasets の列(第一案)

名前・正式名・モダリティ(EEG / iEEG / MEG / PSG …, 同時計測)、領域(clinical / emotion / BCI /
cognitive / sleep …)、提供機関、ライセンス(SPDX)・商用利用の可否(資料の記述)、入手方法と
実際に試した結果、規模(資料の値 `*_reported` と配布物を数えた値 `*_release` を分ける:
被験者数・セッション数・記録数・時間・GB)、BIDS か、公開年、notes。
装置・チャネル数・サンプリング周波数は `acquisition_setups` から導出する列にする
(ser_dataset_db の `derive.py` と同じ考え方)。

### 3.3 出典の種類

- `primary`: 論文・配布ページ・ライセンス・配布物のファイル。**BIDS のメタデータは配布物の一次資料**
  として扱い、locator は `ds00xxxx v1.2.0 participants.tsv` のように版とファイルで示す
- `implementation`: SER DB では recipe の readme。EEG ではまだ recipe が無いので、配布物を開いて
  数えた結果をどこに書くかは決める必要がある(§8 Q5)
- `secondary`: MOABB・Braindecode・NEMAR のカタログ、サーベイ、foundation model 論文の表

## 4. 入手の自動化(最重視)

研究計画に直接響くので、**データの取得まで AI で完結するか(人の手作業の申請が要るか)**を
全データセットで最優先に記録し、調査も「AI で自動取得でき、学習に使えるもの」から先にやる。

### 4.1 入手経路の分類(`access_method` を細かくする案)

人の作業が「いつ・何回・誰の判断で」要るかで分ける。資料の記述(`access_method`)と
実際に試した結果(`access_observed`・`access_observed_on`)は SER DB と同じく分けて持つ。

| 値(案) | 人の作業 | 例 |
|---|---|---|
| `open_direct` | なし。URL・API・CLI でそのまま取れる | OpenNeuro(S3・DataLad)、PhysioNet の open access、Zenodo・figshare の公開ファイル |
| `open_with_token` | サイトごとに 1 回だけ(アカウント作成・API トークン)。以後は自動 | Kaggle、OSF の一部、Hugging Face の gated でないもの |
| `click_through` | データセットごとに利用規約への同意(承認は自動) | Hugging Face の gated(自動承認)、規約同意つきのダウンロードページ |
| `manual_approval` | 申請書・メールを送り、提供者が人手で承認 | TUH EEG Corpus、SEED、DEAP など |
| `credentialed` | 資格審査・研修修了(PhysioNet credentialed + CITI など) | PhysioNet の credentialed |
| `institutional_agreement` | 所属機関の署名つきデータ利用契約 | 病院データの一部 |
| `not_available` | 配布されていない・リンク切れ・「著者に連絡」だけ | |

- `open_with_token` と `click_through` の同意・アカウント作成は maintainer がする(AI は代わりに同意や
  アカウント作成をしない)。それでも「1 回やれば以後は自動」なので研究計画上は `manual_approval` 以下と分けて数える
- 実際に取れるかの確認(`access_observed`)はファイルを落とす作業なので、件数・サイト・容量をまとめて
  maintainer の了承を取ってから行う。全体を落とすのではなく、ファイル一覧の取得や小さいファイル 1 つで確かめる
- 1 つのデータセットに経路が複数ある(公式は申請制、ミラーは公開など)ときは経路ごとに記録する。
  ミラーが著者の許可を得ているかは資料の記述だけを書き、DB は判断しない

### 4.2 「学習に使えるか」の記録

- ライセンス(`license_spdx`)に加え、利用規約が**機械学習の学習**・**商用**・**派生物(モデル)の公開**に
  ついて何と言っているかを、資料の引用つきで記録する列を足す(例: `ml_training_terms`、`derivative_terms`)。
  書いていなければ `unknown`。DB は「使ってよい」と判断せず、判断は `local/`
- 実際に学習に入れられる形か: ファイル形式(EDF / BDF / BrainVision / EEGLAB .set / .mat / .fif …)、
  生データか前処理済みか(`distributed_versions`)、チャネル名・サンプリング周波数が読み取れるか

### 4.3 調査の優先順位

1. `open_direct` が多い所を先に全件: OpenNeuro(EEG・iEEG)、NEMAR、PhysioNet(open access)、
   BNCI Horizon 2020、MOABB が自動で落とせるもの、Zenodo・figshare・OSF の公開データ
2. 次に `open_with_token`・`click_through`(Kaggle、Hugging Face など)
3. `manual_approval` 以下は、規模が大きいもの(TUH など)と foundation model 論文でよく使われるものを
   優先し、残りは入手経路とライセンスだけ先に埋める
4. 進捗は `views/` に「経路ごとの件数・被験者数・時間」の集計を出し、自動で取れる総時間が一目で分かるようにする

## 5. 候補の集め方

1. Excel の 11 件(TUH 系 7・SEED・DEAP・DREAMER・BCI2020-3)を最初の候補にする。値は出典が無いので
   入れず、一次資料から取り直す(ser_dataset_db は新しい `provisional` を作らない決まり)
2. 機械で一覧が取れるところ: OpenNeuro(API で modality=EEG/iEEG を全件)、NEMAR、PhysioNet、
   MOABB の dataset 一覧、BNCI Horizon 2020
3. foundation model 論文(LaBraM, BIOT, BENDR, EEGPT, CBraMod, NeuroLM など)の事前学習・評価データの表
   ── 論文 DB は後回し(§8 Q4)。論文は `sources` として持つ
4. Zenodo・figshare・OSF・Kaggle・Hugging Face・Harvard Dataverse の検索、awesome 系リスト、サーベイ
5. 候補は `candidates` として先に全部並べ、出典に辿れないものは登録しない(ゴースト対策)

## 6. 進め方(段階)

| 段階 | 内容 | 終わりの目安 |
|---|---|---|
| 0 | §8 の質問を決める。リポジトリを作る(場所・公開/非公開) | この計画の状態が「決定」 |
| 1 | `docs/discussions/0001` でテーブル設計を議論。ser_dataset_db の tools を複製して EEG 用に直す | schema と validate が動く |
| 2 | 試作: 性質の違う 10 件程度(TUAB, TUSZ, SEED, DEAP, DREAMER, BCI2020-3, OpenNeuro の BIDS 2–3 件, BNCI の MI 1 件, Sleep-EDF)を手で入れて列を直す | 列の過不足が出尽くす |
| 3 | 候補一覧を作る(§5)。まず全件の入手経路(§4.1)を埋める | 全候補に入手経路 |
| 4 | `open_direct` のもの(OpenNeuro など BIDS 中心)を自動で取り込む道具。了承を得て取得を確かめる | 自動取得できるものが機械で埋まり、`access_observed` つき |
| 5 | 残りを §4.3 の順に AI 調査で埋める(1 件ずつ、根拠つき) | 全件にデータセット単位の基本値 |
| 6 | 確認 PR(`verify/...`)で maintainer が一次資料を見る。ライセンス・学習利用の条件・入手経路は全件 | 3 つが人の確認済み |

## 7. 気をつけること

- Excel の `Checked_Person` には個人名、`OneDrive_Link_*` は内部の場所が入っている。DB が公開なら入れない(`local/` へ)
- Excel の `Provider_Preprocessing` は「提供者がした前処理」か「自分たちのパイプライン」かが混ざって見える
  (`Use torcheeg`、`preprocessing_speech.py`)。前者は `distributed_versions`、後者は `local/`
- 「Task」は実験課題(`tasks`)と評価課題(`benchmarks`)を名前で分ける
- 臨床データ(TUH など)は利用規約が独自で、登録・同意書が要るものが多い。`access_method` と `license_note` で記録だけする

## 8. maintainer への質問

2026-11-14 にチャットで回答を得たもの。

| 問い | 回答 | この計画への反映 |
|---|---|---|
| Q1 リポジトリと公開範囲 | 非公開で始める | private の独立 git。ただし規則は ser_dataset_db と同じく公開前提で書く(個人名・ローカルパス・内部リンクは `local/` へ) |
| Q2 対象のモダリティ | EEG の定義に入るものは全部。SSL に入れられれば何でもよい | 頭皮 EEG(低チャネル・民生機器・ear-EEG を含む)、PSG の中の EEG、iEEG(ECoG・sEEG)を含める。MEG だけのものは EEG ではないので対象外、EEG を同時計測していれば含める(解釈。違えば直す) |
| Q3 個人特性の粒度 | 資料の要約値 + 参加者表の項目の有無 | `participant_groups` と `participant_fields`。1 人 1 行は DB に入れない |
| Q4 論文 DB | 後で考える | 論文は `sources` として持つ |
| 追加の指示 | 取得が AI で完結するか(人の申請が要るか)を重視。自動取得できて学習に使えるものを重点的に調べる | §4 を新設し、段階 3〜6 を入れ替えた |
| Q5 配布物を数えた値の出典 | 未決 | 段階 1 で議論 |

## 付録 A. Excel の列の行き先

| Excel(シート: 列) | 行き先 |
|---|---|
| Basic_info: Dataset_ID, Dataset_Name | `datasets.dataset_id`(規則に合わせて小文字化), `name` / `full_title` |
| Modaliry | `datasets.modality` + `acquisition_setups` の同時計測 |
| Domain | `datasets.domain` |
| Source_URL, Source_Paper, Source_Paper_Year | `sources` + `dataset_sources`(distribution / paper), `datasets.year` |
| #Subjects/Patients, #Sessions, #File, Total_Duration_hours, Dataset_Size_GB | `datasets` の `*_reported` / `*_release` |
| Measurement_Device, Channel_Configuration, #Channel, Sampling_Rate_Hz | `acquisition_setups`(+ `channels`) |
| Parent_Dataset_ID | `relations`(subset_of など) |
| Task_ID | `benchmarks`(実験課題は `tasks`) |
| Preprocessing_ID | `distributed_versions`(提供者の処理)/ `local/`(自分たちの処理) |
| Provider_ID | `providers` |
| License_Type, Commercial_Use | `license_spdx`, `license_note`(商用可否は資料の記述として) |
| Download_Date, OneDrive_Link_*, Checked_Date, Checked_Person | `local/`(DB の確認記録は `checked_on`・`checked_by` と確認 PR) |
| Notes | `notes`(出典タグつき) |
| Task_Definition: Task_Name, Task_Type, Evaluation_Metric, Evaluation_Result, #Classes, Class information, Memo | `benchmarks` |
| Provider_Master: Provider_Name, Provider_Type, Country | `providers` |
| Provider_Preprocessing: Resampling_Hz, Filtering, Segmentation, Normalization_Method | `distributed_versions` / `local/` |
