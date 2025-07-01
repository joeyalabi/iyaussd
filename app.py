from flask import Flask, request
from dotenv import load_dotenv
from api_handler import SafeHavenAPI, SupabaseHandler
import os
import logging
from datetime import datetime, timedelta

# Load environment variables from .env file
load_dotenv()

# --- Setup Enhanced Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Data Lists ---
BANKS = [
    {'name': 'Access Bank', 'bank_code': '000014'}, {'name': 'Zenith Bank', 'bank_code': '000015'},
    {'name': 'UBA', 'bank_code': '000004'}, {'name': 'First Bank of Nigeria', 'bank_code': '000016'},
    {'name': 'GTBank', 'bank_code': '000013'}, {'name': 'Ecobank Nigeria', 'bank_code': '000010'},
    {'name': 'Union Bank of Nigeria', 'bank_code': '000018'}, {'name': 'Fidelity Bank', 'bank_code': '000007'},
    {'name': 'Sterling Bank', 'bank_code': '000001'}, {'name': 'Wema Bank', 'bank_code': '000017'},
    {'name': 'Stanbic IBTC Bank', 'bank_code': '000012'}, {'name': 'FCMB', 'bank_code': '000003'},
    {'name': 'Kuda Bank', 'bank_code': '090267'}, {'name': 'Opay', 'bank_code': '090175'},
    {'name': 'Palmpay', 'bank_code': '090176'}, {'name': 'Moniepoint', 'bank_code': '090405'},
    {'name': 'Globus Bank', 'bank_code': '000027'}, {'name': 'Polaris Bank', 'bank_code': '000008'},
    {'name': 'Keystone Bank', 'bank_code': '000002'}, {'name': 'Heritage Bank', 'bank_code': '000020'},
    {'name': 'Titan Trust Bank', 'bank_code': '000025'}, {'name': 'Unity Bank', 'bank_code': '000011'},
    {'name': 'Providus Bank', 'bank_code': '000023'}, {'name': 'Jaiz Bank', 'bank_code': '000006'},
    {'name': 'Taj Bank', 'bank_code': '000026'}
]
NETWORKS = [
    {'name': 'MTN', 'serviceCategoryId': '61efacbcda92348f9dde5f92'},
    {'name': 'GLO', 'serviceCategoryId': '61efacc8da92348f9dde5f95'},
    {'name': 'Airtel', 'serviceCategoryId': '61efacd3da92348f9dde5f98'},
    {'name': '9mobile', 'serviceCategoryId': '61efacdeda92348f9dde5f9b'}
]
ERROR_MESSAGES = {
    'invalid_account': "CON Invalid account number. Please enter a 10-digit account number:",
    'invalid_phone': "CON Invalid phone number format. Enter 11-digit number (e.g., 08123456789):",
    'invalid_amount': "CON Invalid amount. Enter amount between NGN 100 and NGN 1,000,000:",
    'api_error': "END Service temporarily unavailable. Please try again later.",
    'timeout': "END Session expired. Please dial the code again to continue."
}

# Initialize the Flask app
app = Flask(__name__)

# --- Helper Functions ---

def get_bank_list_page(page_number, banks_per_page=4):
    """(FIXED) Helper function to create a paginated list of banks."""
    start_index = (page_number - 1) * banks_per_page
    end_index = min(start_index + banks_per_page, len(BANKS))
    page_banks = BANKS[start_index:end_index]

    response = "CON Select beneficiary bank:\n"
    # Use relative indexing for the current page
    for i, bank in enumerate(page_banks):
        response += f"{i + 1}. {bank['name']}\n"
    
    nav_options = []
    if end_index < len(BANKS):
        nav_options.append("0. Next")
    if page_number > 1:
        nav_options.append("9. Previous")
    
    if nav_options:
        response += "\n".join(nav_options)
        
    return response

def validate_amount(amount_str, min_amount=100, max_amount=1000000):
    """(ADDED) Comprehensive amount validation."""
    try:
        amount = int(amount_str)
        if amount < min_amount:
            return False, f"Minimum amount is NGN {min_amount}"
        if amount > max_amount:
            return False, f"Maximum amount is NGN {max_amount:,}"
        return True, amount
    except ValueError:
        return False, "Please enter a valid number"

