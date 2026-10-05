"""Small artificial Japanese tasks; public inputs and scoring keys are distinct types."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Document:
    source_id: str
    owner: str
    topic: str
    version: str
    origin: str
    text: str

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PublicTask:
    task_id: str
    family: str
    question: str
    documents: tuple[Document, ...]
    development: bool = False

    def document(self, source_id: str) -> Document:
        return next(item for item in self.documents if item.source_id == source_id)


@dataclass(frozen=True)
class Witness:
    source_id: str
    quote: str


@dataclass(frozen=True)
class GoldTask:
    task_id: str
    decision: str
    witnesses: tuple[Witness, ...]
    minimum_origins: int = 1
    historical_sources: tuple[str, ...] = ()


def _task(
    family: str,
    number: int,
    question: str,
    material: tuple[tuple[str, str, str, str], ...],
    decision: str,
    witness_indices: tuple[int, ...],
    *,
    minimum_origins: int = 1,
    historical: tuple[int, ...] = (),
    development: bool = False,
) -> tuple[PublicTask, GoldTask]:
    task_id = f"{'development' if development else 'confirmation'}-{family}-{number}"
    documents = tuple(
        Document(f"document-{index + 1}", owner, family, version, origin, text)
        for index, (owner, version, origin, text) in enumerate(material)
    )
    task = PublicTask(task_id, family, question, documents, development)
    gold = GoldTask(
        task_id,
        decision,
        tuple(
            Witness(documents[index].source_id, documents[index].text) for index in witness_indices
        ),
        minimum_origins,
        tuple(documents[index].source_id for index in historical),
    )
    return task, gold


def confirmation_tasks(edition: str = "023") -> tuple[tuple[PublicTask, GoldTask], ...]:
    """24 separately worded parents; exactly six have no determined yes/no answer."""
    if edition == "024":
        return _new_tasks(development=False)
    if edition != "023":
        raise ValueError("unknown task edition")
    recipes = (
        (
            "L1",
            1,
            "申請あおいは、全ての条件を満たして貸出可能ですか。",
            (
                (
                    "受付",
                    "1",
                    "受付",
                    "貸出には研修修了と保険加入の両方が必要です。あおいは研修を修了しました。",
                ),
                ("保険窓口", "1", "保険", "あおいの保険は本日有効です。"),
            ),
            "yes",
            (0, 1),
        ),
        (
            "L1",
            2,
            "作業ひかりの夜間実施は許可できますか。",
            (
                (
                    "作業規程",
                    "1",
                    "規程",
                    "夜間作業には照明と監督者の常駐が必要です。現場の照明は稼働しています。",
                ),
                ("勤務表", "1", "勤務", "ひかりの現場には今夜、監督者が常駐しません。"),
                ("倉庫", "1", "倉庫", "倉庫には予備電球が五個あります。"),
            ),
            "no",
            (0, 1),
        ),
        (
            "L1",
            3,
            "標本みずきは出荷できますか。",
            (
                ("出荷規則", "2", "規則", "出荷には冷却完了、密封、識別札の三条件が必要です。"),
                ("工程記録", "1", "工程", "みずきは冷却を終え、密封されました。"),
                ("検品記録", "1", "検品", "みずきには正しい識別札が付いています。"),
            ),
            "yes",
            (0, 1, 2),
        ),
        (
            "L1",
            4,
            "予約すみれは優先枠を利用できますか。",
            (
                (
                    "予約規則",
                    "1",
                    "規則",
                    "優先枠は登録会員で、かつ期限前に支払った予約だけが利用できます。",
                ),
                ("会員係", "1", "会員", "すみれは登録会員です。"),
                ("入金係", "1", "入金", "すみれの支払日は締切の翌日でした。"),
            ),
            "no",
            (0, 1, 2),
        ),
        (
            "L1",
            5,
            "車両つばきは橋を通行できますか。",
            (
                ("橋管理", "3", "管理", "通行には重量三トン以下、幅二メートル以下が必要です。"),
                (
                    "計量所",
                    "1",
                    "計量",
                    "つばきの重量は三トンで、幅は二メートルです。境界値は許容されます。",
                ),
            ),
            "yes",
            (0, 1),
        ),
        (
            "L1",
            6,
            "施設はるかは開館条件を満たしていますか。",
            (
                ("開館規則", "1", "規則", "開館には非常灯の点検完了と水質検査の合格が必要です。"),
                (
                    "点検班",
                    "1",
                    "点検",
                    "はるかの非常灯点検は完了しました。水質の結果は記載されていません。",
                ),
            ),
            "unknown",
            (0, 1),
        ),
        (
            "L2",
            1,
            "二つ以上の独立した発行元で、区画いぶきの安全確認は成立しますか。",
            (
                ("調査班", "1", "調査A", "いぶきは安全です。この報告の原本は調査Aです。"),
                ("広報", "1", "調査A", "いぶきは安全です。この資料は調査Aの報告の転載です。"),
                ("消防", "1", "消防", "独立した消防点検でも、いぶきの安全を確認しました。"),
            ),
            "yes",
            (0, 2),
        ),
        (
            "L2",
            2,
            "二つ以上の独立した発行元で、棚かえでの耐荷重合格は成立しますか。",
            (
                ("試験所", "1", "試験A", "かえでの耐荷重は合格でした。"),
                ("営業部", "1", "試験A", "かえでの耐荷重は合格でした。これは試験Aの転載です。"),
                (
                    "大学",
                    "1",
                    "大学",
                    "独立試験で、かえでの耐荷重は不合格でした。反証がある場合は合格成立としません。",
                ),
            ),
            "no",
            (0, 2),
        ),
        (
            "L2",
            3,
            "二つ以上の独立した発行元で、泉ゆずの飲用可能判定は成立しますか。",
            (
                ("衛生所", "2", "衛生", "ゆずの水は飲用可能です。"),
                ("研究所", "1", "研究", "独立した採水検査で、ゆずの水は飲用可能でした。"),
            ),
            "yes",
            (0, 1),
        ),
        (
            "L2",
            4,
            "二つ以上の独立した発行元で、荷物なぎの破損なし判定は成立しますか。",
            (
                ("配送", "1", "配送", "なぎは破損なしとして発送しました。"),
                (
                    "受取人",
                    "1",
                    "受取人",
                    "独立した受取時確認では、なぎに破損がありました。反証がある場合は成立しません。",
                ),
                (
                    "販売店",
                    "1",
                    "配送",
                    "配送記録によれば、なぎは破損なしです。この記載は配送記録の転載です。",
                ),
            ),
            "no",
            (0, 1),
        ),
        (
            "L2",
            5,
            "独立した二発行元の確認を必要とします。部品れんは適合していますか。",
            (
                ("製造", "1", "製造", "れんは適合しています。独立発行元が二つ必要です。"),
                (
                    "広報",
                    "1",
                    "製造",
                    "れんは適合しています。この資料は製造記録の複写です。独立調査は未実施です。",
                ),
            ),
            "unknown",
            (0, 1),
        ),
        (
            "L2",
            6,
            "独立した二発行元の確認を必要とします。山道あさひは通行可能ですか。",
            (
                (
                    "管理者",
                    "1",
                    "管理",
                    "あさひは通行可能と報告しました。判定には独立発行元が二つ必要です。",
                ),
                (
                    "観光案内",
                    "1",
                    "管理",
                    "あさひは通行可能です。管理者の報告を転載しています。別の確認はありません。",
                ),
                (
                    "天候係",
                    "1",
                    "天候",
                    "本日の平地の天気は晴れです。山道の通行状況は確認していません。",
                ),
            ),
            "unknown",
            (0, 1),
        ),
        (
            "L3",
            1,
            "現行規則で、まことは入場できますか。",
            (
                (
                    "旧規則",
                    "1",
                    "規則",
                    "旧版では会員証だけで入場できました。現行版ではありません。",
                ),
                ("現行規則", "2", "規則", "現行版では会員証と本人確認が必要です。"),
                (
                    "受付",
                    "1",
                    "受付",
                    "まことは会員証を持っていますが、本人確認を済ませていません。",
                ),
            ),
            "no",
            (1, 2),
        ),
        (
            "L3",
            2,
            "現行の例外を含めて、ひなたは薬品保管庫を利用できますか。",
            (
                (
                    "規程",
                    "3",
                    "規程",
                    "現行規程では資格者だけが利用できます。ただし立会いのある見学者は例外です。",
                ),
                ("訪問記録", "1", "訪問", "ひなたは無資格の見学者で、資格者が立ち会っています。"),
            ),
            "yes",
            (0, 1),
        ),
        (
            "L3",
            3,
            "再検査後の現在、しおりの装置は使用可能ですか。",
            (
                ("検査所", "1", "検査", "初回検査で、しおりの装置は使用可能でした。"),
                (
                    "検査所",
                    "2",
                    "検査",
                    "最新の再検査で、しおりの装置は使用不可でした。最新結果を優先します。",
                ),
            ),
            "no",
            (1,),
        ),
        (
            "L3",
            4,
            "現行制度で、こうきの申請は手数料免除ですか。",
            (
                (
                    "制度",
                    "2",
                    "制度",
                    "現行制度は全員有料ですが、災害対象地域の居住者は免除します。",
                ),
                ("住所係", "1", "住所", "こうきは災害対象地域に居住しています。"),
                (
                    "旧案内",
                    "1",
                    "制度",
                    "旧制度では学生だけが免除されました。この制度は失効しています。",
                ),
            ),
            "yes",
            (0, 1),
        ),
        (
            "L3",
            5,
            "現行規則で、さくらの申請は期限内ですか。",
            (
                ("期限規則", "2", "規則", "現行締切は九月三十日です。当日の提出も期限内です。"),
                ("受領係", "1", "受領", "さくらの申請を九月三十日に受領しました。"),
                ("旧期限", "1", "規則", "旧締切は九月二十日でした。旧規則は置換済みです。"),
            ),
            "yes",
            (0, 1),
        ),
        (
            "L3",
            6,
            "最新規則で、たくみは運転できますか。",
            (
                (
                    "旧規則",
                    "1",
                    "規則",
                    "旧版では基礎資格だけで運転可能でした。新版が制定されています。",
                ),
                (
                    "資格係",
                    "1",
                    "資格",
                    "たくみは基礎資格を持っています。新版の運転条件はこの資料にはありません。",
                ),
            ),
            "unknown",
            (0, 1),
        ),
        (
            "L4",
            1,
            "本日の店そらは営業していますか。",
            (
                ("店舗", "1", "店舗", "そらは本日営業しています。"),
                ("交通", "1", "交通", "近くのバス停は移転しました。"),
            ),
            "yes",
            (0,),
        ),
        (
            "L4",
            2,
            "切符ときは払い戻し可能ですか。",
            (
                ("窓口", "1", "窓口", "ときは払い戻し不可の切符です。"),
                ("車内案内", "1", "車内", "車内は禁煙です。"),
                ("売店", "1", "売店", "売店は午前八時に開きます。"),
            ),
            "no",
            (0,),
        ),
        (
            "L4",
            3,
            "図書うみは貸出中ですか。",
            (
                ("図書館", "1", "図書館", "うみは現在貸出中です。"),
                ("書誌", "1", "書誌", "うみは三百ページの本です。"),
            ),
            "yes",
            (0,),
        ),
        (
            "L4",
            4,
            "箱もりは要冷蔵ですか。",
            (
                ("商品表示", "1", "表示", "もりは常温保存の商品で、冷蔵は不要です。"),
                ("販売", "1", "販売", "もりの販売価格は千円です。"),
            ),
            "no",
            (0,),
        ),
        (
            "L4",
            5,
            "会議ほしは九月三十日に開催されますか。",
            (
                ("事務局", "1", "事務局", "ほしの会議日は調整中です。開催日は確定していません。"),
                ("会場", "1", "会場", "会場には二つの会議室があります。"),
            ),
            "unknown",
            (0,),
        ),
        (
            "L4",
            6,
            "荷物つきは到着済みですか。",
            (
                ("運送", "1", "運送", "つきの発送は記録されています。到着を示す記録はありません。"),
                ("受取窓口", "1", "受取", "つきの到着状況は未確認です。"),
            ),
            "unknown",
            (0, 1),
        ),
    )
    obsolete = {("L3", 1): (0,), ("L3", 3): (0,), ("L3", 4): (2,), ("L3", 5): (2,)}
    return tuple(
        _task(
            *recipe,
            minimum_origins=2 if recipe[0] == "L2" and recipe[4] != "unknown" else 1,
            historical=obsolete.get((recipe[0], recipe[1]), ()),
        )
        for recipe in recipes
    )


def development_tasks(edition: str = "023") -> tuple[tuple[PublicTask, GoldTask], ...]:
    """Four pilot-only parents; no document text is reused in confirmation."""
    if edition == "024":
        return _new_tasks(development=True)
    if edition != "023":
        raise ValueError("unknown task edition")
    return (
        _task(
            "L1",
            1,
            "講座ふたばは開講できますか。",
            (
                (
                    "講座規則",
                    "1",
                    "規則",
                    "開講には講師と教室の確保が必要です。講師は確保済みです。",
                ),
                ("教室係", "1", "教室", "ふたばの教室は確保済みです。"),
            ),
            "yes",
            (0, 1),
            development=True,
        ),
        _task(
            "L2",
            1,
            "独立した二発行元で、機器にじは適合していますか。",
            (
                ("技術班", "1", "技術", "にじは適合しています。"),
                ("大学班", "1", "大学", "独立試験でも、にじは適合しています。"),
            ),
            "yes",
            (0, 1),
            minimum_origins=2,
            development=True,
        ),
        _task(
            "L3",
            1,
            "最新記録で、路線かぜは運行していますか。",
            (
                ("運行係", "1", "運行", "旧記録では、かぜは運休でした。"),
                ("運行係", "2", "運行", "最新記録では、かぜは運行しています。"),
            ),
            "yes",
            (1,),
            historical=(0,),
            development=True,
        ),
        _task(
            "L4",
            1,
            "荷物ゆきは午前十時に受領されましたか。",
            (
                ("受領係", "1", "受領", "ゆきの受領日は判明していますが、受領時刻は未記録です。"),
                ("倉庫", "1", "倉庫", "倉庫の入口は南側です。"),
            ),
            "unknown",
            (0,),
            development=True,
        ),
    )


def calibration_tasks() -> tuple[tuple[PublicTask, GoldTask], ...]:
    return _new_tasks(development=False, calibration=True)


def _new_tasks(
    *, development: bool, calibration: bool = False
) -> tuple[tuple[PublicTask, GoldTask], ...]:
    """New finite rule parents, independent of every v0.2.3 document.

    Every permission rule is explicitly necessary AND sufficient. Gold records
    minimal exact spans derived from those public rules, rather than full-document
    memorization. Unknown denotes absent world information after the relevant
    record is retrieved, not a failure to retrieve an available document.
    """
    result = []
    for family in ("L1", "L2", "L3", "L4"):
        for number in (1,) if development else range(1, 7):
            prefix = "校正" if calibration else ("予備" if development else "新規")
            ident = f"{prefix}-{family}-{number}"
            unknown = (family, number) in {
                ("L1", 6),
                ("L2", 5),
                ("L2", 6),
                ("L3", 6),
                ("L4", 5),
                ("L4", 6),
            } or (development and family == "L4")
            decision = "unknown" if unknown else ("yes" if number % 2 else "no")
            rule = "条件Pと条件Qが両方真である場合に限り許可する。他の条件や例外はない。"
            fact_p = f"{ident}の条件Pは真と確認した。"
            fact_q = f"{ident}の条件Qは{'真' if decision == 'yes' else '偽'}と確認した。"
            if unknown:
                fact_q = f"{ident}の条件Qの真偽は未記録である。"
            question = f"公開規則に従い、対象{ident}を許可できるか。未記録は偽とせずunknownとする。"
            material = [
                ("規則当局", "1", "規則当局", rule + fact_p),
                ("観測当局", "1", "観測当局", fact_q + "備品の色は白である。"),
            ]
            witnesses = [(0, rule), (0, fact_p), (1, fact_q)]
            minimum, historical = 1, ()
            if family == "L2":
                rule = (
                    "独立した二発行元が適合と報告した場合に限り許可する。転載は独立発行元でない。"
                )
                p = f"{ident}は適合と検査甲が報告した。"
                q = (
                    f"{ident}の適合性は検査乙では未確認である。"
                    if unknown
                    else f"{ident}は{'適合' if decision == 'yes' else '不適合'}と検査乙が報告した。"
                )
                material = [
                    ("規則当局", "1", "規則", rule),
                    ("検査甲", "1", "独立甲", p),
                    ("広報", "1", "独立甲", "以下は検査甲の転載である。" + p),
                    ("検査乙", "1", "独立乙", q),
                ]
                witnesses, minimum = [(0, rule), (1, p), (3, q)], 3
                question += "発行元の同一性は公開originで判定する。"
            elif family == "L3":
                rule = (
                    "現行版2で条件Pが真かつ禁止例外Qが偽の場合に限り許可する。旧版1は失効している。"
                )
                q = (
                    f"{ident}の禁止例外Qは未確認である。"
                    if unknown
                    else f"{ident}の禁止例外Qは{'偽' if decision == 'yes' else '真'}である。"
                )
                current = fact_p + q
                material = [
                    ("規則当局", "2", "規則", rule),
                    ("記録当局", "1", "記録", f"旧版1では{ident}は許可された。"),
                    ("記録当局", "2", "記録", current),
                ]
                witnesses, historical = [(0, rule), (2, fact_p), (2, q)], ("document-2",)
                question += "記録当局の現行版2を用いる。"
            elif family == "L4":
                rule = (
                    "記録当局が当日到着済みと確認した場合に限り許可する。"
                    "発送だけでは到着を意味しない。"
                )
                fact = (
                    f"{ident}の当日到着状況は未確認である。"
                    if unknown
                    else f"{ident}は当日{'到着済み' if decision == 'yes' else '未到着'}と確認した。"
                )
                material = [
                    ("規則当局", "1", "規則", rule),
                    ("記録当局", "1", "記録", fact + f"{ident}は発送済みである。"),
                    ("倉庫", "1", "倉庫", "棚番号は七である。"),
                ]
                witnesses = [(0, rule), (1, fact)]
            prefix = (
                "calibration024"
                if calibration
                else ("development024" if development else "confirmation024")
            )
            task_id = f"{prefix}-{family}-{number}"
            docs = tuple(
                Document(f"document-{i + 1}", owner, family, version, origin, text)
                for i, (owner, version, origin, text) in enumerate(material)
            )
            task = PublicTask(task_id, family, question, docs, development)
            gold = GoldTask(
                task_id,
                decision,
                tuple(Witness(docs[i].source_id, quote) for i, quote in witnesses),
                minimum,
                historical,
            )
            result.append((task, gold))
    return tuple(result)
