"""Finance tool plugin — financial profile and investment management tools.

Exports:
    get_tools()       → SDK Tool objects (side effect: register_tool() calls)
    get_schemas()     → snake_case name → JSON schema
    execute(name, args) → async dispatcher for non-agentic path
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional, Sequence

from pydantic import Field

from tools.sdk_compat import (
    Action,
    Observation,
    Tool,
    ToolDefinition,
    ToolExecutor,
    register_tool,
)


# =============================================================================
# Helpers (duplicated from agent/tools/base to avoid cross-dir imports)
# =============================================================================

def _run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


def _format_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, indent=2, default=str)


# =============================================================================
# SDK Tool Classes (migrated from agent/tools/finance_tools.py)
# =============================================================================

# --- finance_get_profile ---

class FinanceGetProfileAction(Action):
    pass


class FinanceGetProfileObservation(Observation):
    pass


class FinanceGetProfileExecutor(ToolExecutor[FinanceGetProfileAction, FinanceGetProfileObservation]):
    def __call__(self, action: FinanceGetProfileAction, conversation=None) -> FinanceGetProfileObservation:
        from finance import finance_get_profile
        result = _run_async(finance_get_profile())
        return FinanceGetProfileObservation.from_text(_format_result(result))


class FinanceGetProfileTool(ToolDefinition[FinanceGetProfileAction, FinanceGetProfileObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["FinanceGetProfileTool"]:
        return [cls(
            description=(
                "Get operator profile: age, employment (role, company, income, trajectory), "
                "secondary income, tax brackets. Use instead of GetFinancialContextTool for profile queries."
            ),
            action_type=FinanceGetProfileAction,
            observation_type=FinanceGetProfileObservation,
            executor=FinanceGetProfileExecutor(),
        )]


# --- finance_get_goals ---

class FinanceGetGoalsAction(Action):
    pass


class FinanceGetGoalsObservation(Observation):
    pass


class FinanceGetGoalsExecutor(ToolExecutor[FinanceGetGoalsAction, FinanceGetGoalsObservation]):
    def __call__(self, action: FinanceGetGoalsAction, conversation=None) -> FinanceGetGoalsObservation:
        from finance import finance_get_goals
        result = _run_async(finance_get_goals())
        return FinanceGetGoalsObservation.from_text(_format_result(result))


class FinanceGetGoalsTool(ToolDefinition[FinanceGetGoalsAction, FinanceGetGoalsObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["FinanceGetGoalsTool"]:
        return [cls(
            description=(
                "Get all financial goals grouped by time horizon: short_term (<1yr), "
                "medium_term (1-5yr), long_term (5yr+). Each goal has title, target_amount, "
                "current_amount, deadline, priority, category."
            ),
            action_type=FinanceGetGoalsAction,
            observation_type=FinanceGetGoalsObservation,
            executor=FinanceGetGoalsExecutor(),
        )]


# --- finance_get_risk_profile ---

class FinanceGetRiskProfileAction(Action):
    pass


class FinanceGetRiskProfileObservation(Observation):
    pass


class FinanceGetRiskProfileExecutor(ToolExecutor[FinanceGetRiskProfileAction, FinanceGetRiskProfileObservation]):
    def __call__(self, action: FinanceGetRiskProfileAction, conversation=None) -> FinanceGetRiskProfileObservation:
        from finance import finance_get_risk_profile
        result = _run_async(finance_get_risk_profile())
        return FinanceGetRiskProfileObservation.from_text(_format_result(result))


class FinanceGetRiskProfileTool(ToolDefinition[FinanceGetRiskProfileAction, FinanceGetRiskProfileObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["FinanceGetRiskProfileTool"]:
        return [cls(
            description=(
                "Get risk profile: tolerance (conservative/moderate/aggressive), time_horizon_years, "
                "investment_philosophy, max_drawdown_comfort_pct, notes."
            ),
            action_type=FinanceGetRiskProfileAction,
            observation_type=FinanceGetRiskProfileObservation,
            executor=FinanceGetRiskProfileExecutor(),
        )]


# --- finance_get_net_worth ---

class FinanceGetNetWorthAction(Action):
    pass


class FinanceGetNetWorthObservation(Observation):
    pass


class FinanceGetNetWorthExecutor(ToolExecutor[FinanceGetNetWorthAction, FinanceGetNetWorthObservation]):
    def __call__(self, action: FinanceGetNetWorthAction, conversation=None) -> FinanceGetNetWorthObservation:
        from finance import finance_get_net_worth
        result = _run_async(finance_get_net_worth())
        return FinanceGetNetWorthObservation.from_text(_format_result(result))


class FinanceGetNetWorthTool(ToolDefinition[FinanceGetNetWorthAction, FinanceGetNetWorthObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["FinanceGetNetWorthTool"]:
        return [cls(
            description=(
                "Get net worth snapshot: total_assets, total_liabilities, net_worth, as_of date."
            ),
            action_type=FinanceGetNetWorthAction,
            observation_type=FinanceGetNetWorthObservation,
            executor=FinanceGetNetWorthExecutor(),
        )]


# --- finance_get_accounts ---

class FinanceGetAccountsAction(Action):
    pass


class FinanceGetAccountsObservation(Observation):
    pass


class FinanceGetAccountsExecutor(ToolExecutor[FinanceGetAccountsAction, FinanceGetAccountsObservation]):
    def __call__(self, action: FinanceGetAccountsAction, conversation=None) -> FinanceGetAccountsObservation:
        from finance import finance_get_accounts
        result = _run_async(finance_get_accounts())
        return FinanceGetAccountsObservation.from_text(_format_result(result))


class FinanceGetAccountsTool(ToolDefinition[FinanceGetAccountsAction, FinanceGetAccountsObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["FinanceGetAccountsTool"]:
        return [cls(
            description=(
                "Get all accounts: chequing, savings, credit_cards (with utilization), "
                "lines_of_credit, loans. Use for debt/balance questions."
            ),
            action_type=FinanceGetAccountsAction,
            observation_type=FinanceGetAccountsObservation,
            executor=FinanceGetAccountsExecutor(),
        )]


# --- finance_get_investments ---

class FinanceGetInvestmentsAction(Action):
    pass


class FinanceGetInvestmentsObservation(Observation):
    pass


class FinanceGetInvestmentsExecutor(ToolExecutor[FinanceGetInvestmentsAction, FinanceGetInvestmentsObservation]):
    def __call__(self, action: FinanceGetInvestmentsAction, conversation=None) -> FinanceGetInvestmentsObservation:
        from finance import finance_get_investments
        result = _run_async(finance_get_investments())
        return FinanceGetInvestmentsObservation.from_text(_format_result(result))


class FinanceGetInvestmentsTool(ToolDefinition[FinanceGetInvestmentsAction, FinanceGetInvestmentsObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["FinanceGetInvestmentsTool"]:
        return [cls(
            description=(
                "Get investment accounts (RRSP, TFSA, non-reg) with holdings, target allocation, "
                "and global watchlist."
            ),
            action_type=FinanceGetInvestmentsAction,
            observation_type=FinanceGetInvestmentsObservation,
            executor=FinanceGetInvestmentsExecutor(),
        )]


# --- finance_get_cashflow ---

class FinanceGetCashflowAction(Action):
    pass


class FinanceGetCashflowObservation(Observation):
    pass


class FinanceGetCashflowExecutor(ToolExecutor[FinanceGetCashflowAction, FinanceGetCashflowObservation]):
    def __call__(self, action: FinanceGetCashflowAction, conversation=None) -> FinanceGetCashflowObservation:
        from finance import finance_get_cashflow
        result = _run_async(finance_get_cashflow())
        return FinanceGetCashflowObservation.from_text(_format_result(result))


class FinanceGetCashflowTool(ToolDefinition[FinanceGetCashflowAction, FinanceGetCashflowObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["FinanceGetCashflowTool"]:
        return [cls(
            description=(
                "Get monthly cashflow: income, fixed expenses, debt payments, savings/investments, "
                "variable budget, and computed totals (surplus, outflow)."
            ),
            action_type=FinanceGetCashflowAction,
            observation_type=FinanceGetCashflowObservation,
            executor=FinanceGetCashflowExecutor(),
        )]


# --- finance_get_tax ---

class FinanceGetTaxAction(Action):
    pass


class FinanceGetTaxObservation(Observation):
    pass


class FinanceGetTaxExecutor(ToolExecutor[FinanceGetTaxAction, FinanceGetTaxObservation]):
    def __call__(self, action: FinanceGetTaxAction, conversation=None) -> FinanceGetTaxObservation:
        from finance import finance_get_tax
        result = _run_async(finance_get_tax())
        return FinanceGetTaxObservation.from_text(_format_result(result))


class FinanceGetTaxTool(ToolDefinition[FinanceGetTaxAction, FinanceGetTaxObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["FinanceGetTaxTool"]:
        return [cls(
            description=(
                "Get tax situation: federal/provincial brackets, RRSP room and YTD contributions, "
                "TFSA room and used amount, filing status, capital gains."
            ),
            action_type=FinanceGetTaxAction,
            observation_type=FinanceGetTaxObservation,
            executor=FinanceGetTaxExecutor(),
        )]


# --- finance_get_insurance ---

class FinanceGetInsuranceAction(Action):
    pass


class FinanceGetInsuranceObservation(Observation):
    pass


class FinanceGetInsuranceExecutor(ToolExecutor[FinanceGetInsuranceAction, FinanceGetInsuranceObservation]):
    def __call__(self, action: FinanceGetInsuranceAction, conversation=None) -> FinanceGetInsuranceObservation:
        from finance import finance_get_insurance
        result = _run_async(finance_get_insurance())
        return FinanceGetInsuranceObservation.from_text(_format_result(result))


class FinanceGetInsuranceTool(ToolDefinition[FinanceGetInsuranceAction, FinanceGetInsuranceObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["FinanceGetInsuranceTool"]:
        return [cls(
            description=(
                "Get all insurance policies: type, provider, coverage amount, premium, "
                "deductible, renewal date, beneficiaries."
            ),
            action_type=FinanceGetInsuranceAction,
            observation_type=FinanceGetInsuranceObservation,
            executor=FinanceGetInsuranceExecutor(),
        )]


# --- finance_get_agent_context ---

class FinanceGetAgentContextAction(Action):
    pass


class FinanceGetAgentContextObservation(Observation):
    pass


class FinanceGetAgentContextExecutor(ToolExecutor[FinanceGetAgentContextAction, FinanceGetAgentContextObservation]):
    def __call__(self, action: FinanceGetAgentContextAction, conversation=None) -> FinanceGetAgentContextObservation:
        from finance import finance_get_agent_context
        result = _run_async(finance_get_agent_context())
        return FinanceGetAgentContextObservation.from_text(_format_result(result))


class FinanceGetAgentContextTool(ToolDefinition[FinanceGetAgentContextAction, FinanceGetAgentContextObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["FinanceGetAgentContextTool"]:
        return [cls(
            description=(
                "Get agent context about this operator's financial behaviour: known biases, "
                "recurring questions, and advisory notes."
            ),
            action_type=FinanceGetAgentContextAction,
            observation_type=FinanceGetAgentContextObservation,
            executor=FinanceGetAgentContextExecutor(),
        )]


# --- finance_update_profile ---

class FinanceUpdateProfileAction(Action):
    updates: Dict[str, Any] = Field(
        description="Profile fields to update. Supports: age, net_monthly_income, "
                    "tax_bracket_federal, tax_bracket_provincial, "
                    "employment (dict with role/company/tenure_years/gross_annual_income/trajectory/near_term_change_risk), "
                    "secondary_income (list)."
    )


class FinanceUpdateProfileObservation(Observation):
    pass


class FinanceUpdateProfileExecutor(ToolExecutor[FinanceUpdateProfileAction, FinanceUpdateProfileObservation]):
    def __call__(self, action: FinanceUpdateProfileAction, conversation=None) -> FinanceUpdateProfileObservation:
        from finance import finance_update_profile
        result = _run_async(finance_update_profile(action.updates))
        return FinanceUpdateProfileObservation.from_text(_format_result(result))


class FinanceUpdateProfileTool(ToolDefinition[FinanceUpdateProfileAction, FinanceUpdateProfileObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["FinanceUpdateProfileTool"]:
        return [cls(
            description="Update operator profile fields: age, income, employment details, tax brackets.",
            action_type=FinanceUpdateProfileAction,
            observation_type=FinanceUpdateProfileObservation,
            executor=FinanceUpdateProfileExecutor(),
        )]


# --- finance_update_goals ---

class FinanceUpdateGoalsAction(Action):
    short_term: Optional[List[Dict[str, Any]]] = Field(default=None, description="Replace short-term goals array (<1yr)")
    medium_term: Optional[List[Dict[str, Any]]] = Field(default=None, description="Replace medium-term goals array (1-5yr)")
    long_term: Optional[List[Dict[str, Any]]] = Field(default=None, description="Replace long-term goals array (5yr+)")


class FinanceUpdateGoalsObservation(Observation):
    pass


class FinanceUpdateGoalsExecutor(ToolExecutor[FinanceUpdateGoalsAction, FinanceUpdateGoalsObservation]):
    def __call__(self, action: FinanceUpdateGoalsAction, conversation=None) -> FinanceUpdateGoalsObservation:
        from finance import finance_update_goals
        result = _run_async(finance_update_goals(action.short_term, action.medium_term, action.long_term))
        return FinanceUpdateGoalsObservation.from_text(_format_result(result))


class FinanceUpdateGoalsTool(ToolDefinition[FinanceUpdateGoalsAction, FinanceUpdateGoalsObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["FinanceUpdateGoalsTool"]:
        return [cls(
            description=(
                "Create, update, or delete financial goals. Fetch current goals first, "
                "modify the relevant array, then submit. Each goal: {id, title, description, "
                "target_amount, current_amount, deadline, priority, category, notes}."
            ),
            action_type=FinanceUpdateGoalsAction,
            observation_type=FinanceUpdateGoalsObservation,
            executor=FinanceUpdateGoalsExecutor(),
        )]


# --- finance_update_risk_profile ---

class FinanceUpdateRiskProfileAction(Action):
    updates: Dict[str, Any] = Field(
        description="Risk profile fields: tolerance (conservative/moderate/aggressive), "
                    "time_horizon_years, investment_philosophy, max_drawdown_comfort_pct, notes."
    )


class FinanceUpdateRiskProfileObservation(Observation):
    pass


class FinanceUpdateRiskProfileExecutor(ToolExecutor[FinanceUpdateRiskProfileAction, FinanceUpdateRiskProfileObservation]):
    def __call__(self, action: FinanceUpdateRiskProfileAction, conversation=None) -> FinanceUpdateRiskProfileObservation:
        from finance import finance_update_risk_profile
        result = _run_async(finance_update_risk_profile(action.updates))
        return FinanceUpdateRiskProfileObservation.from_text(_format_result(result))


class FinanceUpdateRiskProfileTool(ToolDefinition[FinanceUpdateRiskProfileAction, FinanceUpdateRiskProfileObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["FinanceUpdateRiskProfileTool"]:
        return [cls(
            description="Update risk profile: tolerance, time horizon, investment philosophy, max drawdown comfort.",
            action_type=FinanceUpdateRiskProfileAction,
            observation_type=FinanceUpdateRiskProfileObservation,
            executor=FinanceUpdateRiskProfileExecutor(),
        )]


# --- finance_update_net_worth ---

class FinanceUpdateNetWorthAction(Action):
    total_assets: Optional[float] = Field(default=None, description="Total assets in dollars")
    total_liabilities: Optional[float] = Field(default=None, description="Total liabilities in dollars")
    as_of: Optional[str] = Field(default=None, description="Snapshot date (YYYY-MM-DD)")


class FinanceUpdateNetWorthObservation(Observation):
    pass


class FinanceUpdateNetWorthExecutor(ToolExecutor[FinanceUpdateNetWorthAction, FinanceUpdateNetWorthObservation]):
    def __call__(self, action: FinanceUpdateNetWorthAction, conversation=None) -> FinanceUpdateNetWorthObservation:
        from finance import finance_update_net_worth
        result = _run_async(finance_update_net_worth(action.total_assets, action.total_liabilities, action.as_of))
        return FinanceUpdateNetWorthObservation.from_text(_format_result(result))


class FinanceUpdateNetWorthTool(ToolDefinition[FinanceUpdateNetWorthAction, FinanceUpdateNetWorthObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["FinanceUpdateNetWorthTool"]:
        return [cls(
            description="Update net worth snapshot. Net worth is auto-computed as assets - liabilities.",
            action_type=FinanceUpdateNetWorthAction,
            observation_type=FinanceUpdateNetWorthObservation,
            executor=FinanceUpdateNetWorthExecutor(),
        )]


# --- finance_update_account ---

class FinanceUpdateAccountAction(Action):
    account_type: str = Field(description="Account type: chequing, savings, credit_cards, lines_of_credit, loans")
    account_id: str = Field(description="Account id field value")
    updates: Dict[str, Any] = Field(description="Fields to update on the account")


class FinanceUpdateAccountObservation(Observation):
    pass


class FinanceUpdateAccountExecutor(ToolExecutor[FinanceUpdateAccountAction, FinanceUpdateAccountObservation]):
    def __call__(self, action: FinanceUpdateAccountAction, conversation=None) -> FinanceUpdateAccountObservation:
        from finance import finance_update_account
        result = _run_async(finance_update_account(action.account_type, action.account_id, action.updates))
        return FinanceUpdateAccountObservation.from_text(_format_result(result))


class FinanceUpdateAccountTool(ToolDefinition[FinanceUpdateAccountAction, FinanceUpdateAccountObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["FinanceUpdateAccountTool"]:
        return [cls(
            description=(
                "Patch a specific account by type and id. Fetch accounts first to get ids. "
                "Credit card utilization is auto-recomputed. "
                "Types: chequing, savings, credit_cards, lines_of_credit, loans."
            ),
            action_type=FinanceUpdateAccountAction,
            observation_type=FinanceUpdateAccountObservation,
            executor=FinanceUpdateAccountExecutor(),
        )]


# --- finance_add_holding ---

class FinanceAddHoldingAction(Action):
    account_id: str = Field(description="Investment account id")
    ticker: str = Field(description="Ticker symbol (e.g. AAPL, VFV.TO)")
    shares: float = Field(description="Number of shares held")
    avg_cost: float = Field(description="Average cost per share")
    current_price: Optional[float] = Field(default=None, description="Current market price per share")
    notes: str = Field(default="", description="Optional notes")


class FinanceAddHoldingObservation(Observation):
    pass


class FinanceAddHoldingExecutor(ToolExecutor[FinanceAddHoldingAction, FinanceAddHoldingObservation]):
    def __call__(self, action: FinanceAddHoldingAction, conversation=None) -> FinanceAddHoldingObservation:
        from finance import finance_add_holding
        result = _run_async(finance_add_holding(
            action.account_id, action.ticker, action.shares,
            action.avg_cost, action.current_price, action.notes
        ))
        return FinanceAddHoldingObservation.from_text(_format_result(result))


class FinanceAddHoldingTool(ToolDefinition[FinanceAddHoldingAction, FinanceAddHoldingObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["FinanceAddHoldingTool"]:
        return [cls(
            description="Add a new investment holding to an account. Fails if ticker already exists — use finance_update_holding instead.",
            action_type=FinanceAddHoldingAction,
            observation_type=FinanceAddHoldingObservation,
            executor=FinanceAddHoldingExecutor(),
        )]


# --- finance_update_holding ---

class FinanceUpdateHoldingAction(Action):
    account_id: str = Field(description="Investment account id")
    ticker: str = Field(description="Ticker symbol to update")
    updates: Dict[str, Any] = Field(description="Fields: shares, avg_cost, current_price, notes")


class FinanceUpdateHoldingObservation(Observation):
    pass


class FinanceUpdateHoldingExecutor(ToolExecutor[FinanceUpdateHoldingAction, FinanceUpdateHoldingObservation]):
    def __call__(self, action: FinanceUpdateHoldingAction, conversation=None) -> FinanceUpdateHoldingObservation:
        from finance import finance_update_holding
        result = _run_async(finance_update_holding(action.account_id, action.ticker, action.updates))
        return FinanceUpdateHoldingObservation.from_text(_format_result(result))


class FinanceUpdateHoldingTool(ToolDefinition[FinanceUpdateHoldingAction, FinanceUpdateHoldingObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["FinanceUpdateHoldingTool"]:
        return [cls(
            description="Update an existing holding: shares, avg_cost, current_price, notes. last_price_update is set automatically when current_price changes.",
            action_type=FinanceUpdateHoldingAction,
            observation_type=FinanceUpdateHoldingObservation,
            executor=FinanceUpdateHoldingExecutor(),
        )]


# --- finance_update_watchlist ---

class FinanceUpdateWatchlistAction(Action):
    watchlist: List[Dict[str, Any]] = Field(description="New watchlist array. Each item: {ticker, notes}")


class FinanceUpdateWatchlistObservation(Observation):
    pass


class FinanceUpdateWatchlistExecutor(ToolExecutor[FinanceUpdateWatchlistAction, FinanceUpdateWatchlistObservation]):
    def __call__(self, action: FinanceUpdateWatchlistAction, conversation=None) -> FinanceUpdateWatchlistObservation:
        from finance import finance_update_watchlist
        result = _run_async(finance_update_watchlist(action.watchlist))
        return FinanceUpdateWatchlistObservation.from_text(_format_result(result))


class FinanceUpdateWatchlistTool(ToolDefinition[FinanceUpdateWatchlistAction, FinanceUpdateWatchlistObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["FinanceUpdateWatchlistTool"]:
        return [cls(
            description="Replace the global investment watchlist. Fetch current first, add/remove tickers, submit full list.",
            action_type=FinanceUpdateWatchlistAction,
            observation_type=FinanceUpdateWatchlistObservation,
            executor=FinanceUpdateWatchlistExecutor(),
        )]


# --- finance_update_cashflow ---

class FinanceUpdateCashflowAction(Action):
    updates: Dict[str, Any] = Field(
        description="Cashflow sections to update. Keys: net_monthly_income (number), "
                    "fixed_expenses (array), debt_payments (array), "
                    "savings_and_investments (array), variable_expense_budget (array). "
                    "Omit sections you don't want to change. Totals are recomputed automatically."
    )


class FinanceUpdateCashflowObservation(Observation):
    pass


class FinanceUpdateCashflowExecutor(ToolExecutor[FinanceUpdateCashflowAction, FinanceUpdateCashflowObservation]):
    def __call__(self, action: FinanceUpdateCashflowAction, conversation=None) -> FinanceUpdateCashflowObservation:
        from finance import finance_update_cashflow
        result = _run_async(finance_update_cashflow(action.updates))
        return FinanceUpdateCashflowObservation.from_text(_format_result(result))


class FinanceUpdateCashflowTool(ToolDefinition[FinanceUpdateCashflowAction, FinanceUpdateCashflowObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["FinanceUpdateCashflowTool"]:
        return [cls(
            description=(
                "Update monthly cashflow sections. Surplus and totals are recomputed automatically. "
                "Fetch current cashflow first, modify the relevant sections, submit only changed keys."
            ),
            action_type=FinanceUpdateCashflowAction,
            observation_type=FinanceUpdateCashflowObservation,
            executor=FinanceUpdateCashflowExecutor(),
        )]


# --- finance_update_tax ---

class FinanceUpdateTaxAction(Action):
    updates: Dict[str, Any] = Field(
        description="Tax fields to update: rrsp_room, rrsp_ytd_contributions, "
                    "tfsa_room, tfsa_used_this_year, filing_status, "
                    "capital_gains_ytd, tax_refund_owing, or others."
    )


class FinanceUpdateTaxObservation(Observation):
    pass


class FinanceUpdateTaxExecutor(ToolExecutor[FinanceUpdateTaxAction, FinanceUpdateTaxObservation]):
    def __call__(self, action: FinanceUpdateTaxAction, conversation=None) -> FinanceUpdateTaxObservation:
        from finance import finance_update_tax
        result = _run_async(finance_update_tax(action.updates))
        return FinanceUpdateTaxObservation.from_text(_format_result(result))


class FinanceUpdateTaxTool(ToolDefinition[FinanceUpdateTaxAction, FinanceUpdateTaxObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["FinanceUpdateTaxTool"]:
        return [cls(
            description="Update tax situation: RRSP room/contributions, TFSA room, filing status, capital gains.",
            action_type=FinanceUpdateTaxAction,
            observation_type=FinanceUpdateTaxObservation,
            executor=FinanceUpdateTaxExecutor(),
        )]


# --- finance_update_insurance ---

class FinanceUpdateInsuranceAction(Action):
    policies: List[Dict[str, Any]] = Field(
        description="Full insurance policies list. Each policy: "
                    "{type, provider, coverage_amount, premium, deductible, renewal_date, beneficiaries, notes}."
    )


class FinanceUpdateInsuranceObservation(Observation):
    pass


class FinanceUpdateInsuranceExecutor(ToolExecutor[FinanceUpdateInsuranceAction, FinanceUpdateInsuranceObservation]):
    def __call__(self, action: FinanceUpdateInsuranceAction, conversation=None) -> FinanceUpdateInsuranceObservation:
        from finance import finance_update_insurance
        result = _run_async(finance_update_insurance(action.policies))
        return FinanceUpdateInsuranceObservation.from_text(_format_result(result))


class FinanceUpdateInsuranceTool(ToolDefinition[FinanceUpdateInsuranceAction, FinanceUpdateInsuranceObservation]):
    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["FinanceUpdateInsuranceTool"]:
        return [cls(
            description="Replace insurance policies list. Fetch current first, add/modify/remove entries, submit full list.",
            action_type=FinanceUpdateInsuranceAction,
            observation_type=FinanceUpdateInsuranceObservation,
            executor=FinanceUpdateInsuranceExecutor(),
        )]


# =============================================================================
# Register all SDK tools
# =============================================================================

# Reads
register_tool("FinanceGetProfileTool", FinanceGetProfileTool)
register_tool("FinanceGetGoalsTool", FinanceGetGoalsTool)
register_tool("FinanceGetRiskProfileTool", FinanceGetRiskProfileTool)
register_tool("FinanceGetNetWorthTool", FinanceGetNetWorthTool)
register_tool("FinanceGetAccountsTool", FinanceGetAccountsTool)
register_tool("FinanceGetInvestmentsTool", FinanceGetInvestmentsTool)
register_tool("FinanceGetCashflowTool", FinanceGetCashflowTool)
register_tool("FinanceGetTaxTool", FinanceGetTaxTool)
register_tool("FinanceGetInsuranceTool", FinanceGetInsuranceTool)
register_tool("FinanceGetAgentContextTool", FinanceGetAgentContextTool)

# Writes
register_tool("FinanceUpdateProfileTool", FinanceUpdateProfileTool)
register_tool("FinanceUpdateGoalsTool", FinanceUpdateGoalsTool)
register_tool("FinanceUpdateRiskProfileTool", FinanceUpdateRiskProfileTool)
register_tool("FinanceUpdateNetWorthTool", FinanceUpdateNetWorthTool)
register_tool("FinanceUpdateAccountTool", FinanceUpdateAccountTool)
register_tool("FinanceAddHoldingTool", FinanceAddHoldingTool)
register_tool("FinanceUpdateHoldingTool", FinanceUpdateHoldingTool)
register_tool("FinanceUpdateWatchlistTool", FinanceUpdateWatchlistTool)
register_tool("FinanceUpdateCashflowTool", FinanceUpdateCashflowTool)
register_tool("FinanceUpdateTaxTool", FinanceUpdateTaxTool)
register_tool("FinanceUpdateInsuranceTool", FinanceUpdateInsuranceTool)


# =============================================================================
# Plugin contract: get_tools()
# =============================================================================

def get_tools() -> List[Tool]:
    """Get all finance SDK Tool objects (side effect: register_tool already called above)."""
    return [
        # Reads
        Tool(name="FinanceGetProfileTool"),
        Tool(name="FinanceGetGoalsTool"),
        Tool(name="FinanceGetRiskProfileTool"),
        Tool(name="FinanceGetNetWorthTool"),
        Tool(name="FinanceGetAccountsTool"),
        Tool(name="FinanceGetInvestmentsTool"),
        Tool(name="FinanceGetCashflowTool"),
        Tool(name="FinanceGetTaxTool"),
        Tool(name="FinanceGetInsuranceTool"),
        Tool(name="FinanceGetAgentContextTool"),
        # Writes
        Tool(name="FinanceUpdateProfileTool"),
        Tool(name="FinanceUpdateGoalsTool"),
        Tool(name="FinanceUpdateRiskProfileTool"),
        Tool(name="FinanceUpdateNetWorthTool"),
        Tool(name="FinanceUpdateAccountTool"),
        Tool(name="FinanceAddHoldingTool"),
        Tool(name="FinanceUpdateHoldingTool"),
        Tool(name="FinanceUpdateWatchlistTool"),
        Tool(name="FinanceUpdateCashflowTool"),
        Tool(name="FinanceUpdateTaxTool"),
        Tool(name="FinanceUpdateInsuranceTool"),
    ]


# =============================================================================
# Plugin contract: get_schemas() — JSON schemas for non-agentic specialist path
# =============================================================================

def get_schemas() -> Dict[str, Dict[str, Any]]:
    """Return snake_case tool name -> JSON schema mapping."""
    return {
        "finance_get_profile": {
            "name": "finance_get_profile",
            "description": "Get the full financial profile.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        "finance_get_goals": {
            "name": "finance_get_goals",
            "description": "Get financial goals (short, medium, long-term).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        "finance_get_accounts": {
            "name": "finance_get_accounts",
            "description": "Get all financial accounts.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        "finance_get_investments": {
            "name": "finance_get_investments",
            "description": "Get investment holdings across all accounts.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        "finance_get_cashflow": {
            "name": "finance_get_cashflow",
            "description": "Get cashflow breakdown (income, expenses, savings).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        "finance_get_tax": {
            "name": "finance_get_tax",
            "description": "Get tax information (RRSP, TFSA room, capital gains).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        "finance_get_insurance": {
            "name": "finance_get_insurance",
            "description": "Get insurance policies.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        "finance_get_net_worth": {
            "name": "finance_get_net_worth",
            "description": "Get net worth snapshot.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        "finance_update_profile": {
            "name": "finance_update_profile",
            "description": "Update financial profile fields (age, income, employment, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "updates": {
                        "type": "object",
                        "description": "Profile fields to update.",
                    },
                },
                "required": ["updates"],
            },
        },
        "finance_update_goals": {
            "name": "finance_update_goals",
            "description": "Replace financial goals.",
            "parameters": {
                "type": "object",
                "properties": {
                    "short_term": {"type": "array", "items": {"type": "object"}, "description": "Short-term goals (<1yr)"},
                    "medium_term": {"type": "array", "items": {"type": "object"}, "description": "Medium-term goals (1-5yr)"},
                    "long_term": {"type": "array", "items": {"type": "object"}, "description": "Long-term goals (5yr+)"},
                },
                "required": [],
            },
        },
        "finance_update_risk_profile": {
            "name": "finance_update_risk_profile",
            "description": "Update risk profile (tolerance, time horizon, philosophy).",
            "parameters": {
                "type": "object",
                "properties": {
                    "updates": {"type": "object", "description": "Risk profile fields to update"},
                },
                "required": ["updates"],
            },
        },
        "finance_update_net_worth": {
            "name": "finance_update_net_worth",
            "description": "Update net worth snapshot.",
            "parameters": {
                "type": "object",
                "properties": {
                    "total_assets": {"type": "number", "description": "Total assets in dollars"},
                    "total_liabilities": {"type": "number", "description": "Total liabilities in dollars"},
                    "as_of": {"type": "string", "description": "Snapshot date (YYYY-MM-DD)"},
                },
                "required": [],
            },
        },
        "finance_update_account": {
            "name": "finance_update_account",
            "description": "Update fields on a financial account.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account_type": {"type": "string", "description": "Account type: chequing, savings, credit_cards, etc."},
                    "account_id": {"type": "string", "description": "Account id field value"},
                    "updates": {"type": "object", "description": "Fields to update"},
                },
                "required": ["account_type", "account_id", "updates"],
            },
        },
        "finance_add_holding": {
            "name": "finance_add_holding",
            "description": "Add an investment holding to an account.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account_id": {"type": "string", "description": "Investment account id"},
                    "ticker": {"type": "string", "description": "Ticker symbol"},
                    "shares": {"type": "number", "description": "Number of shares"},
                    "avg_cost": {"type": "number", "description": "Average cost per share"},
                    "current_price": {"type": "number", "description": "Current market price per share"},
                    "notes": {"type": "string", "description": "Optional notes", "default": ""},
                },
                "required": ["account_id", "ticker", "shares", "avg_cost"],
            },
        },
        "finance_update_holding": {
            "name": "finance_update_holding",
            "description": "Update an investment holding.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account_id": {"type": "string", "description": "Investment account id"},
                    "ticker": {"type": "string", "description": "Ticker symbol to update"},
                    "updates": {"type": "object", "description": "Fields: shares, avg_cost, current_price, notes"},
                },
                "required": ["account_id", "ticker", "updates"],
            },
        },
        "finance_update_watchlist": {
            "name": "finance_update_watchlist",
            "description": "Replace the full watchlist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "watchlist": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "New watchlist array. Each item: {ticker, notes}",
                    },
                },
                "required": ["watchlist"],
            },
        },
        "finance_update_cashflow": {
            "name": "finance_update_cashflow",
            "description": "Update cashflow sections.",
            "parameters": {
                "type": "object",
                "properties": {
                    "updates": {"type": "object", "description": "Cashflow sections to update"},
                },
                "required": ["updates"],
            },
        },
        "finance_update_tax": {
            "name": "finance_update_tax",
            "description": "Update tax fields.",
            "parameters": {
                "type": "object",
                "properties": {
                    "updates": {"type": "object", "description": "Tax fields to update"},
                },
                "required": ["updates"],
            },
        },
        "finance_update_insurance": {
            "name": "finance_update_insurance",
            "description": "Replace the full insurance policies list.",
            "parameters": {
                "type": "object",
                "properties": {
                    "policies": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Full insurance policies list",
                    },
                },
                "required": ["policies"],
            },
        },
    }


# =============================================================================
# Plugin contract: execute() — async dispatcher for non-agentic specialist path
# =============================================================================

async def execute(name: str, args: Dict[str, Any]) -> str:
    """Route finance tool calls to the underlying finance module functions."""
    from finance import (
        finance_get_profile,
        finance_get_goals,
        finance_get_accounts,
        finance_get_investments,
        finance_get_cashflow,
        finance_get_tax,
        finance_get_insurance,
        finance_get_net_worth,
        finance_update_profile,
        finance_update_goals,
        finance_update_risk_profile,
        finance_update_net_worth,
        finance_update_account,
        finance_add_holding,
        finance_update_holding,
        finance_update_watchlist,
        finance_update_cashflow,
        finance_update_tax,
        finance_update_insurance,
    )

    FINANCE_ROUTES = {
        "finance_get_profile": lambda: finance_get_profile(),
        "finance_get_goals": lambda: finance_get_goals(),
        "finance_get_accounts": lambda: finance_get_accounts(),
        "finance_get_investments": lambda: finance_get_investments(),
        "finance_get_cashflow": lambda: finance_get_cashflow(),
        "finance_get_tax": lambda: finance_get_tax(),
        "finance_get_insurance": lambda: finance_get_insurance(),
        "finance_get_net_worth": lambda: finance_get_net_worth(),
        "finance_update_profile": lambda: finance_update_profile(args["updates"]),
        "finance_update_goals": lambda: finance_update_goals(
            args.get("short_term"), args.get("medium_term"), args.get("long_term")
        ),
        "finance_update_risk_profile": lambda: finance_update_risk_profile(args["updates"]),
        "finance_update_net_worth": lambda: finance_update_net_worth(
            args.get("total_assets"), args.get("total_liabilities"), args.get("as_of")
        ),
        "finance_update_account": lambda: finance_update_account(
            args["account_type"], args["account_id"], args["updates"]
        ),
        "finance_add_holding": lambda: finance_add_holding(
            args["account_id"], args["ticker"], args["shares"], args["avg_cost"],
            args.get("current_price"), args.get("notes", ""),
        ),
        "finance_update_holding": lambda: finance_update_holding(
            args["account_id"], args["ticker"], args["updates"]
        ),
        "finance_update_watchlist": lambda: finance_update_watchlist(args["watchlist"]),
        "finance_update_cashflow": lambda: finance_update_cashflow(args["updates"]),
        "finance_update_tax": lambda: finance_update_tax(args["updates"]),
        "finance_update_insurance": lambda: finance_update_insurance(args["policies"]),
    }

    handler = FINANCE_ROUTES.get(name)
    if not handler:
        return f"Unknown finance tool: {name}"

    result = handler()
    if isinstance(result, str):
        return result
    return json.dumps(result, indent=2, default=str)
