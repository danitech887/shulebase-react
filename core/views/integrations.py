import requests
from requests.auth import HTTPBasicAuth

def get_access_token():
    consumer_key = "DoHCYtbUn40mMsLl1GylZglxljdDon33usSAzniNrloxo6XA"
    consumer_secret = "o15oHyqORYhtUBQKCHdxVgTtmp2Pf47C0Vdhdof6xNevCqZqPNh3oevCWkc5a9qu"
    api_URL = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    
    r = requests.get(api_URL, auth=HTTPBasicAuth(consumer_key, consumer_secret))
    return r.json()['access_token']


import base64
from datetime import datetime

def initiate_stk_push(phone_number, amount):
    access_token = get_access_token()
    url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
    
    business_short_code = "174379"
    passkey = "bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919"
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    
    # Generate Password
    data_to_encode = business_short_code + passkey + timestamp
    password = base64.b64encode(data_to_encode.encode()).decode('utf-8')
    
    headers = {"Authorization": f"Bearer {access_token}"}
    
    payload = {    
        "BusinessShortCode": business_short_code,    
        "Password": password,    
        "Timestamp": timestamp,    
        "TransactionType": "CustomerPayBillOnline",    
        "Amount": amount,    
        "PartyA": phone_number, # Format: 2547XXXXXXXX    
        "PartyB": business_short_code,    
        "PhoneNumber": phone_number,    
        "CallBackURL": "https://dff0-197-248-231-201.ngrok-free.app",    
        "AccountReference": "ParentPortal",    
        "TransactionDesc": "School Fee Payment"
    }
    
    response = requests.post(url, json=payload, headers=headers)
    return response.json()



from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

from rest_framework.response import Response
from ..models import Fee



@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def mpesa_callback(request):
    stk_data = request.data
    # Log the data to your terminal so you can see the structure
    print("M-Pesa Callback Data:", stk_data)
    
    try:
        stk_callback = stk_data['Body']['stkCallback']
        result_code = stk_callback['ResultCode']
        checkout_id = stk_callback['CheckoutRequestID'] # <--- LINK THIS
        
        if result_code == 0:
            metadata = stk_callback['CallbackMetadata']['Item']
            
            # Helper to extract values safely
            def get_val(name):
                return next((item['Value'] for item in metadata if item['Name'] == name), None)

            amount = get_val('Amount')
            receipt = get_val('MpesaReceiptNumber')
            
            # UPDATE DATABASE
            from ...students.models import Fee
            Fee.objects.filter(checkout_id=checkout_id).update(
                status='Confirmed',
                transaction_code=receipt,
                amount=amount
            )
            print(f"Success! Receipt: {receipt}")
        else:
            # ResultCode 1032 is 'User Cancelled', etc.
            print(f"Transaction failed or cancelled. Code: {result_code}")

    except Exception as e:
        print(f"Error parsing callback: {str(e)}")
        
    # Safaricom expects this exact success response regardless of ResultCode
    return Response({"ResultCode": 0, "ResultDesc": "Accepted"})

    stk_data = request.data
    result_code = stk_data['Body']['stkCallback']['ResultCode']
    
    if result_code == 0:
        # Success! 
        callback_metadata = stk_data['Body']['stkCallback']['CallbackMetadata']['Item']
        
        # Extract values (M-Pesa sends them in a list of dicts)
        amount = next(item['Value'] for item in callback_metadata if item['Name'] == 'Amount')
        receipt = next(item['Value'] for item in callback_metadata if item['Name'] == 'MpesaReceiptNumber')
        phone = next(item['Value'] for item in callback_metadata if item['Name'] == 'PhoneNumber')
        
        # Logic: Find the student by phone or a CheckoutRequestID you saved earlier
        # Update your Fee model to 'Confirmed'
        print(f"Payment Received: {receipt} for {amount} KES")
        
    return Response({"ResultCode": 0, "ResultDesc": "Accepted"})