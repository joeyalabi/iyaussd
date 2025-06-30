from api_handler import SafeHavenAPI, SupabaseHandler

# --- Data Lists ---
# These are used by the handle_ussd function below
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


def get_bank_list_page(page_number, banks_per_page=4):
    """Helper function to create a paginated list of banks for the USSD menu."""
    start_index = (page_number - 1) * banks_per_page
    end_index = start_index + banks_per_page
    page_banks = BANKS[start_index:end_index]

    response = "CON Select beneficiary bank:\n"
    for i, bank in enumerate(page_banks):
        response += f"{start_index + i + 1}. {bank['name']}\n"
    
    if end_index < len(BANKS):
        response += f"0. Next\n"
    if page_number > 1:
        response += f"9. Previous"
        
    return response


def handle_ussd(data):
    """
    This function contains all the core logic for the USSD application.
    It takes the form data from the web request as input.
    """
    print("--- INCOMING USSD RAW DATA ---")
    print(data)

    db = SupabaseHandler()
    try:
        api = SafeHavenAPI(db)
    except Exception as e:
        print(f"CRITICAL: Failed to initialize SafeHavenAPI. Error: {e}")
        return "END Service is temporarily unavailable. Please try again later."

    session_id = data.get("sessionId")
    phone_number = data.get("phoneNumber")
    text = data.get("text", "")

    user = db.get_user_by_phone(phone_number)
    text_parts = text.split('*')
    level = len(text_parts) if text else 0 if text == "" else len(text.split('*'))

    print("--- PARSED REQUEST ---")
    print(f"Phone: {phone_number}, Text: '{text}', Level: {level}")
    if user:
        print(f"User found. Account Number: '{user.get('accountNumber')}'")
    else:
        print("No user found in DB for this phone number.")

    response = ""

    # ======================================================
    # ===== RETURNING USER FLOW =====
    # ======================================================
    if user and user.get('accountNumber'):
        account_name = user.get('accountName', phone_number)
        
        if text == "":
            # Clear any previous session state when user enters the main menu
            db.update_user(phone_number, {
                'transfer_flow_state': None, 'transfer_recipient_account': None,
                'transfer_recipient_bank_code': None, 'transfer_session_id': None,
                'transfer_page': None, 'airtime_flow_state': None,
                'airtime_service_id': None, 'airtime_recipient_number': None,
                'voucher_flow_state': None
            })
            response  = f"CON Welcome back, {account_name}.\n"
            response += "1. Add Funds\n"
            response += "2. Transfer Funds\n"
            response += "3. Buy Airtime\n"
            response += "4. IyaVoucher\n"
            response += "5. Pay Bills\n"
            response += "6. Savings\n"
            response += "7. Health Insurance\n"
            response += "8. My Account"
        
        else:
            choice = text_parts[0]
            if choice == "2": # Transfer Funds
                flow_state = user.get('transfer_flow_state')

                if flow_state is None:
                    db.update_user(phone_number, {'transfer_flow_state': 'AWAITING_RECIPIENT_ACCOUNT'})
                    response = "CON Enter beneficiary account number:"

                elif flow_state == 'AWAITING_RECIPIENT_ACCOUNT':
                    recipient_account = text_parts[1]
                    if len(recipient_account) == 10 and recipient_account.isdigit():
                        db.update_user(phone_number, {
                            'transfer_recipient_account': recipient_account, 
                            'transfer_page': 1,
                            'transfer_flow_state': 'AWAITING_BANK_SELECTION'
                        })
                        response = get_bank_list_page(1)
                    else:
                        response = "END Invalid account number. Please try again."

                elif flow_state == 'AWAITING_BANK_SELECTION':
                    user_input = text_parts[-1]
                    current_page = user.get('transfer_page', 1)
                    
                    if user_input == '0':
                        new_page = current_page + 1
                        total_pages = (len(BANKS) + 3) // 4
                        if new_page <= total_pages:
                            db.update_user(phone_number, {'transfer_page': new_page})
                            response = get_bank_list_page(new_page)
                        else:
                            response = get_bank_list_page(current_page)

                    elif user_input == '9':
                        new_page = max(1, current_page - 1)
                        db.update_user(phone_number, {'transfer_page': new_page})
                        response = get_bank_list_page(new_page)

                    elif user_input.isdigit():
                        selection = int(user_input)
                        if 1 <= selection <= len(BANKS):
                            selected_bank = BANKS[selection - 1]
                            bank_code = selected_bank['bank_code']
                            recipient_account = user.get('transfer_recipient_account')
                            
                            db.update_user(phone_number, {'transfer_recipient_bank_code': bank_code})
                            
                            name_enquiry_result = api.name_enquiry(bank_code, recipient_account)
                            if name_enquiry_result and name_enquiry_result.get('status') == 'success':
                                enquiry_data = name_enquiry_result.get('data', {}).get('data', {})
                                account_name = enquiry_data.get('accountName')
                                session_id = enquiry_data.get('sessionId')
                                
                                if account_name and session_id:
                                    db.update_user(phone_number, {
                                        'transfer_session_id': session_id,
                                        'transfer_flow_state': 'AWAITING_AMOUNT'
                                    })
                                    response = f"CON Beneficiary: {account_name}\nEnter amount:"
                                else:
                                    response = "END Could not verify account details. Please try again."
                            else:
                                response = "END Could not verify account details. Please try again."
                        else:
                            response = "END Invalid selection. Please try again."
                    else:
                        response = "END Invalid input. Please try again."
                
                elif flow_state == 'AWAITING_AMOUNT':
                    amount_input = text_parts[-1]
                    if amount_input.isdigit():
                        amount = int(amount_input)
                        session_id = user.get('transfer_session_id')
                        debit_account_number = user.get('accountNumber')
                        beneficiary_bank_code = user.get('transfer_recipient_bank_code')
                        beneficiary_account_number = user.get('transfer_recipient_account')
                        
                        transfer_result = api.initiate_transfer(session_id, debit_account_number, beneficiary_bank_code, beneficiary_account_number, amount)
                        if transfer_result and transfer_result.get('status') == 'success':
                            db.update_user(phone_number, {
                                'transfer_flow_state': None, 'transfer_recipient_account': None,
                                'transfer_recipient_bank_code': None, 'transfer_session_id': None,
                                'transfer_page': None
                            })
                            response = "END Transaction Successful."
                        else:
                            response = "END Transaction Failed. Please try again."
                    else:
                        response = "END Invalid amount. Please try again."

            elif choice == "3": # Buy Airtime
                flow_state = user.get('airtime_flow_state')

                if flow_state is None:
                    db.update_user(phone_number, {'airtime_flow_state': 'AWAITING_NETWORK'})
                    response = "CON Select Network:\n1. MTN\n2. GLO\n3. Airtel\n4. 9mobile"

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
                        response = "END Invalid network selection."

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
                        response = "END Invalid selection."

                elif flow_state == 'AWAITING_RECIPIENT_NUMBER':
                    recipient_number = text_parts[3]
                    if len(recipient_number) >= 11 and recipient_number.isdigit():
                        db.update_user(phone_number, {
                            'airtime_recipient_number': recipient_number,
                            'airtime_flow_state': 'AWAITING_AMOUNT'
                        })
                        response = "CON Enter amount:"
                    else:
                        response = "END Invalid phone number."

                elif flow_state == 'AWAITING_AMOUNT':
                    amount_input = text_parts[-1]
                    if amount_input.isdigit():
                        amount = int(amount_input)
                        debit_account = user.get('accountNumber')
                        recipient_num = user.get('airtime_recipient_number')
                        service_id = user.get('airtime_service_id')

                        airtime_result = api.buy_airtime(amount, debit_account, recipient_num, service_id)
                        if airtime_result and airtime_result.get('status') == 'success':
                            db.update_user(phone_number, {
                                'airtime_flow_state': None, 'airtime_service_id': None,
                                'airtime_recipient_number': None
                            })
                            response = f"END Airtime purchase of NGN {amount} for {recipient_num} was successful."
                        else:
                            response = "END Airtime purchase failed."
                    else:
                        response = "END Invalid amount."

            elif choice == "4": # IyaVoucher
                flow_state = user.get('voucher_flow_state')

                if flow_state is None:
                    db.update_user(phone_number, {'voucher_flow_state': 'AWAITING_VOUCHER_CODE'})
                    response = "CON Enter your IyaVoucher code:"
                
                elif flow_state == 'AWAITING_VOUCHER_CODE':
                    voucher_code = text_parts[1]
                    token_details = db.get_token_by_value(voucher_code)

                    if token_details and token_details.get('status') == 'active':
                        amount_to_load = int(token_details.get('type', 0))
                        user_account_number = user.get('accountNumber')

                        if amount_to_load > 0 and user_account_number:
                            name_enquiry_result = api.name_enquiry("090286", user_account_number)
                            if name_enquiry_result and name_enquiry_result.get('status') == 'success':
                                enquiry_data = name_enquiry_result.get('data', {}).get('data', {})
                                name_enquiry_session_id = enquiry_data.get('sessionId')

                                if name_enquiry_session_id:
                                    transfer_result = api.initiate_transfer(
                                        name_enquiry_reference=name_enquiry_session_id,
                                        debit_account_number="0118816902",
                                        beneficiary_bank_code="090286",
                                        beneficiary_account_number=user_account_number,
                                        amount=amount_to_load
                                    )

                                    if transfer_result and transfer_result.get('status') == 'success':
                                        db.update_token_status(voucher_code, 'inactive')
                                        response = f"END NGN {amount_to_load} Loaded successfully."
                                    else:
                                        response = "END Voucher loading failed. Please try again later."
                                else:
                                    response = "END Could not validate your account for loading. Please try again."
                            else:
                                response = "END Could not validate your account for loading. Please try again."
                        else:
                            response = "END Invalid voucher or user account not found."
                    else:
                        response = "END Invalid or already used voucher code."

            elif choice == "8": # My Account (Note the number change)
                acc_num = user.get('accountNumber')
                acc_name = user.get('accountName')
                balance = user.get('accountBalance', 0)
                
                response = f"END Your Account Details:\n"
                response += f"Name: {acc_name}\n"
                response += f"Number: {acc_num}\n"
                response += f"Balance: NGN {balance:,.2f}"
            else:
                response = "END Thank you for using IyaPays. This feature is coming soon."
        
        print(f"--- SENDING USSD RESPONSE ---\n{response}")
        return response

    # ======================================================
    # ===== NEW USER REGISTRATION FLOW =====
    # ======================================================
    if level == 0:
        initial_data = {
            'client': phone_number, 'id_type': None, 'bvn': None,
            'identityId': None, '_id': None
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
                    response = "CON An OTP has been sent. Please enter it to continue:"
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
            response = "END The OTP you entered is incorrect. Please dial the code to try again."

    elif level == 4 and user and user.get('identityId'):
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
            acc_name = update_data['accountName']
            acc_num = update_data['accountNumber']
            balance = update_data['accountBalance']
            response = f"END Congratulations! Your account is ready.\n"
            response += f"Name: {acc_name}\n"
            response += f"Number: {acc_num}\n"
            response += f"Balance: NGN {balance:,.2f}"
        else:
            response = "END We could not create your account at this time. Please try again later."


    else:
        response = "END An error occurred or your session has expired. Please dial the code to start again."

    print(f"--- SENDING USSD RESPONSE ---\n{response}")
    return response
