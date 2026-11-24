"""实盘公司行为核对闸门；只有用户确认的实际到账才进入实际账本。"""

from dataclasses import asdict
from datetime import date, datetime, time
from decimal import Decimal

from easy_quant.application.services.corporate_actions import runtime_snapshot
from easy_quant.application.services.recommendation_actions import (
    actual_portfolio,
    audit_row,
    ledger_entries,
)
from easy_quant.domain.live_tracking.ledger import PortfolioLedgerEntry, rebuild_portfolio
from easy_quant.domain.market_data.corporate_actions import (
    ZONE,
    CorporateActionBook,
    instant,
    number,
)
from easy_quant.domain.shared.errors import NotFoundError, StateConflictError
from easy_quant.infrastructure.core import UuidGenerator


def pending_actions(state, instance_id: str, book: CorporateActionBook, at: datetime):
    instance = state.instances[instance_id]
    entries = [row for row in ledger_entries(state, instance_id) if row.occurred_at <= at]
    started = instant(instance.get("started_at", at))
    initial = {key: number(value) for key, value in instance.get("initial_positions", {}).items()}
    symbols = set(initial) | {row.symbol for row in entries if row.symbol}
    confirmed = instance.get("corporate_action_confirmations", {})
    pending = []
    active_versions = {
        action.event_id: action for symbol in sorted(symbols) for action in book.events(symbol, at)
    }
    for key, confirmation in confirmed.items():
        if instant(confirmation["confirmed_at"]) <= at and key not in active_versions:
            raise StateConflictError(
                "已确认公司行为被取消或不可见，需人工复核实际账本", {"event_id": key}
            )
    for symbol in sorted(symbols):
        book.require_coverage(
            symbol, started.astimezone(ZONE).date(), at.astimezone(ZONE).date(), at
        )
        publication = book.price_publication(symbol) or {}
        equity_days = {price.ex_date for price in book.price_events(symbol, at)} | {
            date.fromisoformat(issue["ex_date"]) for issue in publication.get("equity_issues", [])
        }
        for ex_day in sorted(equity_days):
            ex_open = datetime.combine(ex_day, time(9), ZONE)
            if ex_open < started or ex_open > at:
                continue
            prior_holdings = rebuild_portfolio(
                number(instance.get("initial_cash", "100000")),
                [
                    row
                    for row in entries
                    if row.occurred_at < datetime.combine(ex_day, time.min, ZONE)
                ],
                initial,
            )
            if prior_holdings.positions.get(symbol, Decimal(0)):
                book.require_equity(symbol, ex_day, at)
        for action in book.events(symbol, at):
            record_at = datetime.combine(action.record_date, time.max, ZONE)
            if record_at < started or action.ex_date > at.astimezone(ZONE).date():
                continue
            old = confirmed.get(action.event_id)
            if old and instant(old["confirmed_at"]) <= at:
                if old["record_key"] != action.record_key:
                    raise StateConflictError(
                        "已核对公司行为发生修订，需要人工复核账本", {"event_id": action.event_id}
                    )
                continue
            holdings = rebuild_portfolio(
                number(instance.get("initial_cash", "100000")),
                [row for row in entries if row.occurred_at <= record_at],
                initial,
            )
            quantity = holdings.positions.get(symbol, Decimal(0))
            if quantity:
                pending.append(
                    {
                        "event_id": action.event_id,
                        "record_key": action.record_key,
                        "symbol": symbol,
                        "ex_date": str(action.ex_date),
                        "record_date": str(action.record_date),
                        "record_quantity": str(quantity),
                        "gross_cash": str(quantity * action.cash_per_share),
                        "share_delta": str(quantity * (action.share_multiplier - 1)),
                        "cash_pay_date": str(action.cash_pay_date)
                        if action.cash_pay_date
                        else None,
                        "shares_listing_date": str(action.shares_listing_date)
                        if action.shares_listing_date
                        else None,
                        "rights_ratio": str(action.rights_ratio),
                        "settled": all(
                            day is None or day <= at.astimezone(ZONE).date()
                            for day in (action.cash_pay_date, action.shares_listing_date)
                        ),
                    }
                )
    return pending


def ensure_reconciled(container, instance_id: str, at: datetime, snapshot: dict) -> None:
    book = CorporateActionBook(snapshot["corporate_actions"])
    with container.live_tracking.transaction() as state:
        pending = pending_actions(state, instance_id, book, at)
        # 价格/数量口径已变的旧建议失效，必须重新运行策略产生建议。
        recommendations = list(state.recommendations.get(instance_id, []))
        changed = False
        for item in recommendations:
            if item.get("status") != "pending":
                continue
            for action in book.price_events(str(item["instrument_id"]), at):
                if (
                    instant(item["decision_at"]).astimezone(ZONE).date()
                    < action.ex_date
                    <= at.astimezone(ZONE).date()
                ):
                    item.update(
                        status="rejected",
                        reason="公司行为后原建议失效，请重新分析",
                        version=int(item.get("version", 0)) + 1,
                    )
                    state.audit.append(
                        audit_row(
                            UuidGenerator(),
                            at,
                            None,
                            "invalidate",
                            "recommendation",
                            str(item["id"]),
                            {},
                            {"event_id": action.event_id, "reason": "公司行为导致旧建议失效"},
                            trigger_source="corporate-action",
                        )
                    )
                    changed = True
                    break
        if changed:
            state.recommendations[instance_id] = recommendations
            instance = dict(state.instances[instance_id])
            instance["state_revision"] = int(instance.get("state_revision", 0)) + 1
            state.instances[instance_id] = instance
    if changed:
        raise StateConflictError("除权前待处理建议已失效，请重新运行分析")
    if pending:
        raise StateConflictError(
            "持仓公司行为尚未核对，暂停生成建议", {"corporate_actions": pending}
        )


