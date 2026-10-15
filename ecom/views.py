import json
import logging

from django.shortcuts import render,redirect,reverse
from . import forms,models
from django.http import HttpResponseRedirect,HttpResponse,JsonResponse
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import send_mail
from django.contrib.auth.models import Group
from django.contrib.auth.decorators import login_required,user_passes_test
from django.db import transaction
from django.contrib import messages
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .models import PaymentTransaction
from .payments import DarajaError, initiate_stk_push, normalize_kenyan_phone


logger = logging.getLogger(__name__)

def download_invoice_view(request, orderID, productID):
    # Your code for downloading invoice
    return HttpResponse("Invoice download functionality")

def home_view(request):
    products=models.Product.objects.all()
    if 'product_ids' in request.COOKIES:
        product_ids = request.COOKIES['product_ids']
        counter=product_ids.split('|')
        product_count_in_cart=len(set(counter))
    else:
        product_count_in_cart=0
    if request.user.is_authenticated:
        return HttpResponseRedirect('afterlogin')
    return render(request,'ecom/index.html',{'products':products,'product_count_in_cart':product_count_in_cart})
    


#for showing login button for admin.
def adminclick_view(request):
    if request.user.is_authenticated:
        return HttpResponseRedirect('afterlogin')
    return HttpResponseRedirect('adminlogin')


def customer_signup_view(request):
    userForm=forms.CustomerUserForm()
    customerForm=forms.CustomerForm()
    mydict={'userForm':userForm,'customerForm':customerForm}
    if request.method=='POST':
        userForm=forms.CustomerUserForm(request.POST)
        customerForm=forms.CustomerForm(request.POST,request.FILES)
        if userForm.is_valid() and customerForm.is_valid():
            user=userForm.save()
            user.set_password(user.password)
            user.save()
            customer=customerForm.save(commit=False)
            customer.user=user
            customer.save()
            my_customer_group = Group.objects.get_or_create(name='CUSTOMER')
            my_customer_group[0].user_set.add(user)
            return HttpResponseRedirect('customerlogin')
        mydict={'userForm':userForm,'customerForm':customerForm}
    return render(request,'ecom/customersignup.html',context=mydict)

#for checking user is a customer
def is_customer(user):
    return user.groups.filter(name='CUSTOMER').exists()

#---------AFTER ENTERING CREDENTIALS WE CHECK WHETHER USERNAME AND PASSWORD IS OF ADMIN,CUSTOMER
def afterlogin_view(request):
    if is_customer(request.user):
        return redirect('customer-home')
    else:
        return redirect('admin-dashboard')

#---------------------------------------------------------------------------------
#------------------------ ADMIN RELATED VIEWS START ------------------------------
#---------------------------------------------------------------------------------
@login_required(login_url='adminlogin')
def admin_dashboard_view(request):
    # for cards on dashboard
    customercount=models.Customer.objects.all().count()
    productcount=models.Product.objects.all().count()
    ordercount=models.Orders.objects.all().count()

    # for recent order tables
    orders=models.Orders.objects.all()
    ordered_products=[]
    ordered_bys=[]
    for order in orders:
        ordered_product=models.Product.objects.all().filter(id=order.product.id)
        ordered_by=models.Customer.objects.all().filter(id = order.customer.id)
        ordered_products.append(ordered_product)
        ordered_bys.append(ordered_by)

    mydict={
    'customercount':customercount,
    'productcount':productcount,
    'ordercount':ordercount,
    'data':zip(ordered_products,ordered_bys,orders),
    }
    return render(request,'ecom/admin_dashboard.html',context=mydict)


# admin view customer table
@login_required(login_url='adminlogin')
def view_customer_view(request):
    customers=models.Customer.objects.all()
    return render(request,'ecom/view_customer.html',{'customers':customers})

# admin delete customer
@login_required(login_url='adminlogin')
def delete_customer_view(request,pk):
    customer=models.Customer.objects.get(id=pk)
    user=models.User.objects.get(id=customer.user_id)
    user.delete()
    customer.delete()
    return redirect('view-customer')


