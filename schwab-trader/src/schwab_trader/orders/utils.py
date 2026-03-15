import datetime as dt
from datetime import datetime, timezone
from collections.abc import Callable, Iterator, Iterable
from dotenv import load_dotenv


from typing import  Any

from schwab_trader.accounts.schwab import client


def place_order(client, accountHash: str, order: dict) -> tuple[int, str, str]:
    """
    Place an order for a given account hash.
    Args:
        client: schwabdev.Client instance (authenticated)
        accountHash: str, your account identifier
        order: dict, payload for the order

    Returns:
    tuple[int, str, str]: (status_code, date, order_id)
        - status_code: HTTP status code, 201 >>> success!
        - date: Server Date header
        - order_id: Extracted from Location header

    for key, value in response.headers.items():
        print(f"{key}: {value}")

    response.headers.get("Date")
    It is the HTTP-date format defined in RFC 7231, e.g. "Thu, 05 Mar 2026 23:09:23 GMT"
    Whereas order details from API is in ISO 8601 format. e.g. "2026-03-05T23:09:22+0000"
    Notice UTC (+0000), and GMT (same as UTC)
    """

    response = client.place_order(accountHash=accountHash, order=order)

    status_code = response.status_code

    date = response.headers.get("Date")

    location = response.headers.get("Location")
    order_id = location.split("/")[-1] if location else None

    return status_code, date, order_id


def cancel_order(client, accountHash: str, order_id: int) -> tuple[int, str]:
    """
    Cancel an order for a given account hash and order id.
    Args:
        client: schwabdev.Client instance (authenticated)
        accountHash: str, your account identifier
        order_id: order id to be canceled

    tuple[int, str, str]: (status_code, date)
        - status_code: HTTP status code, 201 >>> success!
        - date: Server Date header

    for key, value in response.headers.items():
        print(f"{key}: {value}")

    response.headers.get("Date")
    """

    response = client.cancel_order(accountHash=accountHash, orderId=order_id)

    date = response.headers.get("Date")
    status_code = response.status_code

    return status_code, date


def get_utc_time_range(
    to_time: dt.datetime = None,
    *,
    offset: dt.timedelta = dt.timedelta(minutes=20),
):
    """
    Generate UTC ISO-formatted from_time and to_time for API calls.

    Args:
        to_time: datetime object to use as end time (defaults to now)
        offset: timedelta to subtract from to_time to get from_time. Only accept the following delta units, not months nor years weeks=1,          # 1 week
        days=3,           # 3 days
        hours=4,          # 4 hours
        minutes=20,       # 20 minutes
        seconds=15,       # 15 seconds
        milliseconds=500, # 0.5 second
        microseconds=250  # 0.00025 second
    Returns:
        tuple: (from_time_iso, to_time_iso)

    Example:
    >>> from_time, to_time = get_utc_time_range(
    ...     offset=datetime.timedelta(minutes=20)
    ...     )
    >>> from_time, to_time
    ('2026-03-06T03:01:58.246+00:00', '2026-03-06T03:21:58.246+00:00')

    >>> from_time, to_time = get_utc_time_range(
    ...     to_time=datetime.datetime(2026, 3, 6, 10, 0),
    ...     offset=datetime.timedelta(minutes=20)
    ...     )
    >>> from_time, to_time
    ('2026-03-06T15:40:00.000+00:00', '2026-03-06T16:00:00.000+00:00')

    """

    # Default to now if no to_time provided
    if to_time is None:
        to_time = dt.datetime.now().astimezone()
    else:
        # Ensure timezone-aware
        if to_time.tzinfo is None:
            to_time = to_time.astimezone()

    from_time = to_time - offset

    # Lambda to convert any datetime to UTC ISO with milliseconds
    to_iso_utc = lambda dt: dt.astimezone(timezone.utc).isoformat(
        timespec="milliseconds"
    )

    return to_iso_utc(from_time), to_iso_utc(to_time)




###  Instead of recursion, we use a stack to remember what to process next. Each iteration pops a node from the stack and checks it. Children are pushed onto the stack instead of calling recursively. No yield from is needed — the while loop naturally continues iteration.


