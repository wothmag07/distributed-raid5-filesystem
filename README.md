# Distributed RAID-5 File System

A distributed file system built in Python that stripes data and parity across multiple block servers using RAID-5, providing fault tolerance against single-server failures.

Built for **ECE 599 / CS 579 — Principles of Computer System Design** (Oregon State University).

---

## Architecture

```
                       fsmain.py
                      (entry point)
                           |
                           v
                       shell.py
                    Interactive CLI
             create, cat, ls, mkdir, append,
             rm, slice, mirror, lnh, lns, cd,
             verify, verifyall, repair, save, load
                           |
               +-----------+-----------+
               |                       |
        absolutepath.py         fileoperations.py
        Path Resolution          File Operations

        /foo/bar -> inode        Create, Read, Write
        Symlink resolution       Slice, Mirror, Unlink
        Link, Symlink
               |                       |
               +-----------+-----------+
                           |
                      filename.py
                    Directory Layer

                    Lookup, Insert,
                    FindAvailableInode,
                    AllocateDataBlock
                           |
                inodenumber.py / inode.py
                 Inode Serialization

                 type, size, refcnt,
                 block_numbers[]
                           |
                       block.py
                    RAID-5 Engine

                Stripe mapping (Put/Get)
                XOR parity compute
                Degraded-mode I/O
                Failed server tracking
                Verify / Repair
                           |
                    XML-RPC / HTTP
                           |
        Server:0   Server:1   Server:2   Server:3   ...up to N=8
         :8000      :8001      :8002      :8003

                 each runs blockserver.py
               stores blocks + MD5 checksums
             verifies integrity on every Get()
```

**RAID-5 stripe layout (4 servers, rotating parity):**

| Stripe | Server 0   | Server 1   | Server 2   | Server 3   |
| ------ | ---------- | ---------- | ---------- | ---------- |
| 0      | **Parity** | Data 0     | Data 1     | Data 2     |
| 1      | Data 3     | **Parity** | Data 4     | Data 5     |
| 2      | Data 6     | Data 7     | **Parity** | Data 8     |
| 3      | Data 9     | Data 10    | Data 11    | **Parity** |

> Parity rotates right by one server per stripe (`parity_server = stripe % N`).

**Virtual-to-physical block mapping:** `getServerBlockAndParity(block_number)` returns `(data_server_index, stripe_number, parity_server_index)` where `stripe_number` is the physical block on each server.

```
Example: virtual_block = 7, N = 4 servers

  datablock_per_stripe = N - 1          = 3
  stripe_number        = 7 // 3         = 2        --> physical block on each server
  data_offset          = 7 %  3         = 1
  parity_server_index  = 2 %  4         = 2        --> Server 2 holds parity
  data_servers         = [0, 1, 3]                  --> all except parity
  data_server_index    = data_servers[1] = 1        --> Server 1 holds this data
```

---

## Write Path (Parity Update)

```
                        Put(block_number, data)
                                |
                                v
                   getServerBlockAndParity()
                   data_server, parity_server
                                |
                +---------------+---------------+
                |               |               |
           All servers up   Data server down   Parity server down
                |               |               |
                v               v               v
        Read old_parity   Read all other     Write new_data
        Read old_data     data in stripe     to data server
                |               |               |
                v               v            (done -- parity
        Write new_data    new_parity =        rebuilt on repair)
        to data server    new_data XOR
                |         all_other_data
                v               |
        new_parity =            v
        old_parity XOR    Write new_parity
        old_data XOR      to parity server
        new_data                |
                |            (done -- data
                v             reconstructed
        Write new_parity      on repair)
        to parity server
                |
             (done)
```

## Read Path (Normal + Recovery)

```
                        Get(block_number)
                                |
                                v
                   getServerBlockAndParity()
                   data_server, parity_server
                                |
                                v
                   Read from data server
                                |
                +---------------+---------------+
                |               |               |
          Checksum OK     CORRUPTED_BLOCK   ConnectionRefused
                |               |               |
                v               |               v
          Return data           |      Add to failed_servers
                                |      Print SERVER_DISCONNECTED
                                |               |
                                +-------+-------+
                                        |
                                        v
                                  Recovery mode
                             Read parity block
                             Read all other data blocks
                                        |
                                        v
                             recovered = parity
                               XOR d1 XOR d2 XOR ...
                                        |
                                        v
                                  Return recovered
```

---

## Quick Start

### Prerequisites

- Python 3.6+
- No third-party dependencies (standard library only)

### 1. Start Block Servers

Open 4 terminals:

```bash
python blockserver.py -nb 256 -bs 128 -port 8000    # Server 0
python blockserver.py -nb 256 -bs 128 -port 8001    # Server 1
python blockserver.py -nb 256 -bs 128 -port 8002    # Server 2
python blockserver.py -nb 256 -bs 128 -port 8003    # Server 3
```

### 2. Start the File System Client

```bash
python fsmain.py -nb 768 -bs 128 -ni 16 -is 16 -cid 0 -startport 8000 -ns 4
```

> **Note:** `-nb` on the client = `blocks_per_server * (N - 1)` = `256 * 3 = 768`.

### 3. Use the Shell

```
[cwd=0]% create testfile
[cwd=0]% append testfile helloworld
Successfully appended 10 bytes.
[cwd=0]% cat testfile
helloworld
[cwd=0]% mkdir mydir
[cwd=0]% ls
[1]:./
[1]:testfile
[1]:mydir/
[cwd=0]% verifyall
All RAID 5 stripes are consistent
```

---

## Shell Commands

### File Operations

| Command                            | Description                                             |
| ---------------------------------- | ------------------------------------------------------- |
| `create <file>`                    | Create a new empty file                                 |
| `append <file> <text>`             | Append text to a file                                   |
| `cat <file>`                       | Print file contents                                     |
| `slice <file> <offset> <count>`    | Remove bytes from a file                                |
| `mirror <file>`                    | Reverse the contents of a file                          |
| `rm <file>`                        | Delete a file                                           |
| `mkdir <dir>`                      | Create a directory                                      |
| `cd <path>`                        | Change directory (`/absolute` or `relative` paths)      |
| `ls`                               | List directory contents                                 |
| `lnh <target> <name>`              | Create a hard link                                      |
| `lns <target> <name>`              | Create a symbolic link                                  |

### RAID-5 Operations

| Command                            | Description                                             |
| ---------------------------------- | ------------------------------------------------------- |
| `verify <block>`                   | Check parity consistency for one block's stripe         |
| `verifyall`                        | Check parity consistency for all stripes                |
| `repair <server_id>`               | Reconstruct all blocks for a failed server              |

### System Operations

| Command                            | Description                                             |
| ---------------------------------- | ------------------------------------------------------- |
| `save <file>`                      | Dump filesystem state to disk                           |
| `load <file>`                      | Restore filesystem from dump                            |
| `showblock <n>`                    | Display raw block contents                              |
| `showblockslice <n> <start> <end>` | Display slice of a block                                |
| `showinode <n>`                    | Display inode contents                                  |
| `showfsconfig`                     | Print filesystem parameters                             |
| `exit`                             | Quit the shell                                          |

---

## Fault Tolerance

### Corruption Detection

Each block server stores an MD5 checksum alongside every block. On `Get()`, the checksum is recomputed and compared. If it doesn't match, the server returns `CORRUPTED_BLOCK`.

To simulate corruption:

```bash
python blockserver.py -nb 256 -bs 128 -port 8000 -cblk 5
```

Any `Get(5)` on this server returns a checksum error. The client detects it, prints `CORRUPTED_BLOCK <virtual_block>`, and recovers transparently via parity.

### Server Failure

When a server is unreachable (`ConnectionRefusedError`):

1. The client prints `SERVER_DISCONNECTED <operation> <block_number>`
2. The server is added to `failed_servers` (at-most-once: no retries)
3. **Reads** recover via parity + remaining servers
4. **Writes** complete in degraded mode (data-only or parity-only)
5. Future operations skip the failed server entirely (fail-fast)

### Repair

After restarting a failed server with blank blocks:

```
[cwd=0]% repair 0
Starting repair for server 0...
Reconstructing block 0 on server 0...
Successfully repaired block 0 on server 0
...
Repair completed for server 0
[cwd=0]% verifyall
All RAID 5 stripes are consistent
```

