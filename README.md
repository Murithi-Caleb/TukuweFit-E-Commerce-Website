# TukuweFit

TukuweFit is a Django e-commerce web application for gym enthusiasts and gym owners to browse and purchase fitness equipment.

## Features

- Product catalog, search, and cookie-based shopping cart
- Customer accounts, profiles, order history, and order administration
- M-Pesa Daraja STK Push checkout with server-side callback confirmation
- Product and customer image uploads
- Django admin interface and contact/feedback forms

## Requirements

- Python 3.10 or newer
- A supported Django 5.2.x environment (see `requirements.txt`)
- A PostgreSQL database for hosted/production deployments; SQLite is configured for local development

## Local setup

From the repository root:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open `http://127.0.0.1:8000/`. Add products in Django admin at `/admin/`. The development settings use a development-only secret, enable debug mode, and print email to the console; do not use those defaults in production.

## Configuration

The application reads configuration from environment variables. Do not commit real credentials, local databases, or uploaded customer files.

| Variable | Purpose |
| --- | --- |
| `DJANGO_DEBUG` | Set to `false` in production. |
| `DJANGO_SECRET_KEY` | A unique, high-entropy Django secret; required when debug is off. |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hostnames serving the application. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma-separated HTTPS origins, including scheme, when required by the deployment. |
| `DB_ENGINE` | Defaults to SQLite. For PostgreSQL, set `django.db.backends.postgresql`. |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | Database credentials and connection settings. |
| `MPESA_ENVIRONMENT` | `sandbox` (default) or `production`. |
| `MPESA_CONSUMER_KEY`, `MPESA_CONSUMER_SECRET` | Daraja app credentials. |
| `MPESA_SHORTCODE`, `MPESA_PASSKEY` | Daraja shortcode and STK Push passkey. |
| `MPESA_CALLBACK_URL` | Public HTTPS callback URL, for example `https://shop.example.com/payments/mpesa/callback`. |
| `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | Optional outbound SMTP configuration. |
| `EMAIL_RECEIVING_USER` | Comma-separated recipient addresses for contact form messages. |

To test M-Pesa, create a Daraja sandbox application, set the sandbox credentials in the environment, and expose the callback endpoint through a public HTTPS tunnel or deployed HTTPS site. The application starts a payment request and only creates orders after a matching Daraja callback confirms the expected amount and phone number. A browser redirect alone never confirms an order. Use valid Safaricom production credentials and a verified HTTPS callback before switching to production.

The existing signing key was previously stored directly in the settings file. If it has ever been used outside local development, replace it and invalidate existing sessions. Removing sensitive files from the latest commit does not erase them from Git history; if real credentials or customer data were pushed, revoke/rotate those credentials and follow your hosting provider's procedure for purging exposed history.

## Production deployment notes

Before accepting real orders:

1. Use PostgreSQL and durable object storage for customer/product uploads. Do not rely on the local SQLite file or app filesystem for hosted data.
2. Configure all production environment variables, `DEBUG=false`, allowed hosts, CSRF origins, HTTPS, database backups, and email delivery.
3. Run migrations and `python manage.py collectstatic --noinput` as part of deployment. WhiteNoise serves collected static assets; user uploads still need durable media storage.
4. Configure a stable public HTTPS Daraja callback URL and verify successful, failed, mismatched, and duplicate callbacks in the Safaricom sandbox.
5. Run `python manage.py check --deploy` and resolve its warnings for the actual deployment environment.

## Free/low-cost hosting options

- **Render (Django web service) + a hosted PostgreSQL provider + Cloudinary or another object-storage service** is a straightforward way to prototype. Free plans and included quotas change, and free services may sleep or have limited database retention/availability; check the current terms before relying on them.
- **PythonAnywhere** is another Python-friendly option for a small Django deployment. Check its current free-plan limits, database choices, outbound network rules, and whether its plan supports the public HTTPS callback you need.
- **Vercel** can run Python functions, but is not the easiest fit for this stateful Django shop: serverless filesystems are ephemeral, request/function limits can interfere with payment callbacks, and SQLite/uploads cannot be treated as durable storage. Use external PostgreSQL and object storage if evaluating it, and confirm the current Python/Django runtime and function limits.

For a public demo, use sandbox payments and non-sensitive sample data. Free hosting is generally suitable for experiments, not a dependable production checkout; payment traffic, persistent media, backups, and support may require paid services. Confirm current provider pricing and free-tier conditions before deployment.

## Tests and checks

```powershell
python manage.py check
python manage.py test
python manage.py check --deploy
```
