# ExternalAPIConnector Tool
# Description: Connect to external APIs or services (e.g., GitHub, calendars) to fetch data or perform actions autonomously on behalf of the user.

import json
import requests
from requests.auth import HTTPBasicAuth

def connect_to_api(api_endpoint, auth_credentials, action):
    '''
    Connect to an external API to fetch data or perform actions.
    
    Args:
        api_endpoint (str): The API URL to connect to
        auth_credentials (str): Authentication credentials or token (format depends on API, e.g., 'username:password' or 'Bearer token')
        action (str): Action to perform ('get', 'post', 'put', 'delete')
    
    Returns:
        dict: Result of API call with status, response data, and message
    '''
    result = {'status': 'success', 'response': {}, 'message': ''}
    
    try:
        headers = {}
        auth = None
        
        # Parse auth_credentials if provided
        if auth_credentials and ':' in auth_credentials:
            username, password = auth_credentials.split(':', 1)
            auth = HTTPBasicAuth(username, password)
        elif auth_credentials and auth_credentials.startswith('Bearer '):
            headers['Authorization'] = auth_credentials
        elif auth_credentials:
            headers['Authorization'] = f'Bearer {auth_credentials}'
        
        # Perform the requested action
        action = action.lower()
        if action == 'get':
            response = requests.get(api_endpoint, headers=headers, auth=auth, timeout=10)
        elif action == 'post':
            response = requests.post(api_endpoint, headers=headers, auth=auth, json={}, timeout=10)
        elif action == 'put':
            response = requests.put(api_endpoint, headers=headers, auth=auth, json={}, timeout=10)
        elif action == 'delete':
            response = requests.delete(api_endpoint, headers=headers, auth=auth, timeout=10)
        else:
            result['status'] = 'error'
            result['message'] = f'Unsupported action: {action}. Use "get", "post", "put", or "delete".'
            return result
        
        # Handle response
        response.raise_for_status()  # Raises an HTTPError for bad responses
        result['response'] = {
            'status_code': response.status_code,
            'data': response.json() if response.content else {}
        }
        result['message'] = f'Successfully performed {action.upper()} request to {api_endpoint}. Status code: {response.status_code}'
    except requests.exceptions.RequestException as e:
        result['status'] = 'error'
        result['message'] = f'API request failed: {str(e)}'
        result['response'] = {'status_code': getattr(e.response, "status_code", None), 'data': {}}
    except Exception as e:
        result['status'] = 'error'
        result['message'] = f'Error connecting to API: {str(e)}'
    
    return result

if __name__ == '__main__':
    # Example usage for testing (using a public API that doesn't require auth)
    test_endpoint = 'https://api.github.com/users/octocat'
    print(json.dumps(connect_to_api(test_endpoint, '', 'get'), indent=2))