@login_required(login_url='adminlogin')
def update_customer_view(request,pk):
    customer=models.Customer.objects.get(id=pk)
    user=models.User.objects.get(id=customer.user_id)
    userForm=forms.CustomerUserForm(instance=user)
    customerForm=forms.CustomerForm(request.FILES,instance=customer)
    mydict={'userForm':userForm,'customerForm':customerForm}
    if request.method=='POST':
        userForm=forms.CustomerUserForm(request.POST,instance=user)
        customerForm=forms.CustomerForm(request.POST,instance=customer)
        if userForm.is_valid() and customerForm.is_valid():
            user=userForm.save()
            user.set_password(user.password)
            user.save()
            customerForm.save()
            return redirect('view-customer')
    return render(request,'ecom/admin_update_customer.html',context=mydict)

# admin view the product
@login_required(login_url='adminlogin')
def admin_products_view(request):
    products=models.Product.objects.all()
    return render(request,'ecom/admin_products.html',{'products':products})


# admin add product by clicking on floating button
@login_required(login_url='adminlogin')
def admin_add_product_view(request):
    productForm=forms.ProductForm()
    if request.method=='POST':
        productForm=forms.ProductForm(request.POST, request.FILES)
        if productForm.is_valid():
            productForm.save()
        return HttpResponseRedirect('admin-products')
    return render(request,'ecom/admin_add_products.html',{'productForm':productForm})


@login_required(login_url='adminlogin')
def delete_product_view(request,pk):
    product=models.Product.objects.get(id=pk)
    product.delete()
    return redirect('admin-products')


@login_required(login_url='adminlogin')
def update_product_view(request,pk):
    product=models.Product.objects.get(id=pk)
    productForm=forms.ProductForm(instance=product)
    if request.method=='POST':
        productForm=forms.ProductForm(request.POST,request.FILES,instance=product)
        if productForm.is_valid():
            productForm.save()
            return redirect('admin-products')
    return render(request,'ecom/admin_update_product.html',{'productForm':productForm})


@login_required(login_url='adminlogin')
def admin_view_booking_view(request):
    orders=models.Orders.objects.all()
    ordered_products=[]
    ordered_bys=[]
    for order in orders:
        ordered_product=models.Product.objects.all().filter(id=order.product.id)
        ordered_by=models.Customer.objects.all().filter(id = order.customer.id)
        ordered_products.append(ordered_product)
        ordered_bys.append(ordered_by)
    return render(request,'ecom/admin_view_booking.html',{'data':zip(ordered_products,ordered_bys,orders)})


@login_required(login_url='adminlogin')
def delete_order_view(request,pk):
    order=models.Orders.objects.get(id=pk)
    order.delete()
    return redirect('admin-view-booking')

# for changing status of order (pending,delivered...)
@login_required(login_url='adminlogin')
def update_order_view(request,pk):
    order=models.Orders.objects.get(id=pk)
    orderForm=forms.OrderForm(instance=order)
    if request.method=='POST':
        orderForm=forms.OrderForm(request.POST,instance=order)
        if orderForm.is_valid():
            orderForm.save()
            return redirect('admin-view-booking')
    return render(request,'ecom/update_order.html',{'orderForm':orderForm})


# admin view the feedback
@login_required(login_url='adminlogin')
def view_feedback_view(request):
    feedbacks=models.Feedback.objects.all().order_by('-id')
    return render(request,'ecom/view_feedback.html',{'feedbacks':feedbacks})



def search_view(request):
    # whatever user write in search box we get in query
    query = request.GET['query']
    products=models.Product.objects.all().filter(name__icontains=query)
    if 'product_ids' in request.COOKIES:
        product_ids = request.COOKIES['product_ids']
        counter=product_ids.split('|')
        product_count_in_cart=len(set(counter))
    else:
        product_count_in_cart=0

    # word variable will be shown in html when user click on search button
    word="Searched Result :"

    if request.user.is_authenticated:
        return render(request,'ecom/customer_home.html',{'products':products,'word':word,'product_count_in_cart':product_count_in_cart})
    return render(request,'ecom/index.html',{'products':products,'word':word,'product_count_in_cart':product_count_in_cart})


