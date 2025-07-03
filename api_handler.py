import os
import random
import string
from supabase import create_client, Client
import requests

class SupabaseHandler:
    def __init__(self):
        # Initialize Supabase client from environment variables
        url: str = os.environ.get("SUPABASE_URL")
        key: str = os.environ.get("SUPABASE_KEY")
        self.client: Client = create_client(url, key)

    def get_user_by_phone(self, phone_number: str):
        """Fetches a user's record from the database by their phone number."""
        try:
            response = self.client.table('userdetails').select('*').eq('client', phone_number).single().execute()
            return response.data
        except Exception as e:
            if "JSONDecodeError" in str(e):
                 return None
            print(f"Error fetching user {phone_number}: {e}")
            return None

    def create_user(self, data: dict):
        """Creates a new user record."""
        try:
            response = self.client.table('userdetails').insert(data).execute()
            return response.data
        except Exception as e:
            print(f"Error creating user: {e}")
            return None

    def update_user(self, phone_number: str, data: dict):
        """Updates a user's record."""
        try:
            response = self.client.table('userdetails').update(data).eq('client', phone_number).execute()
            return response.data
        except Exception as e:
            print(f"Error updating user {phone_number}: {e}")
            return None

    def get_token_by_value(self, token_value: str):
        """Fetches a token's details from the 'tokens' table by its value."""
        try:
            response = self.client.table('tokens').select('*').eq('token_value', token_value).single().execute()
            return response.data
        except Exception as e:
            if "JSONDecodeError" in str(e):
                return None
            print(f"Error fetching token {token_value}: {e}")
            return None

    def update_token_status(self, token_value: str, new_status: str):
        """Updates the status of a token in the 'tokens' table."""
        try:
            response = self.client.table('tokens').update({'status': new_status}).eq('token_value', token_value).execute()
            return response.data
        except Exception as e:
            print(f"Error updating token {token_value}: {e}")
            return None
            
    def create_plaschema_record(self, record_data: dict):
        """Creates a new record in the plaschema table."""
        try:
            response = self.client.table('plaschema').insert(record_data).execute()
            return response.data
        except Exception as e:
            print(f"Error creating PLASCHEMA record: {e}")
            return None


class SafeHavenAPI:
    def __init__(self, db_handler: SupabaseHandler):
        self.db = db_handler
        self.access_token = self._get_access_token() # Fetch token on init
        self.client_id = os.environ.get("SAFEHAVEN_CLIENT_ID")
        self.base_url = "https://api.safehavenmfb.com"

        if not self.access_token:
            raise Exception("Could not retrieve SAFEHAVEN_ACCESS_TOKEN from Supabase.")

    def _get_access_token(self) -> str | None:
        """Fetches the latest access token from the oauth_tokens table."""
        try:
            response = self.db.client.table('oauth_tokens').select('access_token').eq('id', 'access_token').single().execute()
            if response.data and response.data.get('access_token'):
                print("Successfully fetched access token from database.")
                return response.data.get('access_token')
            print("Access token not found in database.")
            return None
        except Exception as e:
            print(f"Error fetching access token from Supabase: {e}")
            return None

    def _make_request(self, method, endpoint, payload=None):
        """Helper function to make API requests with robust error handling."""
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json',
            'ClientID': self.client_id
        }
        
        try:
            url = f"{self.base_url}{endpoint}"
            timeout_seconds = 60

            print("\n--- SENDING API REQUEST TO SAFEHAVEN ---")
            print(f"ENDPOINT: {method} {url}")
            if payload:
                print(f"PAYLOAD: {payload}")
            print("----------------------------------------")

            if method.upper() == 'POST':
                response = requests.post(url, headers=headers, json=payload, timeout=timeout_seconds)
            else: # GET
                response = requests.get(url, headers=headers, timeout=timeout_seconds)
            
            response.raise_for_status()
            
            response_data = response.json()
            
            if response_data.get('statusCode') != 200:
                print("\n--- RECEIVED API APPLICATION ERROR ---")
                print(response_data)
                print("------------------------------------")
                return {'status': 'error', 'message': response_data.get('message', 'Unknown API error.')}

            print("\n--- RECEIVED API SUCCESS RESPONSE ---")
            print(response_data)
            print("-----------------------------------")
            return {'status': 'success', 'data': response_data}

        except requests.exceptions.RequestException as e:
            error_body = e.response.text if e.response else str(e)
            print("\n--- RECEIVED HTTP/NETWORK ERROR ---")
            print(f"ERROR: {error_body}")
            print("---------------------------------")
            return {'status': 'error', 'message': 'A network error occurred.'}

    def initiate_id_verification(self, id_type: str, id_number: str):
        endpoint = "/identity/v2"
        payload = { "type": id_type, "async": True, "number": id_number, "debitAccountNumber": "0118816902" }
        return self._make_request('POST', endpoint, payload)

    def validate_verification(self, identity_id: str, otp: str, id_type: str):
        endpoint = "/identity/v2/validate"
        payload = { "type": id_type, "identityId": identity_id, "otp": otp }
        return self._make_request('POST', endpoint, payload)

    def create_sub_account(self, identity_id: str, phone_number: str):
        def generate_random_email(phone):
            return f"{phone}{random.randint(100,999)}@iyapay.com"
        
        def generate_external_ref():
            return ''.join(random.choices(string.ascii_uppercase, k=4))

        endpoint = "/accounts/v2/subaccount"
        payload = {
            "phoneNumber": phone_number, "emailAddress": generate_random_email(phone_number),
            "identityType": "vID", "autoSweep": False, "autoSweepDetails": {"schedule": "Instant"},
            "externalReference": generate_external_ref(), "identityId": identity_id
        }
        return self._make_request('POST', endpoint, payload)

    def name_enquiry(self, bank_code: str, account_number: str):
        endpoint = "/transfers/name-enquiry"
        payload = { "bankCode": bank_code, "accountNumber": account_number }
        return self._make_request('POST', endpoint, payload)

    def initiate_transfer(self, name_enquiry_reference: str, debit_account_number: str, beneficiary_bank_code: str, beneficiary_account_number: str, amount: int):
        def generate_random_string(length):
            return ''.join(random.choices(string.ascii_uppercase, k=length))

        endpoint = "/transfers"
        payload = {
            "saveBeneficiary": False, "nameEnquiryReference": name_enquiry_reference,
            "debitAccountNumber": debit_account_number, "beneficiaryBankCode": beneficiary_bank_code,
            "beneficiaryAccountNumber": beneficiary_account_number, "amount": amount,
            "narration": generate_random_string(4), "paymentReference": generate_random_string(4)
        }
        return self._make_request('POST', endpoint, payload)

    def buy_airtime(self, amount: int, debit_account_number: str, phone_number: str, service_category_id: str):
        endpoint = "/vas/pay/airtime"
        payload = {
            "amount": amount, "channel": "WEB", "debitAccountNumber": debit_account_number,
            "phoneNumber": phone_number, "serviceCategoryId": service_category_id
        }
        return self._make_request('POST', endpoint, payload)

    def create_virtual_account(self, user_account_number: str, amount: int):
        endpoint = "/virtual-accounts"
        payload = {
            "validFor": 72000,
            "settlementAccount": {
                "bankCode": "090286",
                "accountNumber": "0118816902"
            },
            "amountControl": "Fixed",
            "amount": amount,
            "externalReference": str(random.randint(1000, 9999)),
            "callbackUrl": "https://www.iyapays.com"
        }
        return self._make_request('POST', endpoint, payload)
