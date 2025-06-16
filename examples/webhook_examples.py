#!/usr/bin/env python3
"""
Examples demonstrating webhook job functionality.

This file shows how to create and use webhook jobs that are triggered by HTTP requests.
"""

import requests
import json
from datetime import datetime

# Base URL for your API (adjust as needed)
BASE_URL = "http://localhost:8000"

def create_webhook_examples():
    """Create example webhook jobs."""
    
    # Example 1: Simple webhook that responds with request info
    simple_webhook = {
        "name": "Simple Echo Webhook",
        "endpoint": "/simple-echo",
        "code": '''
# This webhook echoes back the request information
response_data = {
    "message": f"Received {request_data['method']} request",
    "request_info": {
        "method": request_data["method"],
        "endpoint": request_data["endpoint"],
        "query_params": request_data["query_params"],
        "has_body": request_data["body"] is not None
    },
    "timestamp": datetime.now().isoformat()
}
''',
        "timeout": 30,
        "description": "A simple webhook that echoes request information"
    }
    
    # Example 2: Webhook that processes JSON data
    json_processor = {
        "name": "JSON Data Processor", 
        "endpoint": "/process-json",
        "code": '''
# Process JSON data from the request
if request_data["body"] and isinstance(request_data["body"], dict):
    data = request_data["body"]
    
    # Simple data processing example
    processed_items = []
    if "items" in data:
        for item in data["items"]:
            processed_items.append({
                "original": item,
                "processed": str(item).upper() if isinstance(item, str) else item * 2
            })
    
    response_data = {
        "status": "success",
        "processed_count": len(processed_items),
        "processed_items": processed_items,
        "original_data": data
    }
else:
    response_data = {
        "status": "error",
        "message": "Invalid or missing JSON data in request body"
    }
''',
        "timeout": 30,
        "description": "Processes JSON data from POST requests"
    }
    
    # Example 3: Webhook with external API call
    api_webhook = {
        "name": "External API Caller",
        "endpoint": "/fetch-data",
        "code": '''
import requests

# Get URL from query parameters
url = request_data["query_params"].get("url")

if url:
    try:
        # Make external API call
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            response_data = {
                "status": "success",
                "url": url,
                "status_code": response.status_code,
                "data": response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text[:500]
            }
        else:
            response_data = {
                "status": "error",
                "message": f"HTTP {response.status_code}",
                "url": url
            }
    except requests.RequestException as e:
        response_data = {
            "status": "error", 
            "message": f"Request failed: {str(e)}",
            "url": url
        }
    except Exception as e:
        response_data = {
            "status": "error",
            "message": f"Unexpected error: {str(e)}",
            "url": url
        }
else:
    response_data = {
        "status": "error",
        "message": "Missing 'url' query parameter"
    }
''',
        "packages": ["requests"],
        "timeout": 30,
        "description": "Fetches data from external URLs"
    }
    
    # Example 4: Database-like webhook (using in-memory storage)
    database_webhook = {
        "name": "Simple Database",
        "endpoint": "/database",
        "code": '''
import os
import json

# Simple file-based storage
DATA_FILE = "/tmp/webhook_data.json"

# Load existing data
try:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            storage = json.load(f)
    else:
        storage = {}
except:
    storage = {}

method = request_data["method"]

if method == "GET":
    # Return all data or specific key
    key = request_data["query_params"].get("key")
    if key:
        response_data = {
            "key": key,
            "value": storage.get(key),
            "exists": key in storage
        }
    else:
        response_data = {
            "data": storage,
            "count": len(storage)
        }

elif method == "POST":
    # Add/update data
    if request_data["body"] and isinstance(request_data["body"], dict):
        for key, value in request_data["body"].items():
            storage[key] = value
        
        # Save to file
        try:
            with open(DATA_FILE, 'w') as f:
                json.dump(storage, f)
            response_data = {
                "status": "success",
                "message": f"Updated {len(request_data['body'])} items",
                "data": request_data["body"]
            }
        except Exception as e:
            response_data = {
                "status": "error",
                "message": f"Failed to save: {str(e)}"
            }
    else:
        response_data = {
            "status": "error",
            "message": "Invalid JSON data"  
        }

elif method == "DELETE":
    # Delete data
    key = request_data["query_params"].get("key")
    if key and key in storage:
        del storage[key]
        try:
            with open(DATA_FILE, 'w') as f:
                json.dump(storage, f)
            response_data = {
                "status": "success",
                "message": f"Deleted key: {key}"
            }
        except Exception as e:
            response_data = {
                "status": "error",
                "message": f"Failed to save: {str(e)}"
            }
    else:
        response_data = {
            "status": "error",
            "message": f"Key '{key}' not found" if key else "Missing 'key' parameter"
        }

else:
    response_data = {
        "status": "error",
        "message": f"Unsupported method: {method}"
    }
''',
        "timeout": 30,
        "description": "Simple key-value storage webhook"
    }
    
    return [simple_webhook, json_processor, api_webhook, database_webhook]