def list_pending(container, instance_id: str, owner_id: str):
    snapshot = runtime_snapshot(container.market_data)
    with container.live_tracking.transaction() as state:
        instance = state.instances.get(instance_id)
        if instance is None or instance["owner_id"] != owner_id:
            raise NotFoundError("live_instance")
        return pending_actions(
            state,
            instance_id,
            CorporateActionBook(snapshot["corporate_actions"]),
            container.authentication.clock.now(),
        )


def confirm_action(container, instance_id: str, owner_id: str, payload: dict):
    now = container.authentication.clock.now()
    snapshot = runtime_snapshot(container.market_data)
    key = str(payload.get("event_id", ""))
    with container.live_tracking.transaction() as state:
        instance = state.instances.get(instance_id)
        if instance is None or instance["owner_id"] != owner_id:
            raise NotFoundError("live_instance")
        if instance["status"] == "terminated":
            raise StateConflictError("已终止实盘只读")
        cash, shares = number(payload.get("cash", "NaN")), number(payload.get("share_delta", "NaN"))
        previous = instance.get("corporate_action_confirmations", {}).get(key)
        if previous:
            if (
                previous["record_key"] != payload.get("record_key")
                or number(previous["cash"]) != cash
                or number(previous["share_delta"]) != shares
            ):
                raise StateConflictError("同一公司行为已按其他数额确认，不能重复记账")
            return previous
        pending = pending_actions(
            state, instance_id, CorporateActionBook(snapshot["corporate_actions"]), now
        )
        action = next((row for row in pending if row["event_id"] == key), None)
        if action is None or action["record_key"] != payload.get("record_key"):
            raise StateConflictError("公司行为版本已变化或不属于本实例")
        if number(action["rights_ratio"]):
            raise StateConflictError("配股需核对实际认购/缴款及权益处置，不能使用通用分红确认")
        if (
            not action["settled"]
            or not payload.get("evidence")
            or shares != number(action["share_delta"])
            or shares != shares.to_integral_value()
            or not 0 <= cash <= number(action["gross_cash"])
            or cash != cash.quantize(Decimal("0.01"))
        ):
            raise StateConflictError(
                "请在全部权益实际到账后核对净现金、股份及凭证；不支持隐式碎股处理"
            )
        portfolio = actual_portfolio(state, instance_id)
        if portfolio.positions.get(action["symbol"], Decimal(0)) + shares < 0:
            raise StateConflictError("确认后产生负持仓，请先核对实际成交")
        entries = ledger_entries(state, instance_id)
        row = PortfolioLedgerEntry(
            UuidGenerator().new(),
            instance_id,
            f"corporate:{key}",
            now,
            cash,
            action["symbol"],
            shares,
            Decimal(0),
            max((row.sequence for row in entries), default=0) + 1,
            "corporate_action",
        )
        rebuild_portfolio(
            number(instance.get("initial_cash", "100000")),
            [*entries, row],
            {
                symbol: number(value)
                for symbol, value in instance.get("initial_positions", {}).items()
            },
        )
        state.ledger.append(
            {
                **asdict(row),
                "occurred_at": now.isoformat(),
                "cash_delta": str(cash),
                "quantity_delta": str(shares),
                "price": "0",
            }
        )
        confirmation = {
            **action,
            "cash": str(cash),
            "share_delta": str(shares),
            "confirmed_at": now.isoformat(),
            "evidence": str(payload["evidence"])[:1000],
        }
        instance = dict(instance)
        instance["corporate_action_confirmations"] = {
            **instance.get("corporate_action_confirmations", {}),
            key: confirmation,
        }
        recommendations = list(state.recommendations.get(instance_id, []))
        for advice in recommendations:
            if (
                advice.get("status") == "pending"
                and advice.get("instrument_id") == action["symbol"]
                and instant(advice["decision_at"]).astimezone(ZONE).date()
                < date.fromisoformat(action["ex_date"])
            ):
                advice.update(
                    status="rejected",
                    reason="公司行为后原建议失效，请重新分析",
                    version=int(advice.get("version", 0)) + 1,
                )
        state.recommendations[instance_id] = recommendations
        instance["state_revision"] = int(instance.get("state_revision", 0)) + 1
        state.instances[instance_id] = instance
        state.audit.append(
            audit_row(
                UuidGenerator(), now, owner_id, "confirm", "corporate_action", key, {}, confirmation
            )
        )
        return confirmation
