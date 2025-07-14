# File System with RAID 5 Implementation

## Project Overview

This project implements a distributed file system with RAID 5 fault tolerance. The system provides data protection through distributed parity, allowing the file system to continue operating even when one server fails. This is a Computer System Design project that demonstrates RAID 5 concepts in practice.

## Features

- **RAID 5 Distributed Parity**: Parity blocks rotate across all servers for fault tolerance
- **Fault Tolerance**: Can survive single server failure with automatic data recovery
- **Data Recovery**: Automatic reconstruction of data using parity and remaining servers
- **Consistency Verification**: Built-in tools to verify RAID 5 integrity
- **Interactive Shell**: Command-line interface for file operations and RAID management
- **Multi-Server Architecture**: Distributed storage across multiple block servers

## Architecture

### RAID 5 Implementation
- **Distributed Parity**: Parity blocks rotate across servers for each stripe
- **Stripe Distribution**: For N servers, each stripe contains (N-1) data blocks + 1 parity block
- **Fault Tolerance**: Can handle single server failure with automatic recovery
- **Space Efficiency**: 25% storage overhead for 4-server configuration

### System Components
- **Block Servers**: Individual storage servers (default: 4 servers)
- **File System**: Main file system with RAID 5 layer
- **Interactive Shell**: Command-line interface for operations
- **RAID Controller**: Handles parity calculation and data distribution

## Prerequisites

- Python 3.6 or higher
- Network connectivity between servers (localhost for testing)

## Installation

1. **Clone the repository**:
   ```bash
   git clone <your-repository-url>
   cd project
   ```

2. **Verify all files are present**:
   ```bash
   ls -la
   ```
   You should see: `block.py`, `blockserver.py`, `fsmain.py`, `fsconfig.py`, `shell.py`

## Quick Start

### 1. Start Block Servers

Open **4 separate terminal windows** and run these commands:

**Terminal 1** (Server 0):
```bash
python blockserver.py -nb 256 -bs 128 -port 8000
```

**Terminal 2** (Server 1):
```bash
python blockserver.py -nb 256 -bs 128 -port 8001
```

**Terminal 3** (Server 2):
```bash
python blockserver.py -nb 256 -bs 128 -port 8002
```

**Terminal 4** (Server 3):
```bash
python blockserver.py -nb 256 -bs 128 -port 8003
```

### 2. Start File System

Open a **5th terminal** and run:
```bash
python fsmain.py -nb 256 -bs 128 -ni 16 -is 16 -cid 0 -port 8000 -startport 8000 -ns 4
```

### 3. Use the File System

You'll see a prompt like: `[cwd=/]%`

Try these commands:
```bash
create myfile
append myfile "Hello RAID 5!"
cat myfile
ls
```

## Available Commands

### File Operations
- `create <filename>` - Create a new file
- `append <filename> <content>` - Append content to file
- `cat <filename>` - Display file contents
- `ls` - List files in current directory
- `cd <directory>` - Change directory
- `mkdir <directory>` - Create directory
- `rm <filename>` - Remove file

### RAID 5 Operations
- `verify <block_number>` - Verify RAID 5 consistency for a block
- `repair <server_id>` - Repair a failed server using parity reconstruction
- `showblock <block_number>` - Display block contents
- `showfsconfig` - Show file system configuration

### System Operations
- `save <filename>` - Save file system state
- `load <filename>` - Load file system state
- `exit` - Exit the file system

## Testing RAID 5 Functionality

### Basic Test
1. Create and write to a file:
   ```bash
   create testfile
   append testfile "Testing RAID 5 functionality"
   cat testfile
   ```

2. Verify RAID 5 consistency:
   ```bash
   verify 0
   verify 1
   ```

### Failure Recovery Test
1. Create a file with data
2. Stop one of the block servers (Ctrl+C in its terminal)
3. Try to read the file - it should still work using parity recovery
4. Restart the stopped server
5. Use `repair <server_id>` to reconstruct any missing data

### Automated Testing
Run the test suite:
```bash
python test_raid5.py
```

## Configuration Options

### File System Parameters
- `-nb <number>` - Total number of blocks (default: 256)
- `-bs <number>` - Block size in bytes (default: 128)
- `-ni <number>` - Maximum number of inodes (default: 16)
- `-is <number>` - Inode size in bytes (default: 16)

### Network Parameters
- `-cid <number>` - Client ID (default: 0)
- `-port <number>` - Main port (default: 8000)
- `-startport <number>` - Starting port for servers (default: 8000)
- `-ns <number>` - Number of servers (default: 4)

## Understanding RAID 5

### How It Works
1. **Data Distribution**: Data blocks are distributed across (N-1) servers
2. **Parity Calculation**: Parity is calculated using XOR operations
3. **Rotating Parity**: Parity location rotates across servers for each stripe
4. **Fault Tolerance**: Can recover data if one server fails

### Example with 4 Servers
```
Stripe 0: Data[Server0, Server1, Server2] Parity[Server3]
Stripe 1: Data[Server0, Server1, Server3] Parity[Server2]
Stripe 2: Data[Server0, Server2, Server3] Parity[Server1]
Stripe 3: Data[Server1, Server2, Server3] Parity[Server0]
```

### Recovery Process
When a server fails:
1. System detects the failure during read/write
2. Uses parity data from the parity server
3. XORs with data from remaining servers
4. Reconstructs the missing data

## Troubleshooting

### Common Issues

**"SERVER_DISCONNECTED" messages**
- Ensure all 4 block servers are running
- Check that ports 8000-8003 are available
- Verify no firewall blocking connections

**"CORRUPTED_BLOCK" messages**
- Run `verify <block_number>` to check consistency
- Use `repair <server_id>` to reconstruct data
- Check server logs for corruption events

**File system won't start**
- Make sure all block servers are running first
- Check command line arguments
- Verify Python version (3.6+)

### Debug Mode
Enable detailed logging by modifying `fsmain.py`:
```python
logging.basicConfig(filename='memoryfs.log', filemode='w', level=logging.DEBUG)
```

### Performance Notes
- **Write Performance**: 4x slower than single server (due to parity calculations)
- **Read Performance**: Same as single server (normal case)
- **Recovery Performance**: Slower during server failure (requires multiple reads)

## Project Structure

```
project/
├── block.py          # RAID 5 implementation and block layer
├── blockserver.py    # Individual block storage servers
├── fsmain.py         # Main file system entry point
├── fsconfig.py       # Configuration and constants
├── shell.py          # Interactive command shell
├── test_raid5.py     # Automated test suite
├── RAID5_README.md   # Detailed RAID 5 documentation
└── README.md         # This file
```

## Learning Objectives

This project demonstrates:
- **RAID 5 Concepts**: Distributed parity, fault tolerance, data recovery
- **Distributed Systems**: Multi-server architecture, network communication
- **File System Design**: Block storage, inodes, directory structure
- **Error Handling**: Graceful failure recovery, consistency checking
- **System Programming**: Low-level storage operations, XOR calculations

## Contributing

This is an educational project. Feel free to:
- Report bugs or issues
- Suggest improvements
- Add new features
- Improve documentation

## License

This project is for educational purposes as part of a Computer System Design course.

## Acknowledgments

- Based on file system design principles
- Implements RAID 5 fault tolerance concepts
- Educational project for learning distributed systems

---

**Note**: This is a simplified implementation for educational purposes. Production RAID systems have additional features like hot spares, multiple failure handling, and advanced error correction. 