# any one can add product to cart, no need of signin
def add_to_cart_view(request,pk):
    product = get_object_or_404(models.Product, pk=pk)
    products=models.Product.objects.all()

    #for cart counter, fetching products ids added by customer from cookies
    if 'product_ids' in request.COOKIES:
        product_ids = request.COOKIES['product_ids']
        counter=product_ids.split('|')
        product_count_in_cart=len(set(counter))
    else:
        product_count_in_cart=1

    response = render(request, 'ecom/index.html',{'products':products,'product_count_in_cart':product_count_in_cart})

    #adding product id to cookies
    if 'product_ids' in request.COOKIES:
        product_ids = request.COOKIES['product_ids']
        if product_ids=="":
            product_ids=str(pk)
        else:
            product_ids=product_ids+"|"+str(pk)
        response.set_cookie('product_ids', product_ids)
    else:
        response.set_cookie('product_ids', pk)

    messages.info(request, product.name + ' added to cart successfully!')

    return response


def _cart_products(request):
    raw_ids = request.COOKIES.get('product_ids', '')
    product_ids = []
    for value in raw_ids.split('|'):
        if value.isdecimal() and int(value) not in product_ids:
            product_ids.append(int(value))
    return models.Product.objects.filter(id__in=product_ids)


# for checkout of cart
def cart_view(request):
    #for cart counter
    if 'product_ids' in request.COOKIES:
        product_ids = request.COOKIES['product_ids']
        counter=product_ids.split('|')
        product_count_in_cart=len(set(counter))
    else:
        product_count_in_cart=0

    products = _cart_products(request)
    total = sum(product.price for product in products)
    return render(request,'ecom/cart.html',{'products':products,'total':total,'product_count_in_cart':product_count_in_cart})


def remove_from_cart_view(request,pk):
    existing_ids = [
        value for value in request.COOKIES.get('product_ids', '').split('|')
        if value.isdecimal() and value != str(pk)
    ]
    response = redirect('cart')
    if existing_ids:
        response.set_cookie('product_ids', '|'.join(dict.fromkeys(existing_ids)))
    else:
        response.delete_cookie('product_ids')
    return response


def send_feedback_view(request):
    feedbackForm=forms.FeedbackForm()
    if request.method == 'POST':
        feedbackForm = forms.FeedbackForm(request.POST)
        if feedbackForm.is_valid():
            feedbackForm.save()
            return render(request, 'ecom/feedback_sent.html')
    return render(request, 'ecom/send_feedback.html', {'feedbackForm':feedbackForm})


@login_required(login_url='customerlogin')
@user_passes_test(is_customer)
def customer_home_view(request):
    products=models.Product.objects.all()
    if 'product_ids' in request.COOKIES:
        product_ids = request.COOKIES['product_ids']
        counter=product_ids.split('|')
        product_count_in_cart=len(set(counter))
    else:
        product_count_in_cart=0
    return render(request,'ecom/customer_home.html',{'products':products,'product_count_in_cart':product_count_in_cart})

# shipment address before placing order
@login_required(login_url='customerlogin')
@user_passes_test(is_customer)
def customer_address_view(request):
    products = list(_cart_products(request))
    product_in_cart = bool(products)
    product_count_in_cart = len(products)
    address_form = forms.AddressForm()
    if request.method == 'POST':
        address_form = forms.AddressForm(request.POST)
        if not products:
            address_form.add_error(None, 'Your cart is empty.')
        if address_form.is_valid():
            try:
                phone = normalize_kenyan_phone(address_form.cleaned_data['Mobile'])
            except ValueError as exc:
                address_form.add_error('Mobile', str(exc))
            else:
                customer = get_object_or_404(models.Customer, user=request.user)
                total = sum(product.price for product in products)
                if total < 1:
                    address_form.add_error(None, 'The cart total must be at least KES 1 to pay with M-Pesa.')
                    return render(
                        request,
                        'ecom/customer_address.html',
                        {
                            'addressForm': address_form,
                            'product_in_cart': product_in_cart,
                            'product_count_in_cart': product_count_in_cart,
                            'total': total,
                        },
                    )
                payment = PaymentTransaction.objects.create(
                    customer=customer,
                    products=[product.pk for product in products],
                    email=address_form.cleaned_data['Email'],
                    mobile=phone,
                    address=address_form.cleaned_data['Address'],
                    amount=total,
                )
                try:
                    result = initiate_stk_push(phone, total, f'ORDER-{payment.pk}')
                except (DarajaError, ImproperlyConfigured):
                    logger.exception('Daraja STK Push failed for payment %s', payment.pk)
                    payment.status = PaymentTransaction.STATUS_FAILED
                    payment.result_description = 'Could not start M-Pesa payment.'
                    payment.save(update_fields=['status', 'result_description', 'updated_at'])
                    messages.error(
                        request,
                        'We could not start your M-Pesa payment. Please check your details or try again later.',
                    )
                else:
                    payment.merchant_request_id = result.get('MerchantRequestID', '')
                    payment.checkout_request_id = result['CheckoutRequestID']
                    payment.result_description = result.get('CustomerMessage', 'Payment prompt sent to your phone.')
                    payment.save(
                        update_fields=[
                            'merchant_request_id',
                            'checkout_request_id',
                            'result_description',
                            'updated_at',
                        ],
                    )
                    return redirect('payment-status', transaction_id=payment.pk)

    return render(
        request,
        'ecom/customer_address.html',
        {
            'addressForm': address_form,
            'product_in_cart': product_in_cart,
            'product_count_in_cart': product_count_in_cart,
            'total': sum(product.price for product in products),
        },
    )


