#!/usr/bin/env python3
"""
Test script for RAID 5 implementation
This script helps verify that the RAID 5 implementation works correctly.
"""

import subprocess
import time
import sys
import os

def start_servers(num_servers=4, block_size=128, total_blocks=256):
    """Start the block servers"""
    servers = []
    for i in range(num_servers):
        port = 8000 + i
        cmd = [
            'python', 'blockserver.py',
            '-nb', str(total_blocks),
            '-bs', str(block_size),
            '-port', str(port)
        ]
        print(f"Starting server {i} on port {port}")
        server = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        servers.append(server)
        time.sleep(1)  # Give servers time to start
    return servers

def test_raid5_basic():
    """Test basic RAID 5 functionality"""
    print("=== Testing Basic RAID 5 Functionality ===")
    
    # Start servers
    servers = start_servers()
    
    try:
        # Start the file system
        cmd = [
            'python', 'fsmain.py',
            '-nb', '256',
            '-bs', '128',
            '-ni', '16',
            '-is', '16',
            '-cid', '0',
            '-port', '8000',
            '-startport', '8000',
            '-ns', '4'
        ]
        
        print("Starting file system...")
        fs_process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        # Test commands
        test_commands = [
            "create testfile",
            "append testfile 'Hello RAID 5!'",
            "cat testfile",
            "verify 0",
            "verify 1",
            "showblock 0",
            "exit"
        ]
        
        for cmd in test_commands:
            print(f"Executing: {cmd}")
            fs_process.stdin.write(cmd + "\n")
            fs_process.stdin.flush()
            time.sleep(0.5)
        
        # Get output
        stdout, stderr = fs_process.communicate(timeout=10)
        print("File system output:")
        print(stdout)
        if stderr:
            print("Errors:")
            print(stderr)
            
    except subprocess.TimeoutExpired:
        print("File system process timed out")
        fs_process.kill()
    except Exception as e:
        print(f"Error during testing: {e}")
    finally:
        # Clean up
        for server in servers:
            server.terminate()
        if 'fs_process' in locals():
            fs_process.terminate()

def test_raid5_failure_recovery():
    """Test RAID 5 failure recovery"""
    print("\n=== Testing RAID 5 Failure Recovery ===")
    
    # Start servers
    servers = start_servers()
    
    try:
        # Start the file system
        cmd = [
            'python', 'fsmain.py',
            '-nb', '256',
            '-bs', '128',
            '-ni', '16',
            '-is', '16',
            '-cid', '0',
            '-port', '8000',
            '-startport', '8000',
            '-ns', '4'
        ]
        
        print("Starting file system...")
        fs_process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        # Test commands with server failure simulation
        test_commands = [
            "create testfile2",
            "append testfile2 'Testing failure recovery'",
            "cat testfile2",
            # Simulate server 1 failure by terminating it
            "repair 1",  # This should work even if server 1 is down
            "cat testfile2",  # Should still work
            "exit"
        ]
        
        for i, cmd in enumerate(test_commands):
            print(f"Executing: {cmd}")
            fs_process.stdin.write(cmd + "\n")
            fs_process.stdin.flush()
            
            # Simulate server failure after writing data
            if i == 2:  # After writing data
                print("Simulating server 1 failure...")
                servers[1].terminate()
                time.sleep(1)
            
            time.sleep(0.5)
        
        # Get output
        stdout, stderr = fs_process.communicate(timeout=15)
        print("File system output:")
        print(stdout)
        if stderr:
            print("Errors:")
            print(stderr)
            
    except subprocess.TimeoutExpired:
        print("File system process timed out")
        fs_process.kill()
    except Exception as e:
        print(f"Error during testing: {e}")
    finally:
        # Clean up
        for server in servers:
            server.terminate()
        if 'fs_process' in locals():
            fs_process.terminate()

if __name__ == "__main__":
    print("RAID 5 Implementation Test Suite")
    print("=================================")
    
    # Check if required files exist
    required_files = ['block.py', 'blockserver.py', 'fsmain.py', 'fsconfig.py', 'shell.py']
    for file in required_files:
        if not os.path.exists(file):
            print(f"Error: Required file {file} not found")
            sys.exit(1)
    
    # Run tests
    test_raid5_basic()
    test_raid5_failure_recovery()
    
    print("\nTest suite completed!") 