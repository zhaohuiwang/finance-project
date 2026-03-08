### Charles Schwab Developter Portal

1. Charles Schwab Developer Portal > account setup, Trader API application
2. Charles Schwab Developer Portal > API Products > Trader API - Individual > 
Select "Accounts and Trading Production" or "Market Data Production" > Authorize 
3. For Specifications and Documentation, click "Details"


Available authorizations

Scopes are used to grant an application different levels of access to data on behalf of the end user. Each API may declare one or more scopes.

API requires the following scopes. Select which ones you want to grant to Swagger UI.

oauth (OAuth2, authorizationCode)
Authorized
Authorization URL: https://api.schwabapi.com/v1/oauth/authorize?response_type=code&client_id=1wzwOrhivb2PkR1UCAUVTKYqC4MTNYlj&scope=readonly&redirect_uri=https://developer.schwab.com/oauth2-redirect.html

Token URL: https://api.schwabapi.com/v1/oauth/token

Flow: authorizationCode

client_id: ******
A **callback** function, in computer programming, is a function passed as an argument to another function, intended to be executed at a later point in time by that other function. The term "callback" arises from the idea that the function being passed is "called back" by the receiving function after some operation or event has occurred.

In a web application or Client-Server apps (client-server model), the **client** refers to the user's device (like a web browser on a computer or phone) that requests information and interacts with the application. The **server** is the computer that hosts the web application and provides the requested data and functionality. Essentially, the client asks for something, and the server provides it. 

In modern web integrations, **callback URL** (a.k.a redirect URI) provide a means (virtual communication channels) for applications to communicate asynchronously. A callback URL is an address that receives notification from server when a specific event occurs, and any computer in the Internet/private network can POST data to it.

In general web development, callback URLs are used in scenarios such as:
- OAuth Authentication: When a user logs into a service using a third-party account (like their Google account), the third-party service will redirect the user back to the application using a callback URL after successful authentication.
- Payment Gateway Processes: After completing a transaction, a payment service will redirect the user back to the merchant's website using a callback URL, often adding transaction details in the query parameters.
- Asynchronous Operations: When an API operation doesn't yield an immediate response, it might accept a callback URL to notify the calling application once the operation is complete.



