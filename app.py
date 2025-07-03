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
    {'name': 'Taj Bank', 'bank_code': '000026'}, {'name': 'SAFE HAVEN MFB', 'bank_code': '090286'},
    {'name': 'Access Bank', 'bank_code': '000014'}, {'name': 'Zenith Bank', 'bank_code': '000015'},
    {'name': 'UBA', 'bank_code': '000004'}, {'name': 'First Bank of Nigeria', 'bank_code': '000016'},
    {'name': 'GTBank', 'bank_code': '000013'}, {'name': 'Ecobank Nigeria', 'bank_code': '000010'},
    {'name': 'Union Bank of Nigeria', 'bank_code': '000018'}, {'name': 'Fidelity Bank', 'bank_code': '000007'},
    {'name': 'Sterling Bank', 'bank_code': '000001'}, {'name': 'Wema Bank', 'bank_code': '000017'},
    {'name': 'Stanbic IBTC Bank', 'bank_code': '000012'}, {'name': 'FCMB', 'bank_code': '000003'},
    {'name': 'Kuda Bank', 'bank_code': '090267'}, {'name': 'Opay', 'bank_code': '100004'},
    {'name': 'Palmpay', 'bank_code': '090176'}, {'name': 'Moniepoint', 'bank_code': '090405'},
    {'name': 'Globus Bank', 'bank_code': '000027'}, {'name': 'Polaris Bank', 'bank_code': '000008'},
    {'name': 'Keystone Bank', 'bank_code': '000002'}, {'name': 'Heritage Bank', 'bank_code': '000020'},
    {'name': 'Titan Trust Bank', 'bank_code': '000025'}, {'name': 'Unity Bank', 'bank_code': '000011'},
    {'name': 'Providus Bank', 'bank_code': '000023'}, {'name': 'Jaiz Bank', 'bank_code': '000006'}
 
]
NETWORKS = [
    {'name': 'MTN', 'serviceCategoryId': '61efacbcda92348f9dde5f92'},
    {'name': 'GLO', 'serviceCategoryId': '61efacc8da92348f9dde5f95'},
    {'name': 'Airtel', 'serviceCategoryId': '61efacd3da92348f9dde5f98'},
    {'name': '9mobile', 'serviceCategoryId': '61efacdeda92348f9dde5f9b'}
]
NIGERIAN_STATES = [
    "Abia", "Adamawa", "Akwa Ibom", "Anambra", "Bauchi", "Bayelsa", "Benue", "Borno",
    "Cross River", "Delta", "Ebonyi", "Edo", "Ekiti", "Enugu", "Gombe", "Imo",
    "Jigawa", "Kaduna", "Kano", "Katsina", "Kebbi", "Kogi", "Kwara", "Lagos",
    "Nasarawa", "Niger", "Ogun", "Ondo", "Osun", "Oyo", "Plateau", "Rivers",
    "Sokoto", "Taraba", "Yobe", "Zamfara", "FCT"
]

# Initialize the Flask app
app = Flask(__name__)

# --- Helper Functions ---

