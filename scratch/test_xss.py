import requests
import json
url = 'http://127.0.0.1:8000/api/v1/auth/login'
login_resp = requests.post(url, data={'username': 'admin@example.com', 'password': 'admin123'})
tokens = login_resp.json()
access_token = tokens['access_token']
headers = {'Authorization': f'Bearer {access_token}'}

sources = requests.get('http://127.0.0.1:8000/api/v1/sources/', headers=headers).json()
source_id = sources[0]['id'] if sources else None

if source_id:
    lead_data = {
        'name': '<script>alert("XSS Hack")</script> Malicious Lead',
        'email': 'hacker2@example.com',
        'phone': '1234567890',
        'profession': '<script>console.log("stolen")</script> Hacker',
        'source_id': source_id
    }
    lead_resp = requests.post('http://127.0.0.1:8000/api/v1/leads/', json=lead_data, headers=headers)
    print('Lead creation:', lead_resp.status_code, lead_resp.text)
