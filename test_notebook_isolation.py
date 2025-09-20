#!/usr/bin/env python3
"""
Test script to verify notebook conversation isolation
"""
import requests
import json
import time

BASE_URL = "http://localhost:8890"

def test_conversation_isolation():
    """Test that conversations are isolated per notebook"""
    
    print("🧪 Testing notebook conversation isolation...")
    
    # Test notebooks
    notebook_a = "test_notebook_A.ipynb"
    notebook_b = "test_notebook_B.ipynb"
    
    # Clear both notebooks first
    print(f"\n🧹 Clearing conversations for both notebooks...")
    
    for notebook in [notebook_a, notebook_b]:
        response = requests.post(f"{BASE_URL}/api/chat/debug", json={
            "action": "clear_conversations",
            "notebook_path": notebook
        })
        print(f"  Clear {notebook}: {response.status_code}")
    
    # Add conversation to notebook A (using correct openai endpoint)
    print(f"\n📝 Adding conversation to {notebook_a}...")
    response = requests.post(f"{BASE_URL}/api/chat/openai", json={
        "message": "Hello from notebook A - just testing isolation",
        "model": "gpt-4o-mini",
        "provider": "openai",
        "context": {
            "notebook_path": notebook_a
        }
    })
    print(f"  Add message to A: {response.status_code}")
    if response.status_code != 200:
        print(f"    Error: {response.text}")
    
    # Wait a moment for processing
    time.sleep(2)
    
    # Add conversation to notebook B  
    print(f"\n📝 Adding conversation to {notebook_b}...")
    response = requests.post(f"{BASE_URL}/api/chat/openai", json={
        "message": "Hello from notebook B - different conversation",
        "model": "gpt-4o-mini", 
        "provider": "openai",
        "context": {
            "notebook_path": notebook_b
        }
    })
    print(f"  Add message to B: {response.status_code}")
    if response.status_code != 200:
        print(f"    Error: {response.text}")
    
    # Wait a moment for processing
    time.sleep(2)
    
    # Check conversations in notebook A
    print(f"\n📚 Checking conversations in {notebook_a}...")
    response = requests.get(f"{BASE_URL}/api/chat/threads", params={
        "notebook_path": notebook_a
    })
    if response.status_code == 200:
        data = response.json()
        threads_a = data.get("threads", [])
        print(f"  Notebook A has {len(threads_a)} threads")
        for thread in threads_a:
            messages = thread.get("messages", [])
            print(f"    Thread: {len(messages)} messages")
            if messages:
                print(f"      First message: {messages[0].get('content', '')[:50]}...")
    else:
        print(f"  Error getting threads for A: {response.status_code}")
    
    # Check conversations in notebook B
    print(f"\n📚 Checking conversations in {notebook_b}...")
    response = requests.get(f"{BASE_URL}/api/chat/threads", params={
        "notebook_path": notebook_b
    })
    if response.status_code == 200:
        data = response.json()
        threads_b = data.get("threads", [])
        print(f"  Notebook B has {len(threads_b)} threads")
        for thread in threads_b:
            messages = thread.get("messages", [])
            print(f"    Thread: {len(messages)} messages")
            if messages:
                print(f"      First message: {messages[0].get('content', '')[:50]}...")
    else:
        print(f"  Error getting threads for B: {response.status_code}")
    
    # Clear notebook A only
    print(f"\n🧹 Clearing conversations for {notebook_a} only...")
    response = requests.post(f"{BASE_URL}/api/chat/debug", json={
        "action": "clear_conversations", 
        "notebook_path": notebook_a
    })
    print(f"  Clear A: {response.status_code}")
    
    # Check both notebooks after clearing A
    print(f"\n📚 After clearing A, checking both notebooks...")
    
    for notebook in [notebook_a, notebook_b]:
        response = requests.get(f"{BASE_URL}/api/chat/threads", params={
            "notebook_path": notebook
        })
        if response.status_code == 200:
            data = response.json()
            threads = data.get("threads", [])
            print(f"  {notebook}: {len(threads)} threads")
        else:
            print(f"  Error getting threads for {notebook}: {response.status_code}")
    
    print(f"\n✅ Test completed!")
    print(f"Expected: Notebook A should have 0 threads, Notebook B should still have 1 thread")

if __name__ == "__main__":
    test_conversation_isolation() 