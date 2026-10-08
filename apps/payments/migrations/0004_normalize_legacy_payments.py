from django.db import migrations

def normalize(apps, schema_editor):
    Payment = apps.get_model('payments', 'Payment')
    Order = apps.get_model('orders', 'Order')
    Issue = apps.get_model('orders', 'OrderIssue')
    for order in Order.objects.select_related('user').all().iterator():
        payment, _ = Payment.objects.get_or_create(order_id=order.pk, defaults={'user_id': order.user_id, 'method': 'cash'})
        if payment.method == 'card':
            payment.status = 'review'
            payment.save(update_fields=['status'])
        if order.status == 'cancel':
            payment.status = 'refund_due' if payment.status == 'paid' else 'cancelled'
            payment.save(update_fields=['status'])
        elif payment.method == 'card' and order.status not in ('done', 'cancel'):
            Issue.objects.get_or_create(order_id=order.pk, resolved_at=None, defaults={
                'author_id': order.user_id,
                'reason': 'Архивный заказ с имитацией оплаты картой. Требуется проверка и согласование оплаты с покупателем.'})

class Migration(migrations.Migration):
    dependencies = [('payments', '0003_alter_payment_options_remove_payment_otp_code_and_more'),
                    ('orders', '0007_orderevent_orderissue_alter_order_options_and_more')]
    operations = [migrations.RunPython(normalize, migrations.RunPython.noop)]