def get_paginated_list(items, page_number, items_per_page, title):
    """Generic helper function for paginated menus."""
    start_index = (page_number - 1) * items_per_page
    end_index = min(start_index + items_per_page, len(items))
    page_items = items[start_index:end_index]

    response = f"CON {title}:\n"
    for i, item in enumerate(page_items):
        display_name = item['name'] if isinstance(item, dict) else item
        response += f"{start_index + i + 1}. {display_name}\n"
    
    if end_index < len(items):
        response += "0. Next\n"
    if page_number > 1:
        response += "9. Previous"
        
    return response

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

    # Ensure phone number has a consistent format if needed, e.g., starts with '+'
    if phone_number and not phone_number.startswith('+'):
        phone_number = f"+{phone_number}"

    user = db.get_user_by_phone(phone_number)
    text_parts = text.split('*')
    level = len(text_parts) if text else 0

    logger.info(f"--- PARSED REQUEST ---\nPhone: {phone_number}, Text: '{text}', Level: {level}, Session: {session_id}")
    if user:
        logger.info(f"User found. Account Number: '{user.get('accountNumber')}'")
    else:
        logger.info("No user found in DB for this phone_number.")

    response = ""

    # ======================================================
    # ===== RETURNING USER FLOW =====
    # ======================================================
    if user and user.get('accountNumber'):
        account_name = user.get('accountName', phone_number)
        
        if text == "":
            # Clear any stale flow states at the beginning of a new session
            db.update_user(phone_number, {
                'transfer_flow_state': None, 'airtime_flow_state': None, 
                'voucher_flow_state': None, 'iyafix_flow_state': None,
                'health_form_state': None
            })
            response  = f"CON Welcome back, {account_name}.\n"
            response += "1. Transfer Funds\n"
            response += "2. Buy Airtime\n"
            response += "3. IyaVoucher\n"
            response += "4. IyaFix\n"
            response += "5. Health Insurance\n"
            response += "9. My Account"
        
        else:
            choice = text_parts[0]
            logger.info(f"--- EVALUATING MENU CHOICE ---: '{choice}'")

            if choice == "1": # Transfer Funds
                flow_state = user.get('transfer_flow_state')

                if flow_state is None:
                    update_result = db.update_user(phone_number, {'transfer_flow_state': 'AWAITING_RECIPIENT_ACCOUNT'})
                    if update_result:
                        response = "CON Enter beneficiary account number:"
                    else:
                        response = "END A database error occurred. Please contact support."

                elif flow_state == 'AWAITING_RECIPIENT_ACCOUNT':
                    recipient_account = text_parts[1]
                    if len(recipient_account) == 10 and recipient_account.isdigit():
                        db.update_user(phone_number, {
                            'transfer_recipient_account': recipient_account, 
                            'transfer_page': 1,
                            'transfer_flow_state': 'AWAITING_BANK_SELECTION'
                        })
                        response = get_paginated_list(BANKS, 1, 4, "Select Bank")
                    else:
                        response = "END Invalid account number. Please try again."

                elif flow_state == 'AWAITING_BANK_SELECTION':
                    user_input = text_parts[-1]
                    current_page = user.get('transfer_page', 1)
                    
                    if user_input == '0': # Next
                        new_page = current_page + 1
                        total_pages = (len(BANKS) + 3) // 4
                        if new_page <= total_pages:
                            db.update_user(phone_number, {'transfer_page': new_page})
                            response = get_paginated_list(BANKS, new_page, 4, "Select Bank")
                        else:
                            response = get_paginated_list(BANKS, current_page, 4, "Select Bank")

                    elif user_input == '9': # Previous
                        new_page = max(1, current_page - 1)
                        db.update_user(phone_number, {'transfer_page': new_page})
                        response = get_paginated_list(BANKS, new_page, 4, "Select Bank")

                    elif user_input.isdigit():
                        selection = int(user_input)
                        if 1 <= selection <= len(BANKS):
                            selected_bank = BANKS[selection - 1]
                            bank_code = selected_bank['bank_code']
                            recipient_account = user.get('transfer_recipient_account')
                            
                            name_enquiry_result = api.name_enquiry(bank_code, recipient_account)
                            if name_enquiry_result.get('status') == 'success':
                                enquiry_data = name_enquiry_result.get('data', {}).get('data', {})
                                account_name = enquiry_data.get('accountName')
                                session_id_from_api = enquiry_data.get('sessionId')
                                
                                if account_name and session_id_from_api:
                                    db.update_user(phone_number, {
                                        'transfer_recipient_bank_code': bank_code,
                                        'transfer_session_id': session_id_from_api,
                                        'transfer_flow_state': 'AWAITING_AMOUNT'
                                    })
                                    response = f"CON Beneficiary: {account_name}\nEnter amount:"
                                else:
                                    response = "END Could not verify account details."
                            else:
                                response = f"END {name_enquiry_result.get('message', 'Could not verify account details.')}"
                        else:
                            response = "CON Invalid selection. Please try again."
                    else:
                        response = "CON Invalid input. Please try again."
                
                elif flow_state == 'AWAITING_AMOUNT':
                    amount_input = text_parts[-1]
                    if amount_input.isdigit():
                        amount = int(amount_input)
                        transfer_result = api.initiate_transfer(
                            name_enquiry_reference=user.get('transfer_session_id'),
                            debit_account_number=user.get('accountNumber'),
                            beneficiary_bank_code=user.get('transfer_recipient_bank_code'),
                            beneficiary_account_number=user.get('transfer_recipient_account'),
                            amount=amount
                        )
                        if transfer_result and transfer_result.get('status') == 'success':
                            response = "END Transaction Successful."
                        else:
                            response = f"END Transaction Failed: {transfer_result.get('message', 'Unknown error')}"
                    else:
                        response = "CON Invalid amount. Please try again."

            elif choice == "2": # Buy Airtime
                flow_state = user.get('airtime_flow_state')

                if flow_state is None:
                    update_result = db.update_user(phone_number, {'airtime_flow_state': 'AWAITING_NETWORK'})
                    if update_result:
                        response = "CON Select Network:\n1. MTN\n2. GLO\n3. Airtel\n4. 9mobile"
                    else:
                        response = "END A database error occurred. Please contact support."

                elif flow_state == 'AWAITING_NETWORK':
                    network_choice = text_parts[1]
                    if network_choice.isdigit() and 1 <= int(network_choice) <= len(NETWORKS):
                        selected_network = NETWORKS[int(network_choice) - 1]
                        db.update_user(phone_number, {
                            'airtime_service_id': selected_network['serviceCategoryId'],
                            'airtime_flow_state': 'AWAITING_RECIPIENT_CHOICE'
                        })
                        response = "CON Select recipient:\n1. Myself\n2. Others"
                    else:
                        response = "CON Invalid network selection."

                elif flow_state == 'AWAITING_RECIPIENT_CHOICE':
                    recipient_choice = text_parts[2]
                    if recipient_choice == '1': # Myself
                        db.update_user(phone_number, {
                            'airtime_recipient_number': phone_number,
                            'airtime_flow_state': 'AWAITING_AMOUNT'
                        })
                        response = "CON Enter amount:"
                    elif recipient_choice == '2': # Others
                        db.update_user(phone_number, {'airtime_flow_state': 'AWAITING_RECIPIENT_NUMBER'})
                        response = "CON Enter recipient phone number:"
                    else:
                        response = "CON Invalid selection."

                elif flow_state == 'AWAITING_RECIPIENT_NUMBER':
                    recipient_number = text_parts[3]
                    if len(recipient_number) >= 11 and recipient_number.isdigit():
                        db.update_user(phone_number, {
                            'airtime_recipient_number': recipient_number,
                            'airtime_flow_state': 'AWAITING_AMOUNT'
                        })
                        response = "CON Enter amount:"
                    else:
                        response = "CON Invalid phone number."

                elif flow_state == 'AWAITING_AMOUNT':
                    amount_input = text_parts[-1]
                    if amount_input.isdigit():
                        amount = int(amount_input)
                        airtime_result = api.buy_airtime(
                            amount=amount, 
                            debit_account_number=user.get('accountNumber'), 
                            phone_number=user.get('airtime_recipient_number'), 
                            service_category_id=user.get('airtime_service_id')
                        )
                        if airtime_result and airtime_result.get('status') == 'success':
                            response = f"END Airtime purchase of NGN {amount} for {user.get('airtime_recipient_number')} was successful."
                        else:
                            response = "END Airtime purchase failed."
                    else:
                        response = "CON Invalid amount."

            elif choice == "3": # IyaVoucher
                flow_state = user.get('voucher_flow_state')

                if flow_state is None:
                    update_result = db.update_user(phone_number, {'voucher_flow_state': 'AWAITING_VOUCHER_CODE'})
                    if update_result:
                        response = "CON Enter your IyaVoucher code:"
                    else:
                        response = "END A database error occurred. Please contact support."
                
                elif flow_state == 'AWAITING_VOUCHER_CODE':
                    voucher_code = text_parts[1]
                    token_details = db.get_token_by_value(voucher_code)

                    if token_details and token_details.get('status') == 'active':
                        amount_to_load = int(token_details.get('type', 0))
                        user_account_number = user.get('accountNumber')

                        if amount_to_load > 0 and user_account_number:
                            # We need to do a name enquiry on our own bank to get a session ID for the transfer
                            name_enquiry_result = api.name_enquiry("090286", user_account_number) # Assuming 090286 is SafeHaven's code
                            if name_enquiry_result and name_enquiry_result.get('status') == 'success':
                                enquiry_data = name_enquiry_result.get('data', {}).get('data', {})
                                name_enquiry_session_id = enquiry_data.get('sessionId')

                                if name_enquiry_session_id:
                                    transfer_result = api.initiate_transfer(
                                        name_enquiry_reference=name_enquiry_session_id,
                                        debit_account_number="0118816902", # Master debit account
                                        beneficiary_bank_code="090286", # SafeHaven's bank code
                                        beneficiary_account_number=user_account_number,
                                        amount=amount_to_load
                                    )
                                    if transfer_result and transfer_result.get('status') == 'success':
                                        db.update_token_status(voucher_code, 'inactive')
                                        response = f"END NGN {amount_to_load} Loaded successfully."
                                    else:
                                        response = "END Voucher loading failed."
                                else:
                                    response = "END Could not validate your account for loading."
                            else:
                                response = "END Could not validate your account for loading."
                        else:
                            response = "END Invalid voucher or user account not found."
                    else:
                        response = "END Invalid or already used voucher code."

            elif choice == "4": # IyaFix
                flow_state = user.get('iyafix_flow_state')

                if flow_state is None:
                    update_result = db.update_user(phone_number, {'iyafix_flow_state': 'AWAITING_PLAN_NAME'})
                    if update_result:
                        response = "CON Enter a name for your IyaFix plan:"
                    else:
                        response = "END A database error occurred. Please contact support."

                elif flow_state == 'AWAITING_PLAN_NAME':
                    plan_name = text_parts[1]
                    db.update_user(phone_number, {
                        'iyafix_plan_name': plan_name,
                        'iyafix_flow_state': 'AWAITING_DURATION'
                    })
                    response = "CON Select duration:\n1. 30 Days\n2. 60 Days\n3. 90 Days\n4. 6 Months"

                elif flow_state == 'AWAITING_DURATION':
                    duration_choice = text_parts[2]
                    durations = {"1": "30 Days", "2": "60 Days", "3": "90 Days", "4": "6 Months"}
                    if duration_choice in durations:
                        db.update_user(phone_number, {
                            'iyafix_duration': durations[duration_choice],
                            'iyafix_flow_state': 'AWAITING_AMOUNT'
                        })
                        response = "CON Enter amount to fix:"
                    else:
                        response = "CON Invalid duration selected."

                elif flow_state == 'AWAITING_AMOUNT':
                    amount_input = text_parts[-1]
                    if amount_input.isdigit():
                        amount = int(amount_input)
                        user_account = user.get('accountNumber')
                        
                        fix_result = api.create_virtual_account(user_account, amount)
                        
                        if fix_result and fix_result.get('status') == 'success':
                            plan_name = user.get('iyafix_plan_name', 'Your')
                            duration = user.get('iyafix_duration', '')
                            response = f"END Your '{plan_name}' IyaFix of NGN {amount:,.2f} for {duration} is successful."
                        else:
                            error_message = fix_result.get('message', 'An unknown error occurred.')
                            response = f"END Plan creation failed: {error_message}"
                    else:
                        response = "CON Invalid amount entered."

            elif choice == "5": # Health Insurance
                flow_state = user.get('health_form_state')

                if flow_state is None:
                    update_result = db.update_user(phone_number, {'health_form_state': 'AWAITING_STATE_SELECTION', 'health_form_page': 1})
                    if update_result:
                        response = get_paginated_list(NIGERIAN_STATES, 1, 5, "Select State")
                    else:
                        response = "END A database error occurred. Please contact support."

                elif flow_state == 'AWAITING_STATE_SELECTION':
                    user_input = text_parts[-1]
                    current_page = user.get('health_form_page', 1)

                    if user_input == '0': # Next
                        new_page = current_page + 1
                        total_pages = (len(NIGERIAN_STATES) + 4) // 5
                        if new_page <= total_pages:
                            db.update_user(phone_number, {'health_form_page': new_page})
                            response = get_paginated_list(NIGERIAN_STATES, new_page, 5, "Select State")
                        else:
                            response = get_paginated_list(NIGERIAN_STATES, current_page, 5, "Select State")

                    elif user_input == '9': # Previous
                        new_page = max(1, current_page - 1)
                        db.update_user(phone_number, {'health_form_page': new_page})
                        response = get_paginated_list(NIGERIAN_STATES, new_page, 5, "Select State")

                    elif user_input.isdigit():
                        selection = int(user_input)
                        if 1 <= selection <= len(NIGERIAN_STATES):
                            selected_state = NIGERIAN_STATES[selection - 1]
                            if selected_state == "Plateau":
                                db.update_user(phone_number, {'health_form_state': 'AWAITING_LGA'})
                                response = "CON Enter your LGA of residence:"
                            else:
                                response = "END Health insurance for your selected state is not available at this time."
                        else:
                            response = "CON Invalid selection. Please try again."
                    else:
                        response = "CON Invalid input. Please try again."
                
                elif flow_state == 'AWAITING_LGA':
                    lga = text_parts[-1]
                    db.update_user(phone_number, {'health_form_lga': lga, 'health_form_state': 'AWAITING_NIN'})
                    response = "CON Enter your 11-digit NIN:"

                elif flow_state == 'AWAITING_NIN':
                    nin = text_parts[-1]
                    if len(nin) == 11 and nin.isdigit():
                        db.update_user(phone_number, {'health_form_nin': nin, 'health_form_state': 'AWAITING_TIER'})
                        response = "CON Select Tier:\n1. Family\n2. Individual"
                    else:
                        response = "CON Invalid NIN. Please enter an 11-digit NIN:"

                elif flow_state == 'AWAITING_TIER':
                    tier_choice = text_parts[-1]
                    tier = None
                    if tier_choice == '1':
                        tier = 'Family'
                    elif tier_choice == '2':
                        tier = 'Individual'
                    else:
                        response = "CON Invalid selection. Please choose a tier:\n1. Family\n2. Individual"
                        # Return early to prevent proceeding with an invalid tier
                        return response
                    
                    db.update_user(phone_number, {'health_form_tier': tier, 'health_form_state': 'AWAITING_FULL_NAME'})
                    response = "CON Enter your Full Name:"

                elif flow_state == 'AWAITING_FULL_NAME':
                    full_name = text_parts[-1]
                    
                    record = {
                        'lga_of_residence': user.get('health_form_lga'),
                        'NIN': user.get('health_form_nin'),
                        'Tier': user.get('health_form_tier'),
                        'name': full_name,
                        'phone_number': phone_number
                    }
                    
                    create_result = db.create_plaschema_record(record)
                    
                    if create_result:
                        response = "END Your health insurance registration is successful."
                    else:
                        response = "END Registration failed. Please try again later."

            elif choice == "9": # My Account
                acc_num = user.get('accountNumber')
                acc_name = user.get('accountName')
                balance = user.get('accountBalance', 0)
                
                response = f"END Your Account Details:\n"
                response += f"Name: {acc_name}\n"
                response += f"Number: {acc_num}\n"
                response += f"Balance: NGN {balance:,.2f}"
            else:
                response = "END Thank you for using IyaPays. This feature is coming soon."
        
        logger.info(f"--- SENDING USSD RESPONSE ---\n{response}")
        return response

    # ======================================================
    # ===== NEW USER REGISTRATION FLOW =====
    # ======================================================
    if level == 0:
        initial_data = {
            'client': phone_number, 'id_type': None, 'bvn': None,
            'identityId': None, '_id': None, 'status': 'PENDING'
        }
        if user:
            db.update_user(phone_number, initial_data)
        else:
            db.create_user(initial_data)
        response = "CON Welcome to IyaPays.\nPlease choose your ID type:\n1. BVN\n2. NIN"

    elif level == 1:
        id_choice = text_parts[0]
        id_type = "BVN" if id_choice == "1" else "NIN" if id_choice == "2" else None
        if id_type:
            prompt = f"Please enter your 11-digit {id_type}:"
            db.update_user(phone_number, {'id_type': id_type})
            response = f"CON {prompt}"
        else:
            response = "END Invalid choice. Please start over."

    elif level == 2 and user and user.get('id_type'):
        id_type = user.get('id_type')
        id_number = text_parts[1]
        if len(id_number) == 11 and id_number.isdigit():
            db.update_user(phone_number, {'bvn': id_number})
            init_result = api.initiate_id_verification(id_type, id_number)
            if init_result and init_result.get('status') == 'success':
                nested_data = init_result.get('data', {}).get('data', {})
                identity_id = nested_data.get('_id')
                if identity_id:
                    db.update_user(phone_number, {'identityId': identity_id})
                    response = "CON An OTP has been sent to you. Please enter the code to continue."
                else:
                    response = "END Verification failed. Could not get a verification ID."
            else:
                response = f"END Your {id_type} could not be verified. Please check and try again."
        else:
            response = f"END Invalid {id_type}. It must be 11 digits."

    elif level == 3 and user and user.get('identityId'):
        otp = text_parts[2]
        identity_id = user.get('identityId')
        id_type = user.get('id_type')
        validate_result = api.validate_verification(identity_id, otp, id_type)
        if validate_result and validate_result.get('status') == 'success':
            nested_data = validate_result.get('data', {}).get('data', {})
            final_identity_id = nested_data.get('_id', identity_id)
            db.update_user(phone_number, {'identityId': final_identity_id})
            response = "CON OTP Validated successfully! Press 1 to create your account."
        else:
            api_message = validate_result.get('message', 'Please check the code and try again.')
            response = f"END OTP validation failed. {api_message}"

    elif level == 4 and user and user.get('identityId'):
        choice = text_parts[3] 

        if choice == '1':
            identity_id = user.get('identityId')
            account_result = api.create_sub_account(identity_id, phone_number)
            
            if account_result and account_result.get('status') == 'success':
                account_data = account_result.get('data', {})
                update_data = {
                    '_id': account_data.get('_id'),
                    'accountNumber': account_data.get('accountNumber'),
                    'accountName': account_data.get('accountName'),
                    'accountBalance': account_data.get('accountBalance', 0),
                    'external_reference': account_data.get('externalReference'),
                    'status': 'COMPLETED'
                }
                db.update_user(phone_number, update_data)
                
                acc_name = update_data.get('accountName')
                acc_num = update_data.get('accountNumber')
                balance = update_data.get('accountBalance', 0)
                
                response = f"END Congratulations! Your account is ready.\n"
                response += f"Name: {acc_name}\n"
                response += f"Number: {acc_num}\n"
                response += f"Balance: NGN {balance:,.2f}"
            else:
                api_message = account_result.get('message', 'Please try again later.')
                response = f"END We could not create your account at this time. {api_message}"
        else:
            response = "END Invalid choice. Please start over to create your account."

    else:
        response = "END An error occurred or your session has expired. Please dial the code to start again."

    logger.info(f"--- SENDING USSD RESPONSE ---\n{response}")
    return response

if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
