"""Пакет «Решатель»: отвечает на вопросы пакетов вместо человека.

Здесь скилл критического мышления и порядок работы пары решателей:

1. Обычный вопрос решает первый решатель один.
2. Важный вопрос оба решателя решают вслепую, не видя ответа друг друга.
   Совпали — решено. Разошлись — это сомнение: начинается короткий спор.
3. В каждом круге спора решатель видит позицию собрата и либо остаётся при своём,
   либо меняет решение, либо соглашается с собратом. Число кругов задаёт оболочка.
4. Если после всех кругов согласия нет — берётся решение, которое дешевле отменить
   (оценки «цены отмены» дают оба решателя). Спорного ответа не остаётся.

Какие агенты и модели стоят за решателями, определяет оболочка: пакет получает от неё
объект ``env`` и просто спрашивает решателя номер 0 или 1.
"""

from __future__ import annotations

from pathlib import Path

__version__ = "0.1.0"


def brief(question: dict, env) -> str:
    """Вводные для решателя: вопрос, карточки, о которых он, и общая картина."""
    lines = ["ВОПРОС, на который нужно ответить вместо человека:", question["question"]]
    if question.get("comment"):
        lines.append("Комментарий пакета, задавшего вопрос: " + question["comment"])
    lines.append("Варианты:")
    for index, option in enumerate(question["options"], 1):
        tail = f" — {option['consequence']}" if option.get("consequence") else ""
        lines.append(f"{index}. {option['title']}{tail}")
    if question.get("recommended"):
        lines.append(f"Пакет рекомендует вариант {question['recommended']}"
                     + (f": {question['reason']}" if question.get("reason") else "")
                     + " Ты не обязан соглашаться.")
    cards = list(dict.fromkeys(question.get("cards", []) + question.get("revisits", [])))
    if cards:
        lines.append("\nКарточки, о которых вопрос:")
        for card_id in cards:
            lines.append(env.card(card_id))
            lines.append("")
    lines.append("Общая картина — оглавление графа:")
    lines.append(env.outline())
    past = env.past_decisions()
    if past:
        lines.append("\nТвои прошлые решения по этой идее (не противоречь им без причины):")
        lines.append(past)
    lines.append("\n" + env.deleted())
    lines.append("\nРеши вопрос по порядку из своей инструкции и вызови decide.")
    return "\n".join(lines)


def describe(question: dict, decision: dict) -> str:
    chosen = decision["chosen"]
    if chosen["type"] == "option":
        return f"вариант {chosen['index']} — «{chosen['value']}»"
    if chosen["type"] == "custom":
        return f"своё решение: «{chosen['value']}»"
    return "отклонить все варианты"


def same(first: dict, second: dict) -> bool:
    a, b = first["chosen"], second["chosen"]
    if a["type"] != b["type"]:
        return False
    if a["type"] == "option":
        return a["index"] == b["index"]
    if a["type"] == "custom":
        return " ".join(a["value"].lower().split()) == " ".join(b["value"].lower().split())
    return True


def debate_note(question: dict, mine: dict, other: dict, round_number: int, rounds: int) -> str:
    return "\n".join([
        f"СПОР, круг {round_number} из {rounds}. Второй решатель ответил на тот же вопрос иначе.",
        f"Твоё решение: {describe(question, mine)}. Твоё обоснование: {mine['rationale']}",
        f"Решение собрата: {describe(question, other)}. Его обоснование: {other['rationale']}",
        "Взвесь оба решения честно: что говорит за решение собрата и против твоего.",
        "Вызови decide: choice=agree — если собрат прав; иначе повтори или измени своё решение и ответь на его довод.",
        "Обязательно оцени undo_cost (цена отмены твоего решения) и undo_cost_other (цена отмены решения собрата).",
    ])


def _position(slot: int, question: dict, decision: dict) -> dict:
    return {"slot": slot + 1, "value": describe(question, decision), "rationale": decision["rationale"]}


def _final(question, decision, slot, *, disputed=False, positions=None, extra="", assumption=None):
    return {
        "chosen": decision["chosen"],
        "rationale": (decision["rationale"] + (" " + extra if extra else "")).strip(),
        "assumption": decision["assumption"] if assumption is None else assumption,
        "disputed": disputed,
        "positions": positions or [],
        "by": f"decider:{slot + 1}",
    }


def resolve(question: dict, env) -> dict | None:
    """Вынести решение по вопросу. Возвращает итог или ``None``, если решатель не ответил."""
    note = brief(question, env)
    first, first_session = env.ask(0, note)
    if first is None:
        return None
    if not env.important:
        return _final(question, first, 0)

    second, second_session = env.ask(1, note)
    if second is None:                      # второй решатель недоступен — решение первого, но с пометкой
        return _final(question, first, 0, extra="(Второй решатель не ответил: решение принято одним.)")
    if same(first, second):
        return _final(question, first, 0, assumption=first["assumption"] or second["assumption"])

    opening = [_position(0, question, first), _position(1, question, second)]
    for number in range(1, env.rounds + 1):
        answer_first, first_session = env.ask(
            0, debate_note(question, first, second, number, env.rounds), first_session, allow_agree=True)
        answer_second, second_session = env.ask(
            1, debate_note(question, second, first, number, env.rounds), second_session, allow_agree=True)
        next_first = _after(answer_first, first, second)
        next_second = _after(answer_second, second, first)
        first, second = next_first, next_second
        if same(first, second):
            return _final(question, first, 0, disputed=True, positions=opening,
                          extra=f"(Решатели сначала разошлись и сошлись в круге {number}.)",
                          assumption=first["assumption"] or second["assumption"])

    # Согласия нет: берём то, что дешевле отменить. При равенстве — решение первого решателя.
    cost_first = first["undo_cost"] + second["undo_cost_other"]
    cost_second = second["undo_cost"] + first["undo_cost_other"]
    winner, slot = (first, 0) if cost_first <= cost_second else (second, 1)
    return _final(question, winner, slot, disputed=True, positions=opening,
                  extra="(Решатели не сошлись; взято решение, которое дешевле отменить.)")


def _after(answer: dict | None, mine: dict, other: dict) -> dict:
    """Позиция решателя после круга спора: согласился с собратом, изменил решение или остался при своём."""
    if answer is None:
        return mine
    if answer["chosen"]["type"] == "agree":
        return {**other, "rationale": answer["rationale"], "undo_cost": answer["undo_cost_other"],
                "undo_cost_other": answer["undo_cost"], "assumption": other["assumption"] or answer["assumption"]}
    return answer


def manifest() -> dict:
    return {
        "id": "decider",
        "name": "Решатель",
        "description": "Критически взвешивает варианты и отвечает на вопросы пакетов вместо человека. "
                       "На важных вопросах работает парой: два решателя спорят и приходят к одному решению.",
        "kind": "decider",
        "reads": ["идея", "ветка", "решение", "граница"],
        "writes": [],
        "asks": False,
        "model_level": "сильная",
        "outcomes": [],
        "skill": (Path(__file__).parent / "skill.md").read_text(encoding="utf-8"),
        "resolve": resolve,
    }
