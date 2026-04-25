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
    normalized = (text or "").lower().replace("ё", "е")
    normalized = re.sub(r"[^a-zа-я0-9_\s-]+", " ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _has_any(text: str, words: set[str]) -> bool:
    return any(word in text for word in words)


# Слова, которые обычно означают, что пользователь действительно спрашивает
# аналитический вопрос по датасету. Используем подстроки, чтобы ловить формы:
# "заказ", "заказов", "заказы", "водителей", "водитель" и т.д.
METRIC_WORDS = {
    "заказ",
    "поезд",
    "рейс",
    "отмен",
    "удален",
    "удалени",
    "отклон",
    "тендер",
    "водител",
    "пассажир",
    "пользовател",
    "клиент",
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
    "квартал",
    "период",
    "дата",
    "длитель",
    "время",
    "расстоя",
    "процент",
    "конверс",
    "активн",
    "онлайн",
    "rate",
    "колич",
    "count",
    "sum",
    "avg",
    "max",
    "min",
    "средн",
    "максим",
    "миним",
}

ACTION_WORDS = {
    "сколько",
    "покажи",
    "выведи",
    "напиши",
    "дай",
    "посчитай",
    "считай",
    "найди",
    "сравни",
    "сравнить",
    "построй",
    "отобрази",
    "топ",
    "top",
    "рейтинг",
    "самый",
    "самые",
    "какой",
    "какая",
    "какие",
    "где",
    "кто",
    "show",
    "get",
    "calculate",
    "find",
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

GREETINGS_OR_CHITCHAT = {
    "привет",
    "hello",
    "hi",
    "как дела",
    "помоги",
    "начать",
    "старт",
}


# Частые русские служебные слова. Если текст состоит только из них и не содержит
# предметной области, SQL генерировать нельзя.
STOP_WORDS = {
    "и",
    "а",
    "но",
    "или",
    "по",
    "за",
    "на",
    "в",
    "во",
    "с",
    "со",
    "к",
    "от",
    "до",
    "для",
    "мне",
    "пожалуйста",
    "это",
    "что",
    "как",
    "там",
    "тут",
    "вот",
}


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


def _not_analytics_question(reason: str, message: str, confidence: float = 0.1) -> ClarificationResult:
    return ClarificationResult(
        needs_clarification=True,
        reason=reason,
        clarification_question=message,
        options=_generic_metric_options(),
        confidence=confidence,
    )


def _looks_like_random_text(q: str, tokens: list[str]) -> bool:
    """Heuristic for keyboard mash / meaningless input.

    We keep it conservative: if the phrase contains domain words like заказ/водител,
    it will not be blocked here.
    """
    compact = re.sub(r"\s+", "", q)
    letters = re.findall(r"[a-zа-я]", compact)
    if not letters:
        return True

    if _has_any(q, METRIC_WORDS) or _has_any(q, ACTION_WORDS):
        return False

    # Very short non-domain input like "ыые", "asd", "???".
    if len(letters) < 5:
        return True

    # Repeated/low-diversity keyboard input: "ыыыыы", "фывфыв", "asdfasdf".
    unique_ratio = len(set(letters)) / max(len(letters), 1)
    if len(letters) <= 10 and unique_ratio <= 0.45:
        return True

    # One or two unknown words without a clear analytics action/domain is likely not a request.
    meaningful_tokens = [token for token in tokens if token not in STOP_WORDS and not token.isdigit()]
    if len(meaningful_tokens) <= 2:
        return True

    return False


def analyze_question_for_clarification(question: str) -> ClarificationResult:
    """Pre-check for /analytics/ask before Ollama.

    Goals:
    1. Do not send garbage/non-analytics text to LLM.
    2. Ask clarifying questions for underspecified business requests.
    3. Let specific analytics requests pass to templates/LLM.
    """
    q = _normalize(question)
    tokens = q.split()

    if not q:
        return _not_analytics_question(
            "empty_question",
            "Напишите бизнес-вопрос по данным заказов, пассажиров или водителей.",
            confidence=0.05,
        )

    if q in GREETINGS_OR_CHITCHAT:
        return _not_analytics_question(
            "not_an_analytics_question",
            "Какой показатель по заказам, пассажирам или водителям нужно посчитать?",
            confidence=0.2,
        )

    if _looks_like_random_text(q, tokens):
        return _not_analytics_question(
            "invalid_or_random_text",
            "Я не понял запрос. Уточните, какой показатель вы хотите получить по данным.",
            confidence=0.05,
        )

    has_metric_or_domain = _has_any(q, METRIC_WORDS)
    has_action = _has_any(q, ACTION_WORDS)

    # A phrase with neither action nor domain terms should not reach Ollama.
    # Example: "ыые", "что-нибудь", "сделай красиво".
    if not has_metric_or_domain and not has_action:
        return _not_analytics_question(
            "not_an_analytics_question",
            "Запрос не похож на аналитический вопрос. Уточните, что нужно посчитать или показать.",
            confidence=0.1,
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
    has_specific_metric = _has_any(q, METRIC_WORDS - {"город", "водител", "пассажир", "пользовател", "клиент"})
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