@csrf_exempt
@require_POST
def mpesa_callback_view(request):
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'ResultCode': 1, 'ResultDesc': 'Invalid JSON.'}, status=400)

    if not isinstance(payload, dict) or not isinstance(payload.get('Body'), dict):
        return JsonResponse({'ResultCode': 1, 'ResultDesc': 'Invalid callback payload.'}, status=400)
    callback = payload['Body'].get('stkCallback')
    if not isinstance(callback, dict):
        return JsonResponse({'ResultCode': 1, 'ResultDesc': 'Invalid callback payload.'}, status=400)
    checkout_id = callback.get('CheckoutRequestID')
    if not checkout_id:
        return JsonResponse({'ResultCode': 1, 'ResultDesc': 'Missing checkout request ID.'}, status=400)

    with transaction.atomic():
        payment = (
            PaymentTransaction.objects.select_for_update()
            .filter(checkout_request_id=checkout_id)
            .first()
        )
        if payment is None:
            return JsonResponse({'ResultCode': 1, 'ResultDesc': 'Payment not found.'}, status=404)

        if payment.status == PaymentTransaction.STATUS_PENDING:
            result_code = callback.get('ResultCode')
            result_description = callback.get('ResultDesc', '')[:255]
            callback_metadata = callback.get('CallbackMetadata')
            if not isinstance(callback_metadata, dict):
                callback_metadata = {}
            callback_items = callback_metadata.get('Item')
            if not isinstance(callback_items, list):
                callback_items = []
            metadata = {
                item.get('Name'): item.get('Value')
                for item in callback_items
                if isinstance(item, dict) and item.get('Name')
            }
            try:
                paid_amount = int(metadata.get('Amount'))
                paid_phone = normalize_kenyan_phone(str(metadata.get('PhoneNumber', '')))
            except (TypeError, ValueError):
                paid_amount = None
                paid_phone = None

            if (
                str(result_code) == '0'
                and paid_amount == payment.amount
                and paid_phone == payment.mobile
            ):
                product_map = {
                    product.pk: product
                    for product in models.Product.objects.filter(pk__in=payment.products)
                }
                if len(product_map) == len(payment.products):
                    models.Orders.objects.bulk_create(
                        [
                            models.Orders(
                                customer=payment.customer,
                                product=product_map[product_id],
                                email=payment.email,
                                mobile=payment.mobile,
                                address=payment.address,
                                status='Pending',
                                payment=payment,
                            )
                            for product_id in payment.products
                        ]
                    )
                    payment.status = PaymentTransaction.STATUS_COMPLETED
                    payment.mpesa_receipt_number = str(metadata.get('MpesaReceiptNumber', ''))[:50]
                    payment.result_description = result_description or 'Payment confirmed.'
                else:
                    payment.status = PaymentTransaction.STATUS_FAILED
                    payment.result_description = 'A product in the order is no longer available.'
            else:
                payment.status = PaymentTransaction.STATUS_FAILED
                payment.result_description = (
                    result_description or 'Payment details did not match the order.'
                )[:255]
            payment.save(
                update_fields=[
                    'status',
                    'mpesa_receipt_number',
                    'result_description',
                    'updated_at',
                ],
            )

    return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Accepted'})


