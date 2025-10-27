from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from apps.menu.models import MenuItem
from .models import Cart, CartItem

@login_required(login_url='login')  
def cart_detail(request):
    cart, created = Cart.objects.get_or_create(user=request.user)
    return render(request, "cart/cart_detail.html", {"cart": cart})

@login_required(login_url='login')
def add_to_cart(request, item_id):
    item = get_object_or_404(MenuItem, id=item_id)
    cart, created = Cart.objects.get_or_create(user=request.user)

    cart_item, created = CartItem.objects.get_or_create(
        cart=cart,
        menu_item=item
    )

    if not created:
        cart_item.quantity += 1
        cart_item.save()

    return redirect("cart_detail")  

@login_required(login_url='login')
def remove_from_cart(request, cart_item_id):
    cart_item = get_object_or_404(CartItem, id=cart_item_id, cart__user=request.user)
    cart_item.delete()
    return redirect("cart_detail")
@login_required
def update_quantity(request, item_id):
    cart_item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
    
    if request.method == 'POST':
        quantity = request.POST.get('quantity')
        if quantity and quantity.isdigit():
            quantity = int(quantity)
            if quantity > 0:
                cart_item.quantity = quantity
                cart_item.save()
            else:
                cart_item.delete()
    
    return redirect('cart_detail') 