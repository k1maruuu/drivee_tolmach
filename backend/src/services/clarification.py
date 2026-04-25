import re
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ClarificationOption:
    label: str
    question: str
    template_params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ClarificationResult:
    needs_clarification: bool
    reason: str | None = None
    clarification_question: str | None = None
    options: list[ClarificationOption] = field(default_factory=list)
    confidence: float = 0.0

    def to_payload(self) -> dict[str, Any] | None:
        if not self.needs_clarification:
            return None
        return {
            "message_ru": self.clarification_question or "Уточните запрос.",
            "reason": self.reason,
            "options": [asdict(option) for option in self.options],
        }


def _normalize(text: str) -> str:
    normalized = text.lower().replace("ё", "е")
    normalized = re.sub(r"[^a-zа-я0-9_\s-]+", " ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _has_any(text: str, words: set[str]) -> bool:
    return any(word in text for word in words)


METRIC_WORDS = {
    "заказ",
    "поезд",
    "отмен",
    "удален",
    "удалени",
    "отклон",
    "тендер",
    "водител",
    "пользовател",
    "город",
    "стоим",
    "цен",
    "дорог",
    "дешев",
    "чек",
    "оборот",
    "выруч",
    "доход",
    "сумм",
    "спрос",
    "час",
    "день",
    "недел",
    "месяц",
    "год",
    "длитель",
    "время",
    "расстоя",
    "процент",
    "rate",
    "колич",
    "count",
    "avg",
    "max",
    "min",
    "средн",
    "максим",
    "миним",
}

VAGUE_INTENT_WORDS = {
    "статистика",
    "аналитика",
    "отчет",
    "отчеты",
    "данные",
    "показатели",
    "информация",
    "сводка",
}

RANKING_WORDS = {
    "лучшие",
    "лучший",
    "топ",
    "top",
    "рейтинг",
    "худшие",
    "худший",
    "проблемные",
    "проблемный",
    "эффективные",
    "эффективный",
}

COMPARISON_WORDS = {"сравни", "сравнить", "сравнение", "динамика", "изменение", "дельта"}


def _city_options() -> list[ClarificationOption]:
    return [
        ClarificationOption("По количеству заказов", "Покажи города по количеству заказов"),
        ClarificationOption("По обороту", "Покажи города по сумме price_order_local для завершенных заказов"),
        ClarificationOption("По среднему чеку", "Покажи средний чек по городам"),
        ClarificationOption("По числу отмен", "Покажи топ-10 городов по числу отмен"),
        ClarificationOption("По проценту отклонений", "Покажи города, где самый высокий процент отклонений"),
    ]


def _driver_options() -> list[ClarificationOption]:
    return [
        ClarificationOption("По количеству завершенных заказов", "Кто из водителей выполнил больше всего заказов?"),
        ClarificationOption("По числу отмен", "У каких водителей больше всего отмен?"),
        ClarificationOption("По среднему времени принятия", "Какое среднее время до принятия заказа у каждого водителя?"),
    ]


def _generic_metric_options() -> list[ClarificationOption]:
    return [
        ClarificationOption("Количество заказов", "Сколько всего было заказов?"),
        ClarificationOption("Завершенные заказы", "Сколько заказов было завершено?"),
        ClarificationOption("Отмененные заказы", "Сколько заказов было отменено?"),
        ClarificationOption("Оборот", "Какой общий оборот по завершенным заказам?"),
        ClarificationOption("Средний чек", "Какой средний чек?"),
    ]


def analyze_question_for_clarification(question: str) -> ClarificationResult:
    """Conservative ambiguity detector for /analytics/ask.

    It should only stop obviously underspecified business questions. Specific
    prompts and matched templates must continue to run without clarification.
    """
    q = _normalize(question)
    tokens = q.split()

    if not q:
        return ClarificationResult(
            needs_clarification=True,
            reason="empty_question",
            clarification_question="Напишите бизнес-вопрос по данным заказов.",
            options=_generic_metric_options(),
            confidence=0.15,
        )

    if q in {"привет", "hello", "hi", "как дела", "помоги", "начать"}:
        return ClarificationResult(
            needs_clarification=True,
            reason="not_an_analytics_question",
            clarification_question="Какой показатель по заказам нужно посчитать?",
            options=_generic_metric_options(),
            confidence=0.2,
        )

    # Very broad prompts like "покажи статистику" do not say which metric is needed.
    if len(tokens) <= 3 and _has_any(q, VAGUE_INTENT_WORDS):
        return ClarificationResult(
            needs_clarification=True,
            reason="too_broad_metric",
            clarification_question="Какую именно статистику показать?",
            options=_generic_metric_options(),
            confidence=0.25,
        )

    # "лучшие города" / "рейтинг водителей" is dangerous to guess: best by what?
    has_ranking = _has_any(q, RANKING_WORDS)
    has_specific_metric = _has_any(q, METRIC_WORDS - {"город", "водител", "пользовател"})
    if has_ranking and not has_specific_metric:
        if "город" in q:
            return ClarificationResult(
                needs_clarification=True,
                reason="ambiguous_city_ranking_metric",
                clarification_question="Что считать лучшим городом?",
                options=_city_options(),
                confidence=0.3,
            )
        if "водител" in q:
            return ClarificationResult(
                needs_clarification=True,
                reason="ambiguous_driver_ranking_metric",
                clarification_question="Что считать лучшим водителем?",
                options=_driver_options(),
                confidence=0.3,
            )
        return ClarificationResult(
            needs_clarification=True,
            reason="ambiguous_ranking_metric",
            clarification_question="По какому показателю построить рейтинг?",
            options=_generic_metric_options(),
            confidence=0.3,
        )

    # "сравни города" or "динамика" without a metric is also ambiguous.
    has_comparison = _has_any(q, COMPARISON_WORDS)
    if has_comparison and not has_specific_metric:
        return ClarificationResult(
            needs_clarification=True,
            reason="ambiguous_comparison_metric",
            clarification_question="Какой показатель сравнить?",
            options=_generic_metric_options(),
            confidence=0.35,
        )

    return ClarificationResult(needs_clarification=False)