Example - Access/Refresh Token Response
```json
{
"expires_in": 1800, //Number of seconds access_token is valid for
"token_type": "Bearer",
"scope": "api",
"refresh_token": "{REFRESH_TOKEN_HERE}", //Valid for 7 days
"access_token": "{ACCESS_TOKEN_HERE}", //Valid for 30 minutes
"id_token": "{JWT_HERE}"
}
```
### References
* [Schwabdev Documentation](https://tylerebowers.github.io/Schwabdev/?source=pages%2Fwelcome.html)
* [Github - Schwabdev scripts/docs/examples](https://github.com/tylerebowers/Schwabdev)

* [dotenv - Python Package Index (PyPI) repository](https://pypi.org/project/python-dotenv/)

* [schwabdev - PyPI repository](https://pypi.org/project/schwabdev/)

* [Hithub - schwab-py](https://github.com/alexgolec/schwab-py)
* [schwab-py - PyPI repository](https://pypi.org/project/schwab-py/)

* [Mozilla Developer Web Docs](https://developer.mozilla.org/en-US/docs/Learn_web_development)

```python
# token.py
class Tokens:
    def __init__():
        """"Initialize a tokens manager"""
    @staticmethod
    def _validate_input():
        """Validates initialization parameters.""""
    def _post_oauth_token(self, grant_type: str, code: str):
        """Makes API calls with auth code for new/refresh tokens"""  
        requests.post('https://api.schwabapi.com/v1/oauth/token', headers=headers, data=data) # 'grant_type': 'authorization_code' or 'refresh_token' specified in data parameter
        #  refresh_token valid for 7 day, access_token valid for 0.5 hr. So keep refreshing an access_token (with existing refresh_token) until the refresh token expires in a week.

    def _set_tokens():
        """Writes token file and sets class variables, from response.json()"""  
     def update_tokens():
        """Checks if tokens need to be updated and updates if needed (only access token is automatically updated)"""

    def _generate_certificate():
        """Generate a self-signed certificate for use in capturing the callback during authentication"""
    def _update_refresh_token_from_code():
        """Get new access and refresh tokens using either 1. callback url or 2. authorization code."""
        # input parameter can be either a callback url or authorization code. If callback url, then extra the code from it. If code, then apply it directly. 
        ...
        response = self._post_oauth_token('authorization_code', code)
        ...
        self._set_tokens(now, now, response.json())
        ...
    def _launch_capture_server(self, url_base, url_port):
        """
        ShareCode Class: A simple class to share the captured authorization code between the HTTP handler and the main function.
        HTTPHandler Class: Extract code from URL
        Server setup - create a SharedCode instance, initialized an HTTP server
        SSL/TLS Configuration - Checks for the existence of SSL certificate (localhost.crt) and key (localhost.key) files in ~/.schwabdev/. If either file is missing, calls `_generate_certificate` to create them.
        Server Loop and Code Capture -
        """
    def update_access_token(self):
        """"refresh" the access token using self._set_tokens()"""
        ...
        response = self._post_oauth_token('refresh_token', self.refresh_token)
        if response.ok:
            self._set_tokens(at_issued, self._refresh_token_issued, response.json())
    def update_refresh_token(self):
        """Get new access and refresh tokens using (OAuth 2.0 authorization) code."""
        ...
        webbrowser.open(authorization_url)
        ...
        response_url = input("[Schwabdev] After authorizing, paste the address bar url here: ")
        code = f"{response_url[response_url.index('code=') + 5:response_url.index('%40')]}@"
        # response_url.index('code=') returns the index where "code=" starts
        # response_url.index('code=') + 5: Moves the starting point 5 characters forward to skip "code=" (since "code=" is 5 characters long) to get to the start of the actual authorization code.
        # response_url.index('%40'): Finds the index of %40 (URL-encoded @), which marks the end of the authorization code in this URL.
        # f"{...}@": Wraps the extracted substring in an f-string and appends an @ character to it. The result is stored in the `code` variable.
        # example response_url = https://example.com/callback?code=abc123%40xyz&state=some_state, then code = 'abc123'
        if code is not None:
            self._update_refresh_token_from_code(code)



# client.py
class Client:
    def __init__():
        """"Initialize a client to access the Schwab API.""" 
    def _params_parser(self, params: dict):
        """ Removes None (null) values """
    def _time_convert(self, dt=None, format: str | TimeFormat=TimeFormat.ISO_8601) -> str | int | None:
        """ Convert time to the correct format, passthrough if a string, preserve None if None for params parser """
    

    _base_api_url = "https://api.schwabapi.com"

    # GET, account numbers, all the linked accounts and a specific account hash
    f"{self._base_api_url}/trader/v1/accounts/accountNumbers", headers, timeout
    f"{self._base_api_url}/trader/v1/accounts/", headers, params, timeout
    f"{self._base_api_url}/trader/v1/accounts/{accountHash}", headers, params, timeout

    
    # POST (place an order), PUT (replace an order) - why json-order?
    f"{self._base_api_url}/trader/v1/accounts/{accountHash}/orders/{orderId}", headers, json=order, timeout
    # GET (order details), DELETE (cancel an order),
    f"{self._base_api_url}/trader/v1/accounts/{accountHash}/orders/{orderId}", headers, timeout

    # GET all transactions
    f"{self._base_api_url}/trader/v1/accounts/{accountHash}/transactions", headers, params, timeout
    # GET a specific transaction
    f"{self._base_api_url}/trader/v1/accounts/{accountHash}/transactions/{transactionId}",headers, timeout
    # GET user preference information
    f"{self._base_api_url}/trader/v1/userPreference", headers, timeout


    # GET quotes for a list of stocks
    f"{self._base_api_url}/marketdata/v1/quotes", headers, params, timeout
    # GET Option Chain
    f"{self._base_api_url}/marketdata/v1/chains", headers, timeout
    # GET an option expiration chain
    f"{self._base_api_url}/marketdata/v1/expirationchain", headers, params, timeout
    # GET price history for a ticker
    f"{self._base_api_url}/marketdata/v1/pricehistory", headers, params, timeout
    # GET movers in a specific index and direction
    f"{self._base_api_url}/marketdata/v1/movers/{symbol}", headers, params, timeout

    # GET Market Hours, or a specific  market id ("equity"|"option"|"bond"|"future"|"forex")
    f"{self._base_api_url}/marketdata/v1/markets", headers, params, timeout
    f"{self._base_api_url}/marketdata/v1/markets/{market_id}", headers, params, timeout

    # GET instruments for a list of symbols, or a single cusip
    f"{self._base_api_url}/marketdata/v1/instruments", headers, params, timeout
    f"{self._base_api_url}/marketdata/v1/instruments/{cusip_id}", headers, timeout

```

**Headers Only**: Headers are always required because they handle authentication (Authorization Header) and specify the format of the request/response (Content-Type Header). Used for simple GET requests (e.g., listing all accounts) where the access token in the headers is sufficient to identify the user and no additional data is needed.
**Headers + Params**: Required when the endpoint needs specific data, such as an account ID, additional fields (e.g., positions), or a payload for actions like placing orders.

```python
url = "https://api.schwabapi.com/trader/v1/accounts/{accountHash}"
headers = {
    "Authorization": "Bearer {access_token}",
    "Content-Type": "application/json"
}
params = {"fields": "positions"}  # Optional query params
response = requests.get(url, headers=headers, params=params)


url = "https://api.schwabapi.com/trader/v1/accounts/{accountHash}/orders"
headers = {
    "Authorization": "Bearer {access_token}",
    "Content-Type": "application/json",
    "Accept": "application/json"
}
payload = {
    "orderType": "LIMIT",
    "session": "NORMAL",
    "duration": "DAY",
    "symbol": "AAPL",
    "quantity": 10,
    "price": "150.00"
}
response = requests.post(url, headers=headers, json=payload)
```