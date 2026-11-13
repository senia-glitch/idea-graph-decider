"""Порядок работы пары решателей: вслепую, спор, правило «дешевле отменить»."""

from idea_graph_decider import brief, manifest, resolve, same

QUESTION = {
    "question": "Нужна ли оплата в первой версии?", "comment": "", "recommended": [1], "reason": "проще",
    "options": [{"title": "Да, по СБП", "consequence": "плюс две недели"}, {"title": "Нет", "consequence": ""}],
    "cards": ["c2"], "revisits": [],
}


def option(index, rationale="довод", **extra):
    value = QUESTION["options"][index - 1]["title"]
    return {"chosen": {"type": "choice", "indexes": [index], "values": [value], "text": "", "value": value},
            "rationale": rationale,
            "assumption": False, "undo_cost": 3, "undo_cost_other": 3, **extra}


AGREE = {"chosen": {"type": "agree"}, "rationale": "собрат прав", "assumption": False, "undo_cost": 2, "undo_cost_other": 4}


class Env:
    """Вместо оболочки: решатели отвечают по заранее заданному сценарию."""

    def __init__(self, answers, important=True, rounds=2):
        self.answers = {0: list(answers[0]), 1: list(answers[1])}
        self.important, self.rounds = important, rounds
        self.calls = []

    def ask(self, slot, note, session="", allow_agree=False):
        self.calls.append((slot, "СПОР" in note, session, allow_agree))
        queue = self.answers[slot]
        return (queue.pop(0) if queue else None), f"s{slot}"

    def card(self, card_id):
        return f"[{card_id}] ветка · Деньги"

    def outline(self):
        return "Граф идеи · ревизия 3"

    def past_decisions(self):
        return "- [c5] Только веб: Да"

    def deleted(self):
        return "Удалённых карточек нет."


def test_brief_contains_whole_picture():
    text = brief(QUESTION, Env([[], []]))
    for part in ("Нужна ли оплата", "1. Да, по СБП — плюс две недели", "Пакет рекомендует вариант 1",
                 "[c2] ветка", "Граф идеи", "Только веб", "Удалённых карточек нет"):
        assert part in text


def test_ordinary_question_takes_one_decider():
    env = Env([[option(2)], [option(1)]], important=False)
    final = resolve(QUESTION, env)
    assert final["chosen"]["indexes"] == [2] and final["disputed"] is False and final["by"] == "decider:1"
    assert [c[0] for c in env.calls] == [0]


def test_important_question_agreed_blind():
    env = Env([[option(1)], [option(1, assumption=True)]])
    final = resolve(QUESTION, env)
    assert final["chosen"]["indexes"] == [1] and final["disputed"] is False
    assert final["assumption"] is True and final["positions"] == []      # сомневался хотя бы один — допущение
    assert [c[0] for c in env.calls] == [0, 1] and not any(c[1] for c in env.calls)


def test_dispute_ends_when_one_agrees():
    env = Env([[option(1), AGREE], [option(2, "дешевле отменить"), option(2, "остаюсь")]])
    final = resolve(QUESTION, env)
    assert final["chosen"]["indexes"] == [2] and final["disputed"] is True
    assert "сошлись в круге 1" in final["rationale"]
    assert [p["slot"] for p in final["positions"]] == [1, 2] and "вариант 1" in final["positions"][0]["value"]
    # в споре продолжается та же сессия решателя и разрешено согласиться
    assert env.calls[2] == (0, True, "s0", True) and env.calls[3] == (1, True, "s1", True)


def test_no_agreement_takes_cheaper_to_undo():
    stubborn_first = option(1, undo_cost=5, undo_cost_other=1)
    stubborn_second = option(2, undo_cost=1, undo_cost_other=5)
    env = Env([[option(1)] + [stubborn_first] * 2, [option(2)] + [stubborn_second] * 2], rounds=2)
    final = resolve(QUESTION, env)
    assert final["chosen"]["indexes"] == [2] and final["disputed"] is True and final["by"] == "decider:2"
    assert "дешевле отменить" in final["rationale"] and len(env.calls) == 6


def test_swap_is_still_a_dispute_and_zero_rounds():
    env = Env([[option(1), AGREE], [option(2), AGREE]], rounds=1)        # оба «согласились» — поменялись местами
    final = resolve(QUESTION, env)
    assert final["disputed"] is True and "не сошлись" in final["rationale"]
    env = Env([[option(1, undo_cost=1)], [option(2, undo_cost=4)]], rounds=0)
    assert resolve(QUESTION, env)["chosen"]["indexes"] == [1] and len(env.calls) == 2


def test_failures():
    assert resolve(QUESTION, Env([[], [option(1)]])) is None
    final = resolve(QUESTION, Env([[option(1)], []]))
    assert final["chosen"]["indexes"] == [1] and "не ответил" in final["rationale"]
    # решатель замолчал посреди спора — остаётся при своём
    final = resolve(QUESTION, Env([[option(1, undo_cost=1)], [option(2, undo_cost=5), option(2, undo_cost=5)]], rounds=1))
    assert final["chosen"]["indexes"] == [1]


def test_same_and_manifest():
    custom = lambda text: {"chosen": {"type": "choice", "indexes": [], "values": [], "text": text, "value": text}}
    assert same(custom("Только  веб"), custom("только веб")) and not same(custom("a"), option(1))
    m = manifest()
    assert m["kind"] == "decider" and callable(m["resolve"]) and "undo_cost" in m["skill"]


def test_choice_description_and_comparison():
    from idea_graph_decider import describe
    a = {"chosen": {"type": "choice", "indexes": [1, 3], "values": ["А", "В"], "text": "", "value": "А; В"}}
    b = {"chosen": {"type": "choice", "indexes": [1, 3], "values": ["А", "В"], "text": "", "value": "А; В"}}
    c = {"chosen": {"type": "choice", "indexes": [1], "values": ["А"], "text": "", "value": "А"}}
    d = {"chosen": {"type": "choice", "indexes": [1], "values": ["А"], "text": "и своё", "value": "А; и своё"}}
    assert same(a, b) and not same(a, c) and not same(c, d)
    assert "варианты 1, 3" in describe({}, a) and "и своё: «и своё»" in describe({}, d)
    assert describe({}, {"chosen": {"type": "rejected", "value": ""}}) == "отклонить все варианты"


def test_brief_mentions_choice_and_recommendations():
    question = {"question": "Что учесть?", "options": [{"title": "А"}, {"title": "Б"}, {"title": "В"}], "comment": "",
                "recommended": [1, 3], "reason": "важнее", "cards": [], "revisits": []}

    class Env:
        def card(self, _): return ""
        def outline(self): return ""
        def past_decisions(self): return ""
        def deleted(self): return ""

    text = brief(question, Env())
    assert "choice=choice" in text and "варианты 1, 3" in text
