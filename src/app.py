from flask import Flask, render_template, request, jsonify
from flask import Flask, jsonify, render_template, request, session
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, date, time
import pytz
import os
import json

app = Flask(__name__, static_folder='static')
app.secret_key = 'FMBWindsor53'

scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

# Check if the credentials are provided as an environmental variable
if 'GOOGLE_APPLICATION_CREDENTIALS' in os.environ:
    # Load the credentials from the environmental variable
    creds_data = json.loads(os.environ['GOOGLE_APPLICATION_CREDENTIALS'])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_data, scope)
else:
    # Load the credentials from the 'creds.json' file
    creds = ServiceAccountCredentials.from_json_keyfile_name('creds.json', scope)

client = gspread.authorize(creds)
# Load user data from Google Sheet
sheet = client.open('FMB Master Sheet').worksheet('Users')
user_data = sheet.get_all_records()

# Load menu data from Google Sheet
menu_sheet = client.open('FMB Master Sheet').worksheet('Menu')
menu_data = menu_sheet.get_all_records()

# Load response data from Google Sheet
response_sheet = client.open('FMB Master Sheet').worksheet('Response')
response_data = response_sheet.get_all_records()

finance_sheet = client.open('FMB Master Sheet').worksheet('Finance')

# Get current date and time in EST
est = pytz.timezone('US/Eastern')
now = datetime.now(est)

# Get current and next week start and end dates in EST
current_week_start = now.date() - timedelta(days=now.weekday())
current_week_end = current_week_start + timedelta(days=4)
if now.time() <= datetime.time(datetime(now.year, now.month, now.day, hour=17, minute=0)):
    current_week_end += timedelta(days=1)

next_week_start = current_week_end + timedelta(days=3)
next_week_start = next_week_start + timedelta(days=(0 - next_week_start.weekday()))
next_week_end = next_week_start + timedelta(days=5, hours=23, minutes=59, seconds=59)

# Get current and next week menu data
current_week_menu = [menu for menu in menu_data if datetime.strptime(menu['Date'], '%d-%m-%Y').date() >= current_week_start and datetime.strptime(menu['Date'], '%d-%m-%Y').date() <= current_week_end]
next_week_menu = [menu for menu in menu_data if datetime.strptime(menu['Date'], '%d-%m-%Y').date() >= next_week_start and datetime.strptime(menu['Date'], '%d-%m-%Y').date() <= next_week_end and menu['Day'] != 'Saturday' and menu['Day'] != 'Sunday']

next_week_menu = []
for menu in menu_data:
    if datetime.strptime(menu['Date'], '%d-%m-%Y').date() >= next_week_start and datetime.strptime(menu['Date'], '%d-%m-%Y').date() <= next_week_end:
        next_week_menu.append(menu)
        if len(next_week_menu) == 5:
            break

# Load password from config file
config_path = os.path.join(app.root_path, 'config.txt')
with open(config_path, 'r') as f:
    config_data = f.read().strip().split('=')
    admin_password = ''
    for i in range(0, len(config_data), 2):
        if config_data[i] == 'admin_password':
            admin_password = config_data[i + 1]

# Function to fetch thaali count and check response
def fetchThaaliCount(selectedDate):
    response_values = response_sheet.get_all_values()
    thaali_count = 0
    for row in response_values:
        if row[1] == selectedDate and row[3].lower() == 'no':
            thaali_count -= 1
    return thaali_count

@app.route('/')
def intro_page():
    return render_template('index.html')

@app.route('/thaali_count', methods=['POST'])
def get_thaali_count():
    selected_date = request.form['selected_date']
    thaali_count = fetchThaaliCount(selected_date)  # Call the fetchThaaliCount function with the selected date
    selected_day = datetime.strptime(selected_date, '%d-%m-%Y').strftime('%A')
    return jsonify({'thaali_count': thaali_count, 'selected_day': selected_day})

@app.route('/get_no_responses', methods=['POST'])
def get_no_responses():
    selected_date = request.form['selected_date']

    response_values = response_sheet.get_all_values()
    response_users = [row[0] for row in response_values if row[1] == selected_date and row[3].lower() == 'no']

    remaining_users = [user for user in user_data if user['Name'] not in response_users]
    remaining_names = [{'Name': user['Name'], 'Thaali Size': user['Thaali Size']} for user in remaining_users]

    response_names = [{'Name': user['Name'], 'Thaali Size': user['Thaali Size']} for user in user_data if user['Name'] in response_users and user not in remaining_users]

    thaali_count = len(remaining_names)
    not_taking_thaali_count = len(response_names)

    # Count occurrences of each thaali_size
    thaali_size_counts = {}
    for user in remaining_names:
        thaali_size = user['Thaali Size']
        thaali_size_counts[thaali_size] = thaali_size_counts.get(thaali_size, 0) + 1

    return jsonify({
        'remaining_names': remaining_names,
        'response_names': response_names,
        'thaali_count': thaali_count,
        'not_taking_thaali_count': not_taking_thaali_count,
        'thaali_size_counts': thaali_size_counts
    })


