import requests
import json
import urllib.parse

def test_delete():
    session = requests.Session()
    # Login
    r = session.post('http://localhost:5000/login', data={'username': 'admin', 'password': 'password123'})
    print('Login Status:', r.status_code)
    
    # Try to delete Note string matching JS encodeURIComponent
    filename = 'Test_Delete.md'
    url = f'http://localhost:5000/notes/delete/{urllib.parse.quote(filename)}'
    print(f'Sending POST to: {url}')
    r2 = session.post(url)
    print('Delete Note Status:', r2.status_code)
    try:
        print('Response JSON:', r2.json())
    except:
        print('Response Text:', r2.text)

if __name__ == '__main__':
    test_delete()
