from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.cart.models import Cart, CartItem
from apps.courier.models import Courier
from apps.menu.models import Category, MenuItem
from apps.orders.models import Order, OrderItem
from apps.payments.models import Payment


class WorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('customer', password='test-password')
        self.client.force_login(self.user)
        category = Category.objects.create(name='Food')
        self.item = MenuItem.objects.create(category=category, name='Burger', price=12000)

    def test_customer_home_redirects_to_public_home(self):
        self.assertEqual(reverse('home'), '/')
        self.assertRedirects(self.client.get(reverse('user_home')), '/')

    def test_both_courier_registration_urls_create_role_and_profile(self):
        for index, route in enumerate(('register_courier', 'courier_register')):
            with self.subTest(route=route):
                self.client.logout()
                response = self.client.post(reverse(route), {
                    'username': f'courier{index}', 'email': 'courier@example.com',
                    'password1': 'StrongCourierPass123!', 'password2': 'StrongCourierPass123!',
                    'name': 'Courier Name', 'phone': '+998901234567', 'vehicle': 'bike',
                })
                self.assertRedirects(response, reverse('courier_orders'))
                user = get_user_model().objects.get(username=f'courier{index}')
                self.assertEqual(user.role, 'courier')
                self.assertEqual(user.courier_profile.name, 'Courier Name')
                self.assertEqual(user.phone, '+998901234567')

    def test_cart_removal_route_and_ownership(self):
        cart = Cart.objects.create(user=self.user)
        item = CartItem.objects.create(cart=cart, menu_item=self.item)
        self.assertRedirects(self.client.post(reverse('remove_from_cart', args=[item.pk])), reverse('cart_detail'))
        self.assertFalse(CartItem.objects.filter(pk=item.pk).exists())
        other = get_user_model().objects.create_user('other')
        foreign = CartItem.objects.create(cart=Cart.objects.create(user=other), menu_item=self.item)
        self.assertEqual(self.client.post(reverse('remove_from_cart', args=[foreign.pk])).status_code, 404)
        self.assertTrue(CartItem.objects.filter(pk=foreign.pk).exists())

    def test_cash_checkout_and_success_are_idempotent(self):
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, menu_item=self.item, quantity=2)
        response = self.client.post(reverse('create_order'), {'payment_method': 'cash', 'address': 'Test address'})
        order = Order.objects.get(user=self.user)
        self.assertRedirects(response, reverse('order_success', args=[order.pk]))
        self.assertEqual(order.total_price, Decimal('24000'))
        self.assertEqual(order.items.get().price, Decimal('12000'))
        self.assertFalse(cart.items.exists())
        for _ in range(2):
            self.assertEqual(self.client.get(reverse('cash_success', args=[order.pk])).status_code, 200)
        self.assertEqual(Payment.objects.filter(order=order).count(), 1)
        order.payment.status = 'paid'
        order.payment.save()
        self.client.get(reverse('cash_success', args=[order.pk]))
        order.payment.refresh_from_db()
        self.assertEqual(order.payment.status, 'paid')

    def test_courier_can_confirm_assigned_cash_order(self):
        user = get_user_model().objects.create_user('courier', role='courier')
        courier = Courier.objects.create(user=user, name='Courier', phone='123')
        order = Order.objects.create(user=self.user, courier=courier, status='delivery')
        payment = Payment.objects.create(order=order, user=self.user, method='cash')
        self.client.force_login(user)
        response = self.client.get(reverse('courier_orders'))
        self.assertContains(response, reverse('confirm_cash_payment', args=[order.pk]))
        self.assertRedirects(self.client.post(reverse('confirm_cash_payment', args=[order.pk])), reverse('courier_orders'))
        payment.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(payment.status, 'paid')
        self.assertEqual(order.status, 'paid')

    def test_order_line_uses_price_at_checkout(self):
        order = Order.objects.create(user=self.user)
        line = OrderItem.objects.create(order=order, menu_item=self.item, quantity=2, price=10000)
        self.assertEqual(line.total(), 20000)

    def test_failed_checkout_preserves_cart_and_rolls_back_order(self):
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, menu_item=self.item)
        with patch('apps.orders.views.OrderItem.objects.create', side_effect=RuntimeError('failed write')):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse('create_order'), {'payment_method': 'cash'})
        self.assertFalse(Order.objects.filter(user=self.user).exists())
        self.assertEqual(cart.items.count(), 1)
