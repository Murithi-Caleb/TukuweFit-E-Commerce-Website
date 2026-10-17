import json
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .models import Customer, Orders, PaymentTransaction, Product
from .payments import normalize_kenyan_phone


class CatalogAndAdminOrderViewTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            name='Training bench',
            price=2500,
            description='Adjustable gym bench',
        )

    def test_public_catalog_renders_products_without_uploaded_images(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.name)

    def test_admin_order_views_join_related_records(self):
        admin = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='test-password',
        )
        customer_user = User.objects.create_user(
            username='buyer',
            password='test-password',
            first_name='Test',
            last_name='Buyer',
        )
        customer = Customer.objects.create(
            user=customer_user,
            address='Nairobi',
            mobile='0712345678',
        )
        for _ in range(2):
            Orders.objects.create(
                customer=customer,
                product=self.product,
                email='buyer@example.com',
                address='Nairobi CBD',
                mobile='0712345678',
                status='Pending',
            )
        self.client.force_login(admin)

        for route_name in ('admin-dashboard', 'admin-view-booking'):
            with self.subTest(route_name=route_name):
                with CaptureQueriesContext(connection) as queries:
                    response = self.client.get(reverse(route_name))

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, self.product.name)
                order_queries = [
                    query['sql'].lower()
                    for query in queries
                    if (
                        'from "ecom_orders"' in query['sql'].lower()
                        and 'ecom_product' in query['sql'].lower()
                        and 'ecom_customer' in query['sql'].lower()
                    )
                ]
                self.assertEqual(len(order_queries), 1)


class KenyanPhoneNumberTests(TestCase):
    def test_normalizes_local_and_international_numbers(self):
        self.assertEqual(normalize_kenyan_phone('0712 345 678'), '254712345678')
        self.assertEqual(normalize_kenyan_phone('+254712345678'), '254712345678')

    def test_rejects_non_kenyan_or_invalid_numbers(self):
        with self.assertRaises(ValueError):
            normalize_kenyan_phone('12345')


class DarajaCheckoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='buyer', password='test-password')
        customer_group, _ = Group.objects.get_or_create(name='CUSTOMER')
        self.user.groups.add(customer_group)
        self.customer = Customer.objects.create(
            user=self.user,
            address='Nairobi',
            mobile='0712345678',
        )
        self.product = Product.objects.create(
            name='Training bench',
            price=2500,
            description='Adjustable gym bench',
        )
        self.client.force_login(self.user)

    @patch('ecom.views.initiate_stk_push')
    def test_checkout_starts_stk_push_and_keeps_payment_pending(self, initiate):
        initiate.return_value = {
            'ResponseCode': '0',
            'CheckoutRequestID': 'ws_CO_123',
            'MerchantRequestID': 'merchant_123',
            'CustomerMessage': 'Prompt sent',
        }

        response = self.client.get(reverse('add-to-cart', args=[self.product.pk]))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            reverse('customer-address'),
            {
                'Email': 'buyer@example.com',
                'Mobile': '0712345678',
                'Address': 'Nairobi CBD',
            },
        )

        self.assertEqual(response.status_code, 302)
        payment = PaymentTransaction.objects.get(checkout_request_id='ws_CO_123')
        self.assertEqual(payment.status, PaymentTransaction.STATUS_PENDING)
        self.assertEqual(payment.amount, self.product.price)
        self.assertEqual(payment.mobile, '254712345678')
        initiate.assert_called_once_with('254712345678', 2500, f'ORDER-{payment.pk}')

    def _make_payment(self, checkout_id='ws_CO_123'):
        return PaymentTransaction.objects.create(
            customer=self.customer,
            products=[self.product.pk],
            email='buyer@example.com',
            mobile='254712345678',
            address='Nairobi CBD',
            amount=2500,
            checkout_request_id=checkout_id,
        )

    def _post_callback(self, checkout_id='ws_CO_123', amount=2500, phone=254712345678):
        callback = {
            'Body': {
                'stkCallback': {
                    'CheckoutRequestID': checkout_id,
                    'ResultCode': 0,
                    'ResultDesc': 'The service request is processed successfully.',
                    'CallbackMetadata': {
                        'Item': [
                            {'Name': 'Amount', 'Value': amount},
                            {'Name': 'MpesaReceiptNumber', 'Value': 'QAB123XYZ'},
                            {'Name': 'PhoneNumber', 'Value': phone},
                        ],
                    },
                },
            },
        }
        return self.client.post(
            reverse('mpesa-callback'),
            data=json.dumps(callback),
            content_type='application/json',
        )

    def test_successful_callback_creates_order_once(self):
        payment = self._make_payment()

        response = self._post_callback()
        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentTransaction.STATUS_COMPLETED)
        self.assertEqual(payment.mpesa_receipt_number, 'QAB123XYZ')
        self.assertEqual(Orders.objects.filter(payment=payment).count(), 1)

        self._post_callback()
        self.assertEqual(Orders.objects.filter(payment=payment).count(), 1)

    def test_mismatched_amount_does_not_create_order(self):
        payment = self._make_payment()

        self._post_callback(amount=1)

        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentTransaction.STATUS_FAILED)
        self.assertFalse(Orders.objects.filter(payment=payment).exists())

    def test_callback_for_unknown_payment_is_rejected(self):
        response = self._post_callback(checkout_id='unknown')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Orders.objects.count(), 0)

    def test_payment_status_is_limited_to_owning_customer(self):
        payment = self._make_payment()
        other_user = User.objects.create_user(username='other', password='test-password')
        other_group, _ = Group.objects.get_or_create(name='CUSTOMER')
        other_user.groups.add(other_group)
        Customer.objects.create(user=other_user, address='Mombasa', mobile='0711111111')
        self.client.force_login(other_user)

        response = self.client.get(
            reverse('payment-status', args=[payment.pk]),
        )

        self.assertEqual(response.status_code, 404)
