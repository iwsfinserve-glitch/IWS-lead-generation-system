import requests
import time

url = 'http://127.0.0.1:8000/api/v1/auth/login'
login_resp = requests.post(url, data={'username': 'admin@example.com', 'password': 'admin123'})

if login_resp.status_code == 200:
    print('Login successful.')
    tokens = login_resp.json()
    access_token = tokens['access_token']
    refresh_token = tokens.get('refresh_token')
    
    if refresh_token:
        print('Refresh token obtained.')
        refresh_url = 'http://127.0.0.1:8000/api/v1/auth/refresh'
        refresh_resp = requests.post(refresh_url, json={'refresh_token': refresh_token})
        if refresh_resp.status_code == 200:
            print('✅ Token rotation successful. New access token received.')
        else:
            print('❌ Token rotation failed:', refresh_resp.status_code, refresh_resp.text)
    else:
        print('❌ No refresh token in response.')
    
    # Create malicious lead
    lead_data = {
        'name': '<script>alert("XSS Hack")</script> Malicious Lead',
        'email': 'hacker@example.com',
        'phone': '1234567890',
        'profession': '<script>console.log("stolen")</script> Hacker',
        'source_id': 1
    }
    
    leads_url = 'http://127.0.0.1:8000/api/v1/leads/'
    lead_resp = requests.post(leads_url, json=lead_data, headers={'Authorization': f'Bearer {access_token}'})
    if lead_resp.status_code in [200, 201]:
        print('✅ Malicious lead injected successfully. Ready to check frontend XSS.')
    else:
        print('❌ Lead creation failed:', lead_resp.status_code, lead_resp.text)

else:
    print('Login failed:', login_resp.status_code, login_resp.text)