The repair procedure:

1. Iterates all stripes that involve the failed server
2. Reconstructs each block via `XOR(parity, other_data_blocks)`
3. Writes the reconstructed block to the repaired server
4. Clears the server from the failed tracking set

---

## Configuration

### Client Arguments (`fsmain.py`)

| Flag          | Description                              | Default     |
| ------------- | ---------------------------------------- | ----------- |
| `-nb`         | Total virtual blocks (= per_server * (N-1)) | 256     |
| `-bs`         | Block size in bytes                      | 128         |
| `-ni`         | Maximum number of inodes                 | 16          |
| `-is`         | Inode size in bytes                      | 16          |
| `-cid`        | Client ID                                | 0           |
| `-startport`  | Port of server 0                         | 8000        |
| `-ns`         | Number of servers (4 to 8)               | 4           |
| `-sa`         | Server address                           | 127.0.0.1   |

### Server Arguments (`blockserver.py`)

| Flag          | Description                              | Default     |
| ------------- | ---------------------------------------- | ----------- |
| `-nb`         | Number of physical blocks on this server | required    |
| `-bs`         | Block size in bytes                      | required    |
| `-port`       | Port to listen on                        | required    |
| `-delayat`    | Insert 10s delay every N requests        | disabled    |
| `-cblk`       | Physical block to simulate corruption    | none        |

### Example: 5-Server Setup

```bash
# 5 servers, 256 blocks each
python blockserver.py -nb 256 -bs 128 -port 8000
python blockserver.py -nb 256 -bs 128 -port 8001
python blockserver.py -nb 256 -bs 128 -port 8002
python blockserver.py -nb 256 -bs 128 -port 8003
python blockserver.py -nb 256 -bs 128 -port 8004

# Client: -nb = 256 * 4 = 1024 usable blocks
python fsmain.py -nb 1024 -bs 128 -ni 16 -is 16 -cid 0 -startport 8000 -ns 5
```

---

## Project Structure

```
distributed-raid5-filesystem/
├── fsmain.py               Entry point: arg parsing, initialization, shell launch
├── fsconfig.py             Global constants and derived parameters
│
├── block.py                RAID-5 engine: striping, parity, degraded-mode I/O,
│                           failed server tracking, verify, repair, DumpToDisk
├── blockserver.py          Standalone XML-RPC block server with MD5 checksums
│
├── shell.py                Interactive CLI: file ops, RAID commands, repair
├── absolutepath.py         Path resolution, symlink following, Link, Symlink
├── fileoperations.py       Create, Read, Write, Slice, Mirror, Unlink
├── filename.py             Directory entry management, inode lookup, block alloc
├── inodenumber.py          Inode number to raw block mapping
├── inode.py                Inode data structure (type, size, refcnt, blocks)
│
├── test_raid5.py           Integration test harness (subprocess-based)
├── requirements.txt        Python dependencies (stdlib only)
├── TECHNICAL_REPORT.md     Full audit report with fix history
├── FIX_PLAN.md             Implementation plan for all fixes applied
└── README.md               This file
```

---

## Design Decisions

| Decision                                | Rationale                                                                                            |
| --------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| **RSM / Locking is a local no-op**      | Single-client assumption per spec. No server contact needed.                                         |
| **At-most-once / fail-fast**            | Per spec: detect disconnect immediately, no retries. `failed_servers` set avoids repeated timeouts.  |
| **Degraded-mode writes**                | Writes must complete with one server down. Data-down: recompute parity. Parity-down: write data only.|
| **Symlink resolution in path traversal**| `_ResolveSymlink()` transparently follows symlinks at each component, capped at 10 levels.           |
| **RAID-1/4 methods retained**           | Alternative implementations kept for reference; default path uses RAID-5 `Put()`/`Get()`.            |

---

## Limitations

- Single client only (no concurrent access)
- No journaling or write-ahead log (crash during write can leave stale parity)
- No hot spare / automatic failover
- Tolerates exactly 1 failure per stripe (not 2+)
- XML-RPC is unauthenticated and unencrypted
- `save`/`load` uses pickle (not safe for untrusted input)
