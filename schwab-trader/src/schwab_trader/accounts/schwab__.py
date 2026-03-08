# scripts/utils.py

import os
import asyncio
import logging
import schwabdev

# from gitmodules.Schwabdev import schwabdev
from typing import Any, Callable, Final, ParamSpec, TypeVar
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

app_key = os.getenv("APP_KEY")
app_secret = os.getenv("APP_SECRET")
callback_url = os.getenv("CALLBACK_URL")

if not all([app_key, app_secret, callback_url]):
    raise ValueError("Missing API credentials.")

client = schwabdev.Client(
    app_key,
    app_secret,
    callback_url,
)


# =========================
# Logging
# =========================

logger: Final[logging.Logger] = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


R = TypeVar("R")  # A placeholder for any type, more strick than typing.Any
P = ParamSpec(
    "P"
)  # to preserve the types of function signatures in higher-order functions.

# =========================
# Exceptions
# =========================


class SchwabClientError(Exception):
    pass


class AccountNotFoundError(SchwabClientError):
    pass


# =========================
# Pydantic Models
# =========================


class Position(BaseModel):
    quantity: float = Field(gt=0)
    average_price: float = Field(ge=0)
    # model_config = {"frozen": True}


class SingleAccountInfo(BaseModel):
    account_number: str
    account_hash_value: str
    account_details: dict[str, Any] | None


# =========================
# Async Client
# =========================


class AsyncSchwabAccountClient:
    """
    Async Schwab wrapper to fetch account info
    """

    def __init__(
        self,
        app_key: str | None = None,
        app_secret: str | None = None,
        callback_url: str | None = None,
        max_concurrent: int = 2,
        max_retries: int = 3,
    ) -> None:
        load_dotenv()

        self.app_key = app_key or os.getenv("APP_KEY")
        self.app_secret = app_secret or os.getenv("APP_SECRET")
        self.callback_url = callback_url or os.getenv("CALLBACK_URL")

        if not all([self.app_key, self.app_secret, self.callback_url]):
            raise SchwabClientError("Missing API credentials.")

        self.client = schwabdev.Client(
            self.app_key,
            self.app_secret,
            self.callback_url,
        )

        self._account_hash_value_cache: dict[str, str] = {}
        self.semaphore = asyncio.Semaphore(
            max_concurrent
        )  # limit how many coroutines can run a certain block of code at the same time.
        self.max_retries = max_retries

        logger.info("AsyncSchwabAccountClient initialized.")

    # =========================
    # Internal Async Wrapper
    # =========================

    async def _run_blocking(
        self, func: Callable[P, R], *args: P.args, **kwargs: P.kwargs
    ) -> R:
        """
        Run a blocking function in a thread pool safely in async code.

        Args:
            func (Callable[P, R]): Blocking function to run.
            *args (P.args): Positional arguments for func.
            **kwargs (P.kwargs): Keyword arguments for func.

        Returns:
            R: The return value of func.
        """
        return await asyncio.to_thread(func, *args, **kwargs)

    # =========================
    # Account Hash
    # =========================

    async def _get_account_hash_value(self, target_account: str) -> str:
        if target_account in self._account_hash_value_cache:
            return self._account_hash_value_cache[target_account]

        try:
            response = await self._run_blocking(self.client.linked_accounts)
            linked_accounts = response.json()
        except Exception as exc:
            raise SchwabClientError("Failed to fetch linked accounts.") from exc

        account_hash_value = next(
            (
                acct.get("hashValue")
                for acct in linked_accounts
                if acct.get("accountNumber") == target_account
            ),
            None,
        )

        if not account_hash_value:
            raise AccountNotFoundError(f"Account '{target_account}' not found.")

        self._account_hash_value_cache[target_account] = account_hash_value
        return account_hash_value

    # =========================
    # Account Info
    # =========================

    async def _get_single_account_details(
        self, account_number: str, account_hash_value: str
    ) -> SingleAccountInfo:
        """
        Fetch long positions and balances for a single account.
        """
        try:
            response = await self._run_blocking(
                self.client.account_details,
                account_hash_value,
                fields="positions",
            )
            account_details = response.json()
        except Exception as exc:
            raise SchwabClientError("Failed to fetch account details.") from exc

        result = SingleAccountInfo(
            account_number=account_number,
            account_hash_value=account_hash_value,
            account_details=account_details,
        )

        return result

    # =========================
    # Fetch a Single or Multiple Accounts Concurrently with Retries
    # =========================
    async def fetch_single_account(self, account_number: str) -> SingleAccountInfo:
        """
        Fetch info for a single account with retries.

        ACCOUNT_NUMBER = '29308909'

        Approach 1: with global client and data variables
        async def main():
            global client, data
            client_ = AsyncSchwabAccountClient()
            data = await client_.fetch_single_account(account_number=ACCOUNT_NUMBER)

        asyncio.run(main())
        data.model_dump().keys()
        # Return dict_keys(['account_number', 'account_hash_value', 'account_details'])

        Approach 2 - with direct access to result
        async def fetch_account_result(account_numbers: list[str]):
            client_ = AsyncSchwabAccountClient()
            return await client_.fetch_single_account(account_number=ACCOUNT_NUMBER)

        result = asyncio.run(
            fetch_account_result(ACCOUNT_NUMBER)
            )
        result.model_dump().keys()

        """
        for attempt in range(1, self.max_retries + 1):
            try:
                async with self.semaphore:
                    account_hash_value = await self._get_account_hash_value(
                        account_number
                    )
                    account_info = await self._get_single_account_details(
                        account_number, account_hash_value
                    )
                    return account_info
            except Exception as exc:
                logger.warning(
                    "Attempt %d failed for account %s: %s",
                    attempt,
                    account_number,
                    exc,
                )
                await asyncio.sleep(1 * attempt)

    async def fetch_multiple_accounts(
        self, account_numbers: list[str]
    ) -> dict[str, SingleAccountInfo]:
        """
        Fetch info for multiple accounts concurrently with retries.

        Example:
        ACCOUNT_NUMBERS = ['29308909', "123456"]

        #### Approach 1: with global client and data variables
        async def main():
            global results
            client_ = AsyncSchwabAccountClient()
            results = await client_.fetch_multiple_accounts(
                ACCOUNT_NUMBERS
            )

        asyncio.run(main())

        print(results.keys()) # dict_keys(['29308909', '123456'])

        #### Approach 2 - with direct access to result
        async def fetch_account_results(account_numbers: list[str]):
            client_ = AsyncSchwabAccountClient()
            return await client_.fetch_multiple_accounts(account_numbers)


        results = asyncio.run(
            fetch_account_results(ACCOUNT_NUMBERS)
            )
        print(results.keys()) # dict_keys(['29308909', '123456'])
        """

        tasks = {acct: self.fetch_single_account(acct) for acct in account_numbers}

        results = await asyncio.gather(*tasks.values(), return_exceptions=False)

        accounts_dict = {acct: result for acct, result in zip(tasks.keys(), results)}

        return accounts_dict


async def fetch_account_result(account_number: str) -> SingleAccountInfo:
    """
    Fetch info for a single account.

    Exaample:

    result, client = asyncio.run(fetch_account_result("29308909"))

    # Accessing account details for a specific account

    accountNumber = result.account_number
    hashValue = result.account_hash_value


    # Account current liquidation value.
    currentLiquidationValue = result.account_details["aggregatedBalance"][
        "currentLiquidationValue"
    ]

    currentBalances_dict = result.account_details["securitiesAccount"]["currentBalances"]
    cashBalance = currentBalances_dict.get("cashBalance", None)
    # e.g. 873.81
    availableFunds = currentBalances_dict.get("availableFunds", None)  # e.g.10741.58,
    availableFundsNonMarginableTrade = currentBalances_dict.get(
        "availableFundsNonMarginableTrade", None
    )  # e.g. 10741.58,
    buyingPower = currentBalances_dict.get("buyingPower", None)  # e.g. 35805.27,
    buyingPowerNonMarginableTrade = currentBalances_dict.get(
        "buyingPowerNonMarginableTrade", None
    )  # e.g. 10726.58,
    dayTradingBuyingPower = currentBalances_dict.get(
        "dayTradingBuyingPower", None
    )  # e.g. 0.0,


    """
    client_ = AsyncSchwabAccountClient()
    client = client_.client
    result = await client_.fetch_single_account(account_number)

    return result, client
