"""公司行为权益状态机；只处理现金/股数事实，不把复权价用于成交。"""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from easy_quant.domain.backtesting.entities import Portfolio
from easy_quant.domain.market_data.corporate_actions import CorporateAction
from easy_quant.domain.shared.errors import StateConflictError


@dataclass
class Entitlement:
    action: CorporateAction
    quantity: Decimal
    cash: Decimal
    shares: Decimal
    recognized: bool = False
    paid: bool = False
    listed: bool = False
    locked: Decimal = Decimal(0)


class CorporateActionLedger:
    def __init__(self) -> None:
        self.entitlements: dict[str, Entitlement] = {}
        self.audit: list[dict[str, str]] = []
        self.applied: set[str] = set()

    def close(self, day: date, portfolio: Portfolio, events: tuple[CorporateAction, ...]) -> None:
        visible_ids = {action.event_id for action in events}
        if any(key not in visible_ids for key in self.entitlements):
            raise StateConflictError("已登记公司行为被取消或缺少可见版本，回测已中止")
        for action in events:
            prior = self.entitlements.get(action.event_id)
            if prior is not None and prior.action.record_key != action.record_key:
                raise StateConflictError("权益登记后公司行为发生修订，回测已中止待复核")
            if action.record_date != day or action.event_id in self.entitlements:
                continue
            quantity = portfolio.position(action.symbol)
            if quantity == 0:
                continue
            if action.rights_ratio:
                raise StateConflictError(
                    "持仓配股需要明确认购、缴款和权益处置，回测已中止",
                    {"event_id": action.event_id},
                )
            shares = quantity * (action.share_multiplier - 1)
            if shares != shares.to_integral_value():
                raise StateConflictError(
                    "送转/拆合股产生碎股，缺少明确处置规则", {"event_id": action.event_id}
                )
            cash = (quantity * action.cash_per_share).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            self.entitlements[action.event_id] = Entitlement(action, quantity, cash, shares)
            self.audit.append(
                {
                    "event_id": action.event_id,
                    "record_key": action.record_key,
                    "stage": "record",
                    "day": str(day),
                    "quantity": str(quantity),
                }
            )

    def open(
        self,
        day: date,
        portfolio: Portfolio,
        events: tuple[CorporateAction, ...],
        marks: dict[str, Decimal],
    ) -> None:
        for action in events:
            if action.ex_date <= day and action.event_id not in self.applied:
                if (
                    action.ex_date == day
                    and portfolio.position(action.symbol)
                    and action.event_id not in self.entitlements
                ):
                    raise StateConflictError("持仓跨越除权但缺少登记日权益快照，回测已中止")
                # 估值基准随除权变换，即使当天停牌也不会丢失或虚增资产。
                if action.symbol in marks:
                    marks[action.symbol] *= action.price_ratio
                self.applied.add(action.event_id)
        for entitlement in self.entitlements.values():
            action = entitlement.action
            if day >= action.ex_date and not entitlement.recognized:
                entitlement.recognized = True
                previous_quantity = portfolio.position(action.symbol)
                total_cost = portfolio.costs.get(action.symbol, Decimal(0)) * previous_quantity
                if entitlement.shares < 0:
                    # 合股减少股份必须即时作用于总持仓，不能出现负的待上市股份。
                    current = portfolio.position(action.symbol)
                    if current < -entitlement.shares:
                        raise StateConflictError("登记日到合股间持仓不足，需核对事件规则")
                    portfolio.positions[action.symbol] = current + entitlement.shares
                elif entitlement.shares:
                    portfolio.positions[action.symbol] = (
                        portfolio.position(action.symbol) + entitlement.shares
                    )
                if entitlement.shares:
                    current = portfolio.position(action.symbol)
                    portfolio.costs[action.symbol] = total_cost / current if current else Decimal(0)
                    entitlement.locked = (
                        current
                        if set(action.kinds) & {"split", "consolidation"}
                        else max(entitlement.shares, Decimal(0))
                    )
                    portfolio.locked_shares[action.symbol] = (
                        portfolio.locked_shares.get(action.symbol, Decimal(0)) + entitlement.locked
                    )
                portfolio.receivable_cash += entitlement.cash
                self.audit.append(
                    {
                        "event_id": action.event_id,
                        "record_key": action.record_key,
                        "symbol": action.symbol,
                        "stage": "ex",
                        "day": str(day),
                        "cash": str(entitlement.cash),
                        "shares": str(entitlement.shares),
                    }
                )
            if not entitlement.recognized:
                continue
            if not entitlement.paid and action.cash_pay_date and day >= action.cash_pay_date:
                portfolio.receivable_cash -= entitlement.cash
                portfolio.cash += entitlement.cash
                entitlement.paid = True
                self.audit.append(
                    {
                        "event_id": action.event_id,
                        "stage": "cash_paid",
                        "day": str(day),
                        "cash": str(entitlement.cash),
                    }
                )
            if (
                not entitlement.listed
                and action.shares_listing_date
                and day >= action.shares_listing_date
            ):
                portfolio.locked_shares[action.symbol] = (
                    portfolio.locked_shares.get(action.symbol, Decimal(0)) - entitlement.locked
                )
                entitlement.listed = True
                self.audit.append(
                    {
                        "event_id": action.event_id,
                        "stage": "shares_listed",
                        "day": str(day),
                        "shares": str(entitlement.shares),
                    }
                )
