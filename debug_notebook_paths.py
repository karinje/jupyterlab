#!/usr/bin/env python3
"""
Debug script to check what notebook paths are being sent to the backend
"""
import requests
import json

BASE_URL = "http://localhost:8890"

def check_notebook_threads():
    """Check what threads exist for different notebook paths"""
    
    print("🔍 Debugging notebook path detection...")
    
    # Test different notebook paths that might exist
    test_paths = [
        "test_tools.ipynb",
        "Untitled1.ipynb", 
        "Untitled.ipynb",
        "Untitled2.ipynb"
    ]
    
    for notebook_path in test_paths:
        print(f"\n📚 Checking threads for: {notebook_path}")
        
        try:
            response = requests.get(f"{BASE_URL}/api/chat/threads", params={
                "notebook_path": notebook_path
            })
            
            if response.status_code == 200:
                data = response.json()
                threads = data.get("threads", [])
                selected = data.get("selected_thread_id")
                
                print(f"  Status: ✅ {response.status_code}")
                print(f"  Threads: {len(threads)}")
                print(f"  Selected: {selected}")
                
                if threads:
                    for i, thread in enumerate(threads):
                        messages = thread.get("messages", [])
                        title = thread.get("title", "No title")
                        print(f"    Thread {i+1}: '{title}' ({len(messages)} messages)")
                        if messages:
                            first_msg = messages[0].get("content", "")[:50]
                            print(f"      First: {first_msg}...")
            else:
                print(f"  Status: ❌ {response.status_code}")
                print(f"  Error: {response.text}")
                
        except Exception as e:
            print(f"  Error: {e}")
    
    print(f"\n✅ Debug completed!")

if __name__ == "__main__":
    check_notebook_threads() 