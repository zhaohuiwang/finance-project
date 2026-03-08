import os
import schwabdev
from datetime import datetime, time as dt_time, timezone
from dotenv import load_dotenv

load_dotenv()

client = schwabdev.Client(
    os.getenv("APP_KEY"), os.getenv("APP_SECRET"), os.getenv("CALLBACK_URL")
)


def get_account_hash(target_account: str) -> str | None:
    """
    Retrieve the API-specific account hash for a given account number.

    This function queries the brokerage API for all linked accounts and
    searches for the account whose ``accountNumber`` matches the provided
    ``target_account``. If found, the corresponding ``hashValue`` is returned.

    Args:
        target_account (str):
            The human-readable account number to search for among
            linked brokerage accounts.

    Returns:
        str | None:
            The account hash (``hashValue``) associated with the matching
            account number, or ``None`` if no matching account is found.

    Raises:
        requests.HTTPError:
            If the underlying API request fails.
        KeyError:
            If expected keys (e.g., 'accountNumber', 'hashValue')
            are missing from the API response.

    Notes:
        - The returned account hash is typically required for subsequent
          account-specific API calls (e.g., retrieving balances or positions).
        - If multiple accounts share the same account number (unexpected),
          the first match is returned.
    """

    linked_accounts = client.linked_accounts().json()

    account_hash: str | None = next(
        (
            acct["hashValue"]
            for acct in linked_accounts
            if acct["accountNumber"] == target_account
        ),
        None,
    )

    return account_hash


def get_single_account_positions(
    account_hash: str,
) -> tuple[list[dict[str, float | str]], float, float]:
    """
    Retrieve long equity positions and key balance information for a brokerage account.

    This function queries the account details endpoint (requesting only the
    "positions" field), extracts all long positions, and returns a simplified
    representation of each position along with cash and buying power data.

    Args:
        account_hash (str):
            The unique account identifier used to request account details
            from the brokerage API.

    Returns:
        tuple[list[dict[str, float | str]], float, float]:
            A 3-element tuple containing:

            1. long_positions:
               A list of dictionaries representing long positions only.
               Each dictionary contains:
                   - 'symbol' (str): The instrument ticker symbol.
                   - 'quantity' (float): The long quantity held.
                   - 'price' (float): The average long entry price.

            2. cash_balance (float):
               The current available cash balance in the account.

            3. day_trading_buying_power (float):
               The day trading buying power if the account type is "MARGIN".
               Returns 0.0 for non-margin accounts.

    Raises:
        KeyError:
            If expected keys (e.g., 'securitiesAccount', 'positions',
            'currentBalances') are missing from the API response.
        requests.HTTPError:
            If the underlying API request fails.

    Notes:

        >>> account_data.keys()
        dict_keys(['securitiesAccount', 'aggregatedBalance'])

        >>> account_data['securitiesAccount'].keys()
        dict_keys(['type', 'accountNumber', 'roundTrips', 'isDayTrader', 'isClosingOnlyRestricted', 'pfcbFlag', 'positions', 'initialBalances', 'currentBalances', 'projectedBalances'])
        >>> account_data['securitiesAccount']['type']
        'MARGIN'
        >>> account_data['securitiesAccount']['accountNumber']
        '29308909'
        >>> account_data['securitiesAccount']['roundTrips']
        0
        >>> account_data['securitiesAccount']['isDayTrader']
        True
        >>> account_data['securitiesAccount']['isClosingOnlyRestricted']
        False
        >>> account_data['securitiesAccount']['pfcbFlag']
        False
        >>> account_data['securitiesAccount']['positions']
        [{'shortQuantity': 0.0, 'averagePrice': 8.826, 'currentDayProfitLoss': -1218.0, 'currentDayProfitLossPercentage': -5.59, 'longQuantity': 2900.0, 'settledLongQuantity': 2900.0, 'settledShortQuantity': 0.0, 'instrument': {'assetType': 'EQUITY', 'cusip': '03945R102', 'symbol': 'ACHR', 'netChange': -0.42}, 'marketValue': 20590.0, 'maintenanceRequirement': 10295.0, 'averageLongPrice': 8.826, 'taxLotAverageLongPrice': 8.826, 'longOpenProfitLoss': -5005.400000000002, 'previousSessionLongQuantity': 2900.0, 'currentDayCost': 0.0}, ...]
        >>> account_data['securitiesAccount']['currentBalances']
        {'accruedInterest': 0.0, 'cashBalance': 873.81, 'cashReceipts': 0.0, 'longOptionMarketValue': 0.0, 'liquidationValue': 22297.08, 'longMarketValue': 21423.27, 'moneyMarketFund': 0.0, 'savings': 0.0, 'shortMarketValue': 0.0, 'pendingDeposits': 0.0, 'mutualFundValue': 0.0, 'bondValue': 0.0, 'shortOptionMarketValue': 0.0, 'availableFunds': 11211.9, 'availableFundsNonMarginableTrade': 11211.9, 'buyingPower': 37373.0, 'buyingPowerNonMarginableTrade': 11196.9, 'dayTradingBuyingPower': 0.0, 'equity': 22297.08, 'equityPercentage': 100.0, 'longMarginValue': 21423.27, 'maintenanceCall': 0.0, 'maintenanceRequirement': 11085.18, 'marginBalance': 0.0, 'regTCall': 0.0, 'shortBalance': 0.0, 'shortMarginValue': 0.0, 'sma': 25060.0}

        >>> account_data['aggregatedBalance'].keys()
        dict_keys(['currentLiquidationValue', 'liquidationValue'])
        >>> account_data['aggregatedBalance']['currentLiquidationValue']
        22297.08
        >>> account_data['aggregatedBalance']['liquidationValue']
        22297.08

    """

    account_data = client.account_details(
        accountHash=account_hash, fields="positions"
    ).json()  # dict of two keys ['securitiesAccount', 'aggregatedBalance']

    # pretty_json_string = json.dumps(account_data, indent=4)
    # print(pretty_json_string)

    positions = account_data["securitiesAccount"]["positions"]
    long_positions: list[dict[str, float | str]] = [
        {
            "symbol": pos["instrument"]["symbol"],
            "quantity": pos["longQuantity"],
            "price": pos["averageLongPrice"],
        }
        for pos in positions
    ]

    cash_balance: float = account_data["securitiesAccount"]["currentBalances"][
        "cashBalance"
    ]

    day_trading_buying_power: float = (
        account_data["securitiesAccount"]["currentBalances"]["dayTradingBuyingPower"]
        if account_data["securitiesAccount"]["type"] == "MARGIN"
        else 0.0
    )

    return long_positions, cash_balance, day_trading_buying_power


#
import sys

cached_module = [
    "src.schwab_bot.accounts.schwab",
    "src.schwab_bot.orders.utils",
    "src.schwab_bot.orders.equity",
    "src.schwab_bot.orders.option",
]
for module in cached_module:
    if exist := module in sys.modules:
        print(f"Found cached module '{module}': {exist} >> Deleting it")
        del sys.modules[module]

del AsyncSchwabAccountClient
# verify new object by its id, which is different from the previous one, indicating that the module has been reloaded and the new class definition is in effect.
id(AsyncSchwabAccountClient)
