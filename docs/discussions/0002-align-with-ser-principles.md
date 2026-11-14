# 0002 ser_dataset_db の理念・原則と進め方に合わせる

状態: 決定(2026-11-14、maintainer の指示「ser_dataset_db のやり方をちゃんと確認し、同じ思想を引き継ぐ」による。この文書は、それに従って直したことと、その理由)
関連: [0001](0001-table-design.md)(第一版。この文書で §3.2〜3.4 が決着)、ser_dataset_db の `docs/manual.ja.md` §2(理念・原則)と DB 管理の skill

## 1. 確認したこと(ser_dataset_db の要点)

- **理念**: 研究者がデータセットを調べるコストを下げるために、最新情報を網羅的に集め、誰もが一次資料を確かめられる DB を提供する
- **原則**(優先順位なし): 検証可能性・網羅性・最新性・透明性・中立性
- **DB は自分で事実を作らない**(skill の規則 1)。ファイルを数えない・重複を探さない・測らない。
  数えないと分からない値は、recipe の readme が書くまで空欄
- **進め方は 2 段**: 資料調査(論文・配布ページなど一次資料から登録。`documents_checked`)→
  使えそうなものは ESPnet でレシピを作り、readme の `## The data` 節に配布物の事実を書く →
  実装調査(その節を公開フォークのコミットで引用。`implementation_checked`)
- **`implementation` の出典は recipe の readme だけ**。`*_release` と `access_observed` はこれだけが根拠になれる
- **表記の正規化は DB、意味の対応づけは `local/`**: `label_normalization` は大文字小文字・語形・資料が示す翻訳だけ。
  略号や翻訳などの「誰がやっても同じ」統合も、1 段目の統合表として `local/` に置いている(SER の discussions/0004)

## 2. 直したこと

| 第一版(0001) | 直した後 | 理由 |
|---|---|---|
| DB 側の道具で数えた結果を `count_report` として出典にできる | 削除。`implementation` は recipe の readme(`kind=readme`、`publisher=recipe_author`)だけ。`*_release` と `access_observed` はこれだけが根拠 | 規則 1(DB は事実を作らない)。数える作業はレシピを作る段階で readme に書く |
| 入手できるかを DB 側で試す道具を作る(了承を得てファイルを落とす) | やめる。`access_observed` は readme の「Access」から写す | 同上。試すのはレシピを作る人 |
| `participant_fields.n_with_value` を数える余地 | 資料(readme を含む)が書いたときだけ | 同上 |
| `channels.standard_name`(表記の揺れを直した 10-05 名) | 削除。`channels.channel_name` は資料の表記のまま。別表 `channel_normalization` に、大文字小文字だけの違い(`case`)と、そのデータセット自身の資料が「この名前はこの電極」と書いているもの(`source_stated`、出典つき)だけ | 下の §3 |
| ライセンスの語彙は独自 | SER と同じ SPDX と `LicenseRef-*`(PhysioNet の 2 つを追加) | 同じ思想を引き継ぐ |
| 入手方法の語彙は独自(open_direct など) | SER の語彙(`direct_download` など)に合わせ、EEG で要る 3 つを足した: `site_terms_agreement`(サイトに 1 回同意)・`credentialed_training`(PhysioNet の資格審査など) | 同上。足した理由は §4 |
| `dataset_id` の決め方なし | SER と同じ。レシピを作ったら egs3 のレシピ名。OpenNeuro は受付番号(`ds003478`) | 同上 |

## 3. チャネル名の判断

**判断: DB は資料の表記をそのまま記録する。旧名と新名の読み替え(T3→T7 など)、参照の付いた名前からの電極名の取り出し(`EEG FP1-REF`→`Fp1`)、
双極導出(`FP1-F7`)の扱いは DB に入れない。**

原則に照らした理由:

- **中立性**: T3 と T7 を同じとみなすのは、ACNS などの規格に従うという選択である。データセットによっては
  電極の位置そのものが違う(キャップの製品ごとの配置、10-20 のつもりの近似)可能性があり、
  読み替えが正しいかは DB が決めることではない。SER でラベルの意味の対応づけを DB に置かないのと同じ
- **検証可能性**: 読み替えた名前には、そのデータセットの一次資料という出典がない。出典が言っていない値になる
- **例外**: そのデータセット自身の資料が対応を書いているとき(例: 配布元の文書が「`EEG FP1-REF` は Fp1 を参照電極に対して記録したもの」と書く)は、
  出典つきで `channel_normalization`(`rule=source_stated`)に入れられる。SER の `source_translation` と同じ考え方
- **学習で要る統一**(全データセットのチャネルを共通の配置に揃えるなど)は、SER のラベル統合と同じく
  プロジェクトの判断として `local/` に置く。DB はその材料(資料の表記・順番・種類・配置方式・座標の有無)を揃える

## 4. 入手方法に足した値

- `site_terms_agreement`: OpenNeuro は、ダウンロードページに**サイト共通の同意**(「I Agree」を押すと、所属機関の許可があること・個人を特定しないことを確約する)を出す。
  ブラウザごとに 1 回で、データセットごとではない。アカウントも要らない。SER の語彙ではどれにも当たらないので足した。人の作業は「サイトごとに 1 回」なので tier は `one_time_human`
- `credentialed_training`: PhysioNet の credentialed access(資格審査+研修の修了)。SER の `signed_agreement` とは手続きが違う

**OpenNeuro の注意点(maintainer に判断してほしいこと)**: 同じダウンロードページに `aws s3 sync --no-sign-request` の手順も出ていて、S3 からは同意を押さずに技術的には取れる。
同意の文言は「OpenNeuro からのダウンロード」についての確約である。S3 で取ることがこの同意の対象かどうかは DB は判断せず、
経路の値は同意があるとおり `site_terms_agreement`、手段として `aws-s3` を記録した。研究計画上「AI で完結」と数えるかは maintainer の判断(`local/`)。

## 5. 資料調査の進め方(今回の作業)

1. OpenNeuro: GraphQL API で EEG・iEEG・MEG のデータセットを全件(612)取り、EEG か iEEG を含むものを登録。
   値はすべてスナップショットの記録(データセットのページが表示する値)と配布物の中のメタデータ文書
   (`dataset_description.json`・`participants.json/tsv`・`*_eeg.json` 1 つ・`*_channels.tsv` 1 つ)から。`checked_by=script`
   - 被験者数はページの「Participants」、容量はページの「Size」(資料の値なので `*_reported`)
   - サイドカーが最上位に無いときは最初の被験者の最初の記録のものを読み、`acquisition_setups.description` に「1 つの記録のもの、他は読んでいない」と書く
   - 論文・README の本文はまだ読んでいない(パラダイムの分類・被験者群の要約値・品質情報は空欄)
2. OpenNeuro 以外(PhysioNet・BNCI Horizon・TUH・Zenodo・figshare・OSF・Kaggle・Hugging Face・Excel の 11 件・foundation model 論文が使ったもの):
   候補の一覧を作り、1 件ずつ一次資料を読んで登録する
3. 実装調査(レシピを作って readme の `## The data` を書く)は、資料調査が一通り済んでから。OpenBMI の試作レシピ
   (ブランチ `espnet3/eeg-openbmi`、システム `eegcls`)を土台にする。今の readme には `## The data` 節が無いので、実装調査のときに足す
