# MemoryBank Tool
# Description: Store and retrieve long-term memories or milestones to build an evolving personality and reference shared history in conversations.

import json
from datetime import datetime
import os

def manage_memory(memory_entry, timestamp=None):
    '''
    Store or retrieve memories with timestamps for contextual conversation recall.
    
    Args:
        memory_entry (str): The memory or milestone to store, or a query to retrieve relevant memories
        timestamp (str, optional): ISO format timestamp for the memory; if None, current time is used for storing, or retrieval mode is assumed
    
    Returns:
        dict: Result of memory operation (store or retrieve) with status and data
    '''
    result = {'status': 'success', 'operation': '', 'data': {}, 'message': ''}
    memory_file = 'memory_bank.json'
    
    try:
        # Initialize memory storage if file doesn't exist
        if not os.path.exists(memory_file):
            with open(memory_file, 'w') as f:
                json.dump({'memories': []}, f)
        
        # Load existing memories
        with open(memory_file, 'r') as f:
            memory_data = json.load(f)
        
        if timestamp is None:
            # Retrieval mode: Search for relevant memories based on entry as query
            result['operation'] = 'retrieve'
            query = memory_entry.lower()
            matching_memories = [
                m for m in memory_data['memories']
                if query in m['content'].lower()
            ]
            result['data'] = {'matches': matching_memories}
            result['message'] = f'Found {len(matching_memories)} relevant memories for query "{memory_entry}".'
        else:
            # Storage mode: Save the memory with provided or current timestamp
            result['operation'] = 'store'
            if timestamp.strip() == '':
                timestamp = datetime.now().isoformat()
            new_memory = {
                'content': memory_entry,
                'timestamp': timestamp
            }
            memory_data['memories'].append(new_memory)
            with open(memory_file, 'w') as f:
                json.dump(memory_data, f, indent=2)
            result['data'] = {'stored_memory': new_memory}
            result['message'] = f'Successfully stored memory: "{memory_entry}" at {timestamp}.'
    except Exception as e:
        result['status'] = 'error'
        result['message'] = f'Error managing memory: {str(e)}'
    
    return result

if __name__ == '__main__':
    # Example usage for testing
    print(json.dumps(manage_memory('First interaction with user', '2026-03-12T23:45:00'), indent=2))
    print(json.dumps(manage_memory('interaction with user'), indent=2))