def check_transaction_timeout(user, timeout_minutes=5):
    """(ADDED) Checks if the user's session has timed out."""
    if not user or not user.get('last_activity'):
        return False
    last_activity_str = user.get('last_activity')
    try:
        # Ensure the string is in the correct format for fromisoformat
        last_time = datetime.fromisoformat(last_activity_str)
        if datetime.utcnow() - last_time > timedelta(minutes=timeout_minutes):
            return True
    except (ValueError, TypeError):
        # Handle cases with invalid timestamp format
        return False
    return False

@app.route("/callback", methods=['POST'])
def ussd_callback():
    logger.info(f"--- INCOMING USSD RAW DATA ---\n{request.form}")

    db = SupabaseHandler()
    try:
        api = SafeHavenAPI(db)
    except Exception as e:
        logger.critical(f"CRITICAL: Failed to initialize SafeHavenAPI. Error: {e}")
        return "END Service is temporarily unavailable. Please try again later."

    session_id = request.form.get("sessionId")
    phone_number = request.form.get("phoneNumber")
    text = request.form.get("text", "")

    user = db.get_user_by_phone(phone_number)
    text_parts = text.split('*')
    
    # (FIXED) Correct level calculation
    level = len(text_parts) if text else 0

    logger.info(f"--- PARSED REQUEST ---\nPhone: {phone_number}, Text: '{text}', Level: {level}, Session: {session_id}")
    if user:
        logger.info(f"User found. State: {user.get('transfer_flow_state') or user.get('airtime_flow_state') or 'None'}")
    else:
        logger.info("No user found in DB for this phone number.")

    response = ""

    # (ADDED) Session Timeout Check
    if user and check_transaction_timeout(user):
        logger.warning(f"User {phone_number} session timed out.")
        # Clear all states on timeout
        db.update_user(phone_number, {
            'transfer_flow_state': None, 'airtime_flow_state': None, 'voucher_flow_state': None, 'iyafix_flow_state': None,
            'last_activity': None
        })
        return ERROR_MESSAGES['timeout']

    # Update last activity timestamp for active users
    if user:
        db.update_user(phone_number, {'last_activity': datetime.utcnow().isoformat()})

    # ======================================================
    # ===== RETURNING USER FLOW =====
    # ======================================================
    if user and user.get('accountNumber'):
        account_name = user.get('accountName', phone_number)
        
        if text == "":
            # (FIXED) Comprehensive state cleanup when returning to the main menu
            logger.info(f"User {phone_number} returning to main menu. Clearing all session states.")
            db.update_user(phone_number, {
                'transfer_flow_state': None, 'transfer_recipient_account': None,
                'transfer_recipient_bank_code': None, 'transfer_session_id': None,
                'transfer_page': None, 'airtime_flow_state': None,
                'airtime_service_id': None, 'airtime_recipient_number': None,
                'voucher_flow_state': None, 'iyafix_flow_state': None,
                'iyafix_plan_name': None, 'iyafix_duration': None, 'iyafix_amount': None,
                'last_activity': datetime.utcnow().isoformat() # Also reset activity timer
            })
            response  = f"CON Welcome back, {account_name}.\n1. Add Funds\n2. Transfer Funds\n3. Buy Airtime\n4. IyaVoucher\n5. IyaFix\n9. My Account"
        
        else:
            choice = text_parts[0]
            # (FIXED) Standardize to always use the last part of the input string for the user's most recent action
            user_input = text_parts[-1]
            logger.info(f"--- EVALUATING MENU CHOICE ---: Choice: '{choice}', User Input: '{user_input}'")

            if choice == "2": # Transfer Funds
                flow_state = user.get('transfer_flow_state')

                if flow_state is None:
                    db.update_user(phone_number, {'transfer_flow_state': 'AWAITING_RECIPIENT_ACCOUNT'})
                    response = "CON Enter beneficiary account number:"

                elif flow_state == 'AWAITING_RECIPIENT_ACCOUNT':
                    if len(user_input) == 10 and user_input.isdigit():
                        db.update_user(phone_number, {
                            'transfer_recipient_account': user_input, 
                            'transfer_page': 1,
                            'transfer_flow_state': 'AWAITING_BANK_SELECTION'
                        })
                        response = get_bank_list_page(1)
                    else:
                        response = ERROR_MESSAGES['invalid_account']

                elif flow_state == 'AWAITING_BANK_SELECTION':
                    current_page = user.get('transfer_page', 1)
                    
                    if user_input == '0': # Next
                        new_page = current_page + 1
                        total_pages = (len(BANKS) + 3) // 4
                        if new_page <= total_pages:
                            db.update_user(phone_number, {'transfer_page': new_page})
                        response = get_bank_list_page(new_page if new_page <= total_pages else current_page)
                    elif user_input == '9': # Previous
                        new_page = max(1, current_page - 1)
                        db.update_user(phone_number, {'transfer_page': new_page})
                        response = get_bank_list_page(new_page)
                    elif user_input.isdigit():
                        # (FIXED) Corrected bank selection logic for pagination
                        banks_per_page = 4
                        start_index = (current_page - 1) * banks_per_page
                        global_index = start_index + int(user_input) - 1

                        if 1 <= int(user_input) <= banks_per_page and global_index < len(BANKS):
                            selected_bank = BANKS[global_index]
                            bank_code = selected_bank['bank_code']
                            recipient_account = user.get('transfer_recipient_account')
                            
                            db.update_user(phone_number, {'transfer_recipient_bank_code': bank_code})
                            
                            # (FIXED) Improved API response handling
                            name_enquiry_result = api.name_enquiry(bank_code, recipient_account)
                            if name_enquiry_result.get('status') == 'success':
                                response_data = name_enquiry_result.get('data', {})
                                enquiry_data = response_data.get('data', {}) if isinstance(response_data, dict) else {}
                                account_name = enquiry_data.get('accountName')
                                session_id_from_api = enquiry_data.get('sessionId')
                                
                                if account_name and session_id_from_api:
                                    db.update_user(phone_number, {'transfer_session_id': session_id_from_api, 'transfer_flow_state': 'AWAITING_AMOUNT'})
                                    response = f"CON Beneficiary: {account_name}\nEnter amount:"
                                else:
                                    response = "END Account verification failed. Please check details."
                            else:
                                response = "END Could not verify account details. Please try again."
                        else:
                            response = "CON Invalid selection. Please try again."
                    else:
                        response = "CON Invalid input. Please try again."
                
                elif flow_state == 'AWAITING_AMOUNT':
                    is_valid, result = validate_amount(user_input)
                    if is_valid:
                        amount = result
                        transfer_result = api.initiate_transfer(
                            name_enquiry_reference=user.get('transfer_session_id'),
                            debit_account_number=user.get('accountNumber'),
                            beneficiary_bank_code=user.get('transfer_recipient_bank_code'),
                            beneficiary_account_number=user.get('transfer_recipient_account'),
                            amount=amount
                        )
                        if transfer_result and transfer_result.get('status') == 'success':
                            db.update_user(phone_number, {'transfer_flow_state': None, 'transfer_page': None}) # Clear flow
                            response = "END Transaction Successful."
                        else:
                            response = "END Transaction Failed. Please try again."
                    else:
                        response = f"CON {result}. Please enter a valid amount:" # Show detailed error

            elif choice == "3": # Buy Airtime
                flow_state = user.get('airtime_flow_state')

                if flow_state is None:
                    db.update_user(phone_number, {'airtime_flow_state': 'AWAITING_NETWORK'})
                    response = "CON Select Network:\n1. MTN\n2. GLO\n3. Airtel\n4. 9mobile"
                
                elif flow_state == 'AWAITING_NETWORK':
                    if user_input.isdigit() and 1 <= int(user_input) <= len(NETWORKS):
                        selected_network = NETWORKS[int(user_input) - 1]
                        db.update_user(phone_number, {
                            'airtime_service_id': selected_network['serviceCategoryId'],
                            'airtime_flow_state': 'AWAITING_RECIPIENT_CHOICE'
                        })
                        response = "CON Select recipient:\n1. Myself\n2. Others"
                    else:
                        response = "CON Invalid network selection. Please try again."

                elif flow_state == 'AWAITING_RECIPIENT_CHOICE':
                    if user_input == '1': # Myself
                        db.update_user(phone_number, {
                            'airtime_recipient_number': phone_number,
                            'airtime_flow_state': 'AWAITING_AMOUNT'
                        })
                        response = "CON Enter amount:"
                    elif user_input == '2': # Others
                        db.update_user(phone_number, {'airtime_flow_state': 'AWAITING_RECIPIENT_NUMBER'})
                        response = "CON Enter recipient phone number:"
                    else:
                        response = "CON Invalid selection. Please try again."

                elif flow_state == 'AWAITING_RECIPIENT_NUMBER':
                    # (FIXED) Added phone number validation and normalization
                    recipient_number = user_input
                    if recipient_number.startswith('0') and len(recipient_number) == 11:
                        recipient_number = '234' + recipient_number[1:]
                    elif recipient_number.startswith('+234') and len(recipient_number) == 14:
                         recipient_number = '234' + recipient_number[4:]
                    
                    if len(recipient_number) == 13 and recipient_number.isdigit():
                        db.update_user(phone_number, {
                            'airtime_recipient_number': recipient_number,
                            'airtime_flow_state': 'AWAITING_AMOUNT'
                        })
                        response = "CON Enter amount:"
                    else:
                        response = ERROR_MESSAGES['invalid_phone']

                elif flow_state == 'AWAITING_AMOUNT':
                    is_valid, result = validate_amount(user_input, min_amount=50, max_amount=50000)
                    if is_valid:
                        amount = result
                        airtime_result = api.buy_airtime(
                            amount=amount, 
                            debit_account_number=user.get('accountNumber'), 
                            phone_number=user.get('airtime_recipient_number'), 
                            service_category_id=user.get('airtime_service_id')
                        )
                        if airtime_result and airtime_result.get('status') == 'success':
                            db.update_user(phone_number, {'airtime_flow_state': None}) # Clear flow
                            response = f"END Airtime purchase of NGN {amount} for {user.get('airtime_recipient_number')} was successful."
                        else:
                            response = "END Airtime purchase failed."
                    else:
                        response = f"CON {result}. Please enter a valid amount:" # Show detailed error

            elif choice == "5": # IyaFix
                flow_state = user.get('iyafix_flow_state')

                if flow_state is None:
                    db.update_user(phone_number, {'iyafix_flow_state': 'AWAITING_PLAN_NAME'})
                    response = "CON Enter a name for your IyaFix plan:"

                elif flow_state == 'AWAITING_PLAN_NAME':
                    plan_name = user_input
                    db.update_user(phone_number, {
                        'iyafix_plan_name': plan_name,
                        'iyafix_flow_state': 'AWAITING_DURATION'
                    })
                    response = "CON Select duration:\n1. 30 Days\n2. 60 Days\n3. 90 Days\n4. 6 Months"

                elif flow_state == 'AWAITING_DURATION':
                    durations = {"1": "30 Days", "2": "60 Days", "3": "90 Days", "4": "6 Months"}
                    if user_input in durations:
                        db.update_user(phone_number, {
                            'iyafix_duration': durations[user_input],
                            'iyafix_flow_state': 'AWAITING_AMOUNT'
                        })
                        response = "CON Enter amount to fix:"
                    else:
                        response = "CON Invalid duration selected. Please try again."

                elif flow_state == 'AWAITING_AMOUNT':
                    # (FIXED) Improved IyaFix state persistence and validation
                    is_valid, result = validate_amount(user_input, min_amount=5000)
                    if is_valid:
                        amount = result
                        fix_result = api.create_virtual_account(user.get('accountNumber'), amount)
                        
                        if fix_result and fix_result.get('status') == 'success':
                            plan_name = user.get('iyafix_plan_name')
                            duration = user.get('iyafix_duration')
                            db.update_user(phone_number, {
                                'iyafix_flow_state': None, # End the flow
                                'iyafix_amount': float(amount),
                                'iyafix_plan_name': plan_name,
                                'iyafix_duration': duration,
                                'iyafix_created_at': datetime.utcnow().isoformat()
                            })
                            response = f"END Your '{plan_name}' IyaFix of NGN {amount:,} for {duration} is successful."
                        else:
                            response = "END Could not create your IyaFix plan at this time."
                    else:
                        response = f"CON {result}. Please enter a valid amount:"

            elif choice == "9": # My Account
                acc_num = user.get('accountNumber')
                acc_name = user.get('accountName')
                balance = float(user.get('accountBalance', 0))
                response = f"END Your Account:\nName: {acc_name}\nNumber: {acc_num}\nBalance: NGN {balance:,.2f}"
            else:
                response = "END Thank you for using IyaPays. This feature is coming soon."
        
        logger.info(f"--- SENDING USSD RESPONSE ---\n{response}")
        return response

    # ======================================================
    # ===== NEW USER REGISTRATION FLOW =====
    # ======================================================
    if level == 0:
        initial_data = {
            'client': phone_number, 'id_type': None, 'bvn': None, 'identityId': None, 
            '_id': None, 'status': 'PENDING_ID_TYPE', 'last_activity': datetime.utcnow().isoformat()
        }
        db.create_user(initial_data) if not user else db.update_user(phone_number, initial_data)
        response = "CON Welcome to IyaPays.\nPlease choose your ID type:\n1. BVN\n2. NIN"

    elif level == 1:
        id_choice = text_parts[0]
        id_type = "BVN" if id_choice == "1" else "NIN" if id_choice == "2" else None
        if id_type:
            db.update_user(phone_number, {'id_type': id_type, 'status': 'PENDING_ID_NUMBER'})
            response = f"CON Please enter your 11-digit {id_type}:"
        else:
            response = "END Invalid choice. Please start over."

    elif level == 2 and user and user.get('id_type'):
        id_type = user.get('id_type')
        id_number = text_parts[1]
        if len(id_number) == 11 and id_number.isdigit():
            db.update_user(phone_number, {'bvn': id_number, 'status': 'PENDING_OTP'})
            init_result = api.initiate_id_verification(id_type, id_number)
            if init_result.get('status') == 'success':
                nested_data = init_result.get('data', {}).get('data', {})
                identity_id = nested_data.get('_id')
                if identity_id:
                    db.update_user(phone_number, {'identityId': identity_id})
                    response = "CON An OTP has been sent. Please enter it to continue:"
                else:
                    response = f"END Verification failed. Could not get a verification ID."
            else:
                response = f"END Your {id_type} could not be verified. Please check and try again."
        else:
            response = f"END Invalid {id_type}. It must be 11 digits."

    elif level == 3 and user and user.get('identityId'):
        otp = text_parts[2]
        if len(otp) >= 4 and otp.isdigit():
            validate_result = api.validate_verification(user.get('identityId'), otp, user.get('id_type'))
            if validate_result.get('status') == 'success':
                db.update_user(phone_number, {'status': 'PENDING_ACCOUNT_CREATION'})
                response = "CON OTP Validated successfully! Press 1 to create your account."
            else:
                response = "END The OTP you entered is incorrect. Please dial the code to try again."
        else:
            response = "END Invalid OTP format. Please try again."

    elif level == 4 and user and user.get('identityId'):
        account_result = api.create_sub_account(user.get('identityId'), phone_number)
        if account_result.get('status') == 'success':
            account_data = account_result.get('data', {})
            # (FIXED) Ensure correct data types for database update
            update_data = {
                '_id': account_data.get('_id'),
                'accountNumber': account_data.get('accountNumber'),
                'accountName': account_data.get('accountName'),
                'accountBalance': float(account_data.get('accountBalance', 0)),
                'external_reference': account_data.get('externalReference'),
                'status': 'COMPLETED'
            }
            db.update_user(phone_number, update_data)
            response = f"END Congratulations! Your account is ready.\nName: {update_data['accountName']}\nNumber: {update_data['accountNumber']}\nBalance: NGN {update_data['accountBalance']:,.2f}"
        else:
            response = "END We could not create your account at this time. Please try again later."
    else:
        response = "END An error occurred or your session has expired. Please dial the code to start again."

    logger.info(f"--- SENDING USSD RESPONSE ---\n{response}")
    return response

if __name__ == "__main__":
    app.run(debug=True, port=os.environ.get("PORT", 5000))
