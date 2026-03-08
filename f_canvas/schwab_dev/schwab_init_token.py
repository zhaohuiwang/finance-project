# https://medium.com/@carstensavage/the-unofficial-guide-to-charles-schwabs-trader-apis-14c1f5bc1d57
# https://medium.com/@carstensavage/cloud-deploy-your-trading-bot-charles-schwab-apis-google-cloud-0900de321951

# https://medium.com/@carstensavage/level-up-your-trading-bot-with-stock-news-7c3d8cfdeccd


import os
import base64
import requests
import webbrowser
import logging

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)

app_key = os.getenv("APP_KEY")
app_secret = os.getenv("APP_SECRET")
callback_url = os.getenv("CALLBACK_URL")


def construct_init_auth_url() -> tuple[str, str, str]:
    auth_url = f"https://api.schwabapi.com/v1/oauth/authorize?client_id={app_key}&redirect_uri={callback_url}"

    logging.info("Click to authenticate:")
    logging.info(auth_url)

    return app_key, app_secret, auth_url


def construct_headers_and_payload(returned_url, app_key, app_secret):
    response_code = (
        f"{returned_url[returned_url.index('code=') + 5: returned_url.index('%40')]}@"
    )

    credentials = f"{app_key}:{app_secret}"
    base64_credentials = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")

    headers = {
        "Authorization": f"Basic {base64_credentials}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    payload = {
        "grant_type": "authorization_code",
        "code": response_code,
        "redirect_uri": callback_url,
    }

    return headers, payload


def retrieve_tokens(headers, payload) -> dict:
    init_token_response = requests.post(
        url="https://api.schwabapi.com/v1/oauth/token",
        headers=headers,
        data=payload,
    )

    init_tokens_dict = init_token_response.json()

    return init_tokens_dict


def main():
    app_key, app_secret, cs_auth_url = construct_init_auth_url()
    webbrowser.open(cs_auth_url)

    logging.info("Paste Returned URL:")
    returned_url = input()

    init_token_headers, init_token_payload = construct_headers_and_payload(
        returned_url, app_key, app_secret
    )

    init_tokens_dict = retrieve_tokens(
        headers=init_token_headers, payload=init_token_payload
    )

    logging.debug(init_tokens_dict)

    return "Done!"


if __name__ == "__main__":
    main()