def iter_keys_path_tuple(
    data: dict | list,
    keys: str | Iterable[str],
    predicate: Callable[[dict], bool] | None = None,
    root_name: str = "data",
) -> Iterator[tuple[tuple[str, object], ...]]:
    """
    Traverse nested JSON (Schwab order) and yield tuples of (path_str, value) for multiple keys, optionally filtered by a predicate.

    Parameters
    ----------
    data : dict | list
        Nested JSON structure.
    keys : str | Iterable[str]
        Key or keys to search for.
    predicate : Callable[[dict], bool] | None
        Optional filter applied to candidate dictionaries.
    root_name : str
        Root name for Python-style paths.

    Yields
    ------
    tuple of (path_str, value) pairs for each dict containing the keys at the same level.

    Example:
    iter_result = list(
        iter_keys_path_tuple(
            data=orders,
            keys=['orderId', 'enteredTime'],
            predicate=lambda d: d.get("cancelable") is True,
            root_name="orders",
            )
        )
    >>> from pprint import pprint
    >>> pprint(iter_result)
    [(("orders[0]['enteredTime']", '2026-03-04T17:32:30+0000'),
    ("orders[0]['orderId']", 1005596382168)),
    (("orders[0]['childOrderStrategies'][0]['enteredTime']",
    '2026-03-04T17:32:30+0000'),
    ("orders[0]['childOrderStrategies'][0]['orderId']", 1005596382169))]

    >>> pprint([dict(group) for group in iter_result])
    [{"orders[0]['enteredTime']": '2026-03-04T17:32:30+0000',
    "orders[0]['orderId']": 1005596382168},
    {"orders[0]['childOrderStrategies'][0]['enteredTime']": '2026-03-04T17:32:30+0000',
    "orders[0]['childOrderStrategies'][0]['orderId']": 1005596382169}]

    # to get a list of orderIds
    >>> order_ids = [
    ...     value
    ...     for group in iter_result
    ...     for path, value in group
    ...     if "['orderId']" in path
    ...     ]
    >>>
    >>> order_ids
    [1005596382168, 1005596382169]

    """

    if isinstance(keys, str):
        keys_to_match = {keys}
    else:
        keys_to_match = set(keys)

    stack: list[tuple[dict | list, tuple[int | str, ...]]] = [(data, ())]

    while stack:
        current, path = stack.pop()

        if isinstance(current, list):
            # Process lists first
            for idx, item in enumerate(current):
                stack.append((item, path + (idx,)))

        elif isinstance(current, dict):
            if predicate is None or predicate(current):
                # Collect all keys that exist at this level
                matched = tuple(
                    (
                        root_name
                        + "".join(
                            f"[{p!r}]" if isinstance(p, str) else f"[{p}]"
                            for p in path + (k,)
                        ),
                        current[k],
                    )
                    for k in keys_to_match
                    if k in current
                )
                if matched:
                    yield matched

            # Add children to stack
            for k, v in current.items():
                stack.append((v, path + (k,)))


# Simple lambda conversion to convert datetime.datetime to ISO UTC time format, e.g. '2026-03-06T00:54:57.375+00:00'
to_iso_utc = lambda dt: dt.astimezone(timezone.utc).isoformat(timespec="milliseconds")



def extract_final_executions(
    hashValue: str,
    status: str | None = None,
    fromEnteredTime: Any = None,
    toEnteredTime: Any = None,
) -> list[dict[str, Any]]:
    """
    Extracts all executed orders (including nested child orders) for a given account,
    returning a list of dictionaries with execution details, order hierarchy, and type.

    Args:
        hashValue (str): Account hash to fetch orders for.
        status (str | None, optional): Filter orders by status (e.g., 'FILLED'). Defaults to None.
        fromEnteredTime (Any, optional): Start time filter for orders. Defaults to None.
        toEnteredTime (Any, optional): End time filter for orders. Defaults to None.

    Returns:
        List[Dict[str, Any]]: A list of execution dictionaries.
    """
    from datetime import datetime
    
    orders = client.account_orders(
        accountHash=hashValue,
        fromEnteredTime=fromEnteredTime,
        toEnteredTime=toEnteredTime,
        status=status,
    ).json()

    results: list[dict[str, Any]] = []

    def parse_orders(order_list: list[dict[str, Any]], parent_id: int | None = None) -> None:
        for order in order_list:
            order_id = order.get("orderId")
            order_status = order.get("status")
            cancelable = order.get("cancelable")
            editable = order.get("editable")
            order_type = order.get("orderType")
            placed_time = (
                datetime.fromisoformat(order["enteredTime"].replace("Z", "+00:00"))
                if order.get("enteredTime")
                else None
            )
            note = "simple" if parent_id is None else f"child_of_{parent_id}"

            # Map legId → instrument info
            leg_map = {}
            for leg in order.get("orderLegCollection", []):
                leg_map[leg["legId"]] = {
                    "symbol": leg["instrument"]["symbol"],
                    "instruction": leg["instruction"],
                }

            for activity in order.get("orderActivityCollection", []):
                if activity.get("activityType") != "EXECUTION":
                    continue

                for exec_leg in activity.get("executionLegs", []):
                    leg_id = exec_leg.get("legId")
                    leg_info = leg_map.get(leg_id, {})
                    instruction = leg_info.get("instruction", "")
                    side = "BUY" if instruction.startswith("BUY") else "SELL"

                    executed_time = (
                        datetime.fromisoformat(exec_leg["time"].replace("Z", "+00:00"))
                        if exec_leg.get("time")
                        else None
                    )

                    results.append(
                        {
                            "orderId": order_id,
                            "symbol": leg_info.get("symbol"),
                            "instruction": instruction,
                            "side": side,
                            "orderType": order_type,
                            "price": exec_leg.get("price"),
                            "quantity": exec_leg.get("quantity"),
                            "status": order_status,
                            "cancelable": cancelable,
                            "editable": editable,
                            "note": note,
                            "placedTime": placed_time,
                            "executedTime": executed_time,
                        }
                    )

            # Recurse nested orders
            if "childOrderStrategies" in order:
                parse_orders(order["childOrderStrategies"], parent_id=order_id)

    parse_orders(orders)

    return results

class TimeUtil:
    """
    Example Usage

        from datetime import datetime

        local_time = datetime.now()

        >>> TimeUtil.to_utc(local_time)
        datetime.datetime(2026, 3, 6, 1, 39, 23, 565998, tzinfo=datetime.timezone.utc)

        # Standard ISO 8601 (+00:00)
        >>> TimeUtil.to_iso_utc(local_time)
        2026-03-06T01:39:23.565+00:00

        # Compact ISO (+0000)
        >>> TimeUtil.to_iso_utc(local_time, compact=True)
        Compact ISO: 2026-03-06T01:39:23.565+0000

        # Current UTC now, compact
        >>> TimeUtil.now_iso(compact=True)
        '2026-03-06T01:40:55.208+0000'
        >>> iso_standard = "2026-03-06T01:45:12.456+00:00"
        >>> dt1 = TimeUtil.parse_iso(iso_standard)
        >>> print(dt1, dt1.tzinfo)
        2026-03-06 01:45:12.456000+00:00 UTC
    """

    @staticmethod
    def ensure_tz(dt: datetime) -> datetime:
        """Attach local timezone if naive."""
        return dt if dt.tzinfo else dt.astimezone()

    @staticmethod
    def to_utc(dt: datetime) -> datetime:
        """Convert any datetime to UTC."""
        return TimeUtil.ensure_tz(dt).astimezone(timezone.utc)

    @staticmethod
    def to_iso_utc(dt: datetime, compact: bool = False) -> str:
        """
        Convert datetime to UTC ISO 8601 string.

        Args:
            dt: datetime object (naive or aware)
            compact: False → standard ISO (+00:00)
                     True  → compact ISO (+0000)

        Returns:
            ISO 8601 string with milliseconds
        """
        dt_utc = TimeUtil.to_utc(dt)
        if compact:
            # YYYY-MM-DDTHH:MM:SS.mmm+0000
            return dt_utc.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+0000"
        else:
            # Standard ISO with colon
            return dt_utc.isoformat(timespec="milliseconds")

    @staticmethod
    def now_iso(compact: bool = False) -> str:
        """Get current UTC time in ISO 8601, optional compact format."""
        return TimeUtil.to_iso_utc(datetime.now(timezone.utc), compact=compact)

    @staticmethod
    def to_epoch(dt: datetime) -> int:
        """Convert any datetime to Unix epoch seconds (UTC)."""
        return int(TimeUtil.to_utc(dt).timestamp())

    @staticmethod
    def from_epoch(ts: int) -> datetime:
        """Convert Unix epoch seconds to UTC datetime."""
        return datetime.fromtimestamp(ts, timezone.utc)

    @staticmethod
    def parse_iso(s: str) -> datetime:
        """Parse ISO 8601 string to datetime, handling 'Z' for UTC."""
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