@login_required(login_url='customerlogin')
@user_passes_test(is_customer)
def payment_status_view(request, transaction_id):
    payment = get_object_or_404(
        PaymentTransaction,
        pk=transaction_id,
        customer__user=request.user,
    )
    response = render(request, 'ecom/payment_status.html', {'payment': payment})
    if payment.status == PaymentTransaction.STATUS_COMPLETED:
        response.delete_cookie('product_ids')
    return response




@login_required(login_url='customerlogin')
@user_passes_test(is_customer)
def my_order_view(request):
    customer = get_object_or_404(models.Customer, user=request.user)
    orders = models.Orders.objects.filter(customer=customer).select_related('product').order_by('-order_date')
    return render(request, 'ecom/my_order.html', {'orders': orders})
 



# @login_required(login_url='customerlogin')
# @user_passes_test(is_customer)
# def my_order_view2(request):

#     products=models.Product.objects.all()
#     if 'product_ids' in request.COOKIES:
#         product_ids = request.COOKIES['product_ids']
#         counter=product_ids.split('|')
#         product_count_in_cart=len(set(counter))
#     else:
#         product_count_in_cart=0
#     return render(request,'ecom/my_order.html',{'products':products,'product_count_in_cart':product_count_in_cart})    



#--------------for discharge patient bill (pdf) download and printing
"""import io
from xhtml2pdf import pisa
from django.template.loader import get_template
from django.template import Context
from django.http import HttpResponse


def render_to_pdf(template_src, context_dict):
    template = get_template(template_src)
    html  = template.render(context_dict)
    result = io.BytesIO()
    pdf = pisa.pisaDocument(io.BytesIO(html.encode("ISO-8859-1")), result)
    if not pdf.err:
        return HttpResponse(result.getvalue(), content_type='application/pdf')
    return

@login_required(login_url='customerlogin')
@user_passes_test(is_customer)
def download_invoice_view(request,orderID,productID):
    order=models.Orders.objects.get(id=orderID)
    product=models.Product.objects.get(id=productID)
    mydict={
        'orderDate':order.order_date,
        'customerName':request.user,
        'customerEmail':order.email,
        'customerMobile':order.mobile,
        'shipmentAddress':order.address,
        'orderStatus':order.status,

        'productName':product.name,
        'productImage':product.product_image,
        'productPrice':product.price,
        'productDescription':product.description,


    }
    return render_to_pdf('ecom/download_invoice.html',mydict)"""

@login_required(login_url='customerlogin')
@user_passes_test(is_customer)
def my_profile_view(request):
    customer = get_object_or_404(models.Customer, user=request.user)
    return render(request, 'ecom/my_profile.html', {'customer': customer})


@login_required(login_url='customerlogin')
@user_passes_test(is_customer)
def edit_profile_view(request):
    customer=models.Customer.objects.get(user_id=request.user.id)
    user=models.User.objects.get(id=customer.user_id)
    userForm=forms.CustomerUserForm(instance=user)
    customerForm=forms.CustomerForm(request.FILES,instance=customer)
    mydict={'userForm':userForm,'customerForm':customerForm}
    if request.method=='POST':
        userForm=forms.CustomerUserForm(request.POST,instance=user)
        customerForm=forms.CustomerForm(request.POST,instance=customer)
        if userForm.is_valid() and customerForm.is_valid():
            user=userForm.save()
            user.set_password(user.password)
            user.save()
            customerForm.save()
            return HttpResponseRedirect('my-profile')
    return render(request,'ecom/edit_profile.html',context=mydict)



#---------------------------------------------------------------------------------
#------------------------ ABOUT US AND CONTACT US VIEWS START --------------------
#---------------------------------------------------------------------------------
def aboutus_view(request):
    return render(request, 'ecom/about Us.html')

def contactus_view(request):
    sub = forms.ContactusForm()
    if request.method == 'POST':
        sub = forms.ContactusForm(request.POST)
        if sub.is_valid():
            email = sub.cleaned_data['Email']
            name=sub.cleaned_data['Name']
            message = sub.cleaned_data['Message']
            send_mail(str(name)+' || '+str(email),message, settings.EMAIL_HOST_USER, settings.EMAIL_RECEIVING_USER, fail_silently = False)
            return render(request, 'ecom/contactussuccess.html')
    return render(request, 'ecom/contactus.html', {'form':sub})