@app.route('/booking', methods=['GET', 'POST'])
def booking_page():
    # Set timezone to IST
    tz = pytz.timezone('US/Eastern')
    now = datetime.now(tz)

    if request.method == 'POST':
        email_id = request.form['email_id']
        password = request.form['password']

        error_message = None
        error_field = None

        if not password.isdigit():
            error_message = 'Invalid. Password should contain only numeric values. Try again or contact admin.'
            error_field = 'password'
        else:
            for user in user_data:
                if user['Email Address'] == str(email_id):
                    if user['ITs ID'] == int(password):
                        session['username'] = user['Name']
                        # Include all menus for the current week
                        current_week_menu_filtered = []
                        for menu in current_week_menu:
                            menu_date = datetime.strptime(menu['Date'], '%d-%m-%Y').date()
                            if menu_date < now.date():
                                menu['disable_submit'] = True
                            else:
                                menu['disable_submit'] = False
                            current_week_menu_filtered.append(menu)
                        return render_template('menu.html', user=user['Name'], current_week_menu=current_week_menu_filtered, next_week_menu=next_week_menu)
                    else:
                        error_message = 'Wrong Password. Try again or contact admin.'
                        error_field = 'password'
                        break
            else:
                error_message = 'Wrong Email ID. Try again or contact admin.'
                error_field = 'email_id'

        return render_template('login.html', error_message=error_message, error_field=error_field)

    return render_template('login.html')


@app.route('/submit', methods=['POST'])
def submit_response():
    name = request.form['name']
    date = request.form['date']
    day = request.form['day']
    response = request.form['response']

    # Set timezone to EST
    tz = pytz.timezone('US/Eastern')
    now = datetime.now(tz)
	
    # Check if the current time is past Saturday 11:59 PM EST
    current_weekday = now.weekday()  # Monday is 0 and Sunday is 6
    if current_weekday > 5 or (current_weekday == 5 and now.time() >= time(hour=23, minute=59)):
        return jsonify({'status': 'error', 'message': 'The deadline to submit the response has passed. Contact the admin.'})

    # Register the response
    for user in user_data:
        if user['Name'] == name:													  
            response_values = response_sheet.get_all_values()
            for i, row in enumerate(response_values):
                if row[1] == date and row[2] == day and row[0] == name:
                    response_sheet.update_cell(i + 1, 4, response)
                    return jsonify({'status': 'success', 'message': 'Response updated successfully.'})
            response_sheet.append_row([name, date, day, response])
            return jsonify({'status': 'success', 'message': 'Response submitted successfully.'})
    return jsonify({'status': 'error', 'message': 'Invalid user.'})



@app.route('/admin', methods=['GET', 'POST'])
def admin_page():

    response_data = response_sheet.get_all_records()  # Load response data from Google Sheet

    if request.method == 'POST':
        admin_username = request.form['username']
        admin_password = request.form['password']
        if admin_username == 'admin' and admin_password == admin_password:
            return render_template('admin.html', response_data=response_data)
        else:
            return 'Invalid username or password'
    else:
        return render_template('admin_login.html')

@app.route('/get_finance_data', methods=['GET'])
def get_finance_data():
    try:
        finance_data = finance_sheet.get_all_records()
        return render_template('finance.html', finance_data=finance_data)
    
    except Exception as e:
        print(f"Error retrieving finance data: {e}")
        return render_template('finance.html', finance_data=[])  # Return an empty list if there was an error

@app.route('/get_user_finance_data', methods=['GET'])
def get_user_finance_data():
    try:
        finance_data = finance_sheet.get_all_records()
        username = session.get('username')
        user_data = [row for row in finance_data if row['Name'] == username]
        if len(user_data) > 0:
            user_data = user_data[0]  # Retrieve the first row as a dictionary
        else:
            user_data = {}  # Set an empty dictionary if no data is found
        return render_template('user_finance.html', user_data=user_data)
    except Exception as e:
        print(f"Error retrieving user finance data: {e}")
        return render_template('user_finance.html', user_data={})


if __name__ == '__main__':
    app.run(debug=True)