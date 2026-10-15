import base64
import json
import re
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class DarajaError(Exception):
    pass


def normalize_kenyan_phone(phone):
    digits = re.sub(r'\D', '', phone)
    if digits.startswith('0'):
        digits = '254' + digits[1:]
    elif digits.startswith('7') or digits.startswith('1'):
        digits = '254' + digits
    if not re.fullmatch(r'254[17]\d{8}', digits):
        raise ValueError('Enter a valid Kenyan mobile number, such as 0712345678.')
    return digits


def _api_root():
    if settings.MPESA_ENVIRONMENT == 'sandbox':
        return 'https://sandbox.safaricom.co.ke'
    if settings.MPESA_ENVIRONMENT == 'production':
        return 'https://api.safaricom.co.ke'
    raise ImproperlyConfigured('MPESA_ENVIRONMENT must be "sandbox" or "production".')


def _request_json(url, data=None, headers=None):
    body = json.dumps(data).encode('utf-8') if data is not None else None
    request = Request(
        url,
        data=body,
        headers=headers or {},
        method='POST' if body is not None else 'GET',
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode('utf-8'))
    except HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')
        raise DarajaError(f'Daraja returned HTTP {exc.code}: {detail}') from exc
    except URLError as exc:
        raise DarajaError(f'Could not reach Daraja: {exc.reason}') from exc
    except json.JSONDecodeError as exc:
        raise DarajaError('Daraja returned an invalid JSON response.') from exc


def initiate_stk_push(phone, amount, account_reference):
    required = {
        'MPESA_CONSUMER_KEY': settings.MPESA_CONSUMER_KEY,
        'MPESA_CONSUMER_SECRET': settings.MPESA_CONSUMER_SECRET,
        'MPESA_SHORTCODE': settings.MPESA_SHORTCODE,
        'MPESA_PASSKEY': settings.MPESA_PASSKEY,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ImproperlyConfigured(
            'Configure the following Daraja settings before accepting payments: '
            + ', '.join(missing)
        )
    callback = urlparse(settings.MPESA_CALLBACK_URL)
    if callback.scheme != 'https' or not callback.netloc:
        raise ImproperlyConfigured('MPESA_CALLBACK_URL must be an absolute public HTTPS URL.')

    root = _api_root()
    credentials = f'{settings.MPESA_CONSUMER_KEY}:{settings.MPESA_CONSUMER_SECRET}'
    encoded_credentials = base64.b64encode(credentials.encode('ascii')).decode('ascii')
    token_result = _request_json(
        f'{root}/oauth/v1/generate?{urlencode({"grant_type": "client_credentials"})}',
        headers={'Authorization': f'Basic {encoded_credentials}'},
    )
    access_token = token_result.get('access_token')
    if not access_token:
        raise DarajaError('Daraja did not return an access token.')

    timestamp = datetime.now(ZoneInfo('Africa/Nairobi')).strftime('%Y%m%d%H%M%S')
    password_source = f'{settings.MPESA_SHORTCODE}{settings.MPESA_PASSKEY}{timestamp}'
    password = base64.b64encode(password_source.encode('ascii')).decode('ascii')
    result = _request_json(
        f'{root}/mpesa/stkpush/v1/processrequest',
        data={
            'BusinessShortCode': settings.MPESA_SHORTCODE,
            'Password': password,
            'Timestamp': timestamp,
            'TransactionType': 'CustomerPayBillOnline',
            'Amount': int(amount),
            'PartyA': phone,
            'PartyB': settings.MPESA_SHORTCODE,
            'PhoneNumber': phone,
            'CallBackURL': settings.MPESA_CALLBACK_URL,
            'AccountReference': account_reference[:12],
            'TransactionDesc': 'TukuweFit order',
        },
        headers={
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        },
    )
    if str(result.get('ResponseCode')) != '0' or not result.get('CheckoutRequestID'):
        raise DarajaError(result.get('CustomerMessage') or result.get('ResponseDescription') or
                          'Daraja did not accept the STK Push request.')
    return result