def create_webhooks():
    """Create the webhook jobs via API."""
    webhooks = create_webhook_examples()
    
    created_webhooks = []
    for webhook in webhooks:
        try:
            response = requests.post(f"{BASE_URL}/webhook-jobs", json=webhook)
            if response.status_code == 200:
                created_webhook = response.json()
                created_webhooks.append(created_webhook)
                print(f"✓ Created webhook: {webhook['name']} at {webhook['endpoint']}")
            else:
                print(f"✗ Failed to create webhook {webhook['name']}: {response.text}")
        except Exception as e:
            print(f"✗ Error creating webhook {webhook['name']}: {e}")
    
    return created_webhooks

def test_webhooks():
    """Test the created webhooks."""
    print("\n" + "="*50)
    print("TESTING WEBHOOKS")
    print("="*50)
    
    # Test 1: Simple echo webhook
    print("\n1. Testing Simple Echo Webhook...")
    try:
        response = requests.get(f"{BASE_URL}/webhook/simple-echo?test=value")
        print(f"Response: {response.json()}")
    except Exception as e:
        print(f"Error: {e}")
    
    # Test 2: JSON processor webhook
    print("\n2. Testing JSON Data Processor...")
    try:
        test_data = {
            "items": ["hello", "world", 42, 3.14]
        }
        response = requests.post(
            f"{BASE_URL}/webhook/process-json",
            json=test_data,
            headers={"Content-Type": "application/json"}
        )
        print(f"Response: {response.json()}")
    except Exception as e:
        print(f"Error: {e}")
    
    # Test 3: External API caller
    print("\n3. Testing External API Caller...")
    try:
        response = requests.get(
            f"{BASE_URL}/webhook/fetch-data?url=https://httpbin.org/json"
        )
        print(f"Response: {response.json()}")
    except Exception as e:
        print(f"Error: {e}")
    
    # Test 4: Database webhook
    print("\n4. Testing Simple Database Webhook...")
    
    # Store some data
    try:
        test_data = {"name": "John", "age": 30, "city": "New York"}
        response = requests.post(
            f"{BASE_URL}/webhook/database",
            json=test_data,
            headers={"Content-Type": "application/json"}
        )
        print(f"Store data response: {response.json()}")
    except Exception as e:
        print(f"Store error: {e}")
    
    # Retrieve data
    try:
        response = requests.get(f"{BASE_URL}/webhook/database")
        print(f"Get all data response: {response.json()}")
    except Exception as e:
        print(f"Get error: {e}")
    
    # Get specific key
    try:
        response = requests.get(f"{BASE_URL}/webhook/database?key=name")
        print(f"Get specific key response: {response.json()}")
    except Exception as e:
        print(f"Get key error: {e}")

def list_webhook_jobs():
    """List all webhook jobs."""
    try:
        response = requests.get(f"{BASE_URL}/webhook-jobs")
        if response.status_code == 200:
            webhooks = response.json()
            print(f"\nFound {len(webhooks)} webhook jobs:")
            for webhook in webhooks:
                print(f"- {webhook['name']} ({webhook['endpoint']}) - Active: {webhook['is_active']}")
        else:
            print(f"Failed to list webhooks: {response.text}")
    except Exception as e:
        print(f"Error listing webhooks: {e}")

if __name__ == "__main__":
    print("Webhook Job Examples")
    print("="*50)
    
    # List existing webhooks
    list_webhook_jobs()
    
    # Create example webhooks
    print("\nCreating example webhooks...")
    created = create_webhooks()
    
    if created:
        # Test the webhooks
        test_webhooks()
        
        print("\n" + "="*50)
        print("WEBHOOK ENDPOINTS CREATED:")
        print("="*50)
        for webhook in created:
            print(f"• {webhook['name']}")
            print(f"  Endpoint: {BASE_URL}/webhook{webhook['endpoint']}")
            print(f"  Description: {webhook['description']}")
            print(f"  Methods: GET, POST, PUT, DELETE, PATCH")
            print()
    else:
        print("No webhooks were created successfully.") 