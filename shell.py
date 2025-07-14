import fsconfig
import os.path

from block import *
from inode import *
from inodenumber import *
from filename import *
from fileoperations import *
from absolutepath import *

## This class implements an interactive shell to navigate the file system

class FSShell():
    def __init__(self, RawBlocks, FileOperationsObject, AbsolutePathObject):
        # cwd stored the inode of the current working directory
        # we start in the root directory
        self.cwd = 0
        self.FileOperationsObject = FileOperationsObject
        self.AbsolutePathObject = AbsolutePathObject
        self.RawBlocks = RawBlocks

    # block-layer inspection, load/save, and debugging shell commands
    # implements showfsconfig (log fs config contents)
    def showfsconfig(self):
        fsconfig.PrintFSConstants()
        return 0

    # implements showinode (log inode i contents)
    def showinode(self, i):
        try:
            i = int(i)
        except ValueError:
            print('Error: ' + i + ' not a valid Integer')
            return -1

        if i < 0 or i >= fsconfig.MAX_NUM_INODES:
            print('Error: inode number ' + str(i) + ' not in valid range [0, ' + str(fsconfig.MAX_NUM_INODES - 1) + ']')
            return -1
        inobj = InodeNumber(i)
        inobj.InodeNumberToInode(self.RawBlocks)
        inode = inobj.inode
        inode.Print()
        return 0

    # implements load (load the specified dump file)
    def load(self, dumpfilename):
        if not os.path.isfile(dumpfilename):
            print("Error: Please provide valid file")
            return -1
        self.RawBlocks.LoadFromDump(dumpfilename)
        self.cwd = 0
        return 0

    # implements save (save the file system contents to specified dump file)
    def save(self, dumpfilename):
        self.RawBlocks.DumpToDisk(dumpfilename)
        return 0

    # implements showblock (log block n contents)
    def showblock(self, n):
        try:
            n = int(n)
        except ValueError:
            print('Error: ' + n + ' not a valid Integer')
            return -1
        if n < 0 or n >= fsconfig.TOTAL_NUM_BLOCKS:
            print('Error: block number ' + str(n) + ' not in valid range [0, ' + str(fsconfig.TOTAL_NUM_BLOCKS - 1) + ']')
            return -1
        print('Block (showing any string snippets in block the block) [' + str(n) + '] : \n' + str(
            (self.RawBlocks.Get(n).decode(encoding='UTF-8', errors='ignore'))))
        print('Block (showing raw hex data in block) [' + str(n) + '] : \n' + str((self.RawBlocks.Get(n).hex())))
        return 0

    # implements showblockslice (log slice of block n contents)
    def showblockslice(self, n, start, end):
        try:
            n = int(n)
        except ValueError:
            print('Error: ' + n + ' not a valid Integer')
            return -1
        try:
            start = int(start)
        except ValueError:
            print('Error: ' + start + ' not a valid Integer')
            return -1
        try:
            end = int(end)
        except ValueError:
            print('Error: ' + end + ' not a valid Integer')
            return -1

        if n < 0 or n >= fsconfig.TOTAL_NUM_BLOCKS:
            print('Error: block number ' + str(n) + ' not in valid range [0, ' + str(fsconfig.TOTAL_NUM_BLOCKS - 1) + ']')
            return -1
        if start < 0 or start >= fsconfig.BLOCK_SIZE:
            print('Error: start ' + str(start) + 'not in valid range [0, ' + str(fsconfig.BLOCK_SIZE - 1) + ']')
            return -1
        if end < 0 or end >= fsconfig.BLOCK_SIZE or end <= start:
            print('Error: end ' + str(end) + 'not in valid range [0, ' + str(fsconfig.BLOCK_SIZE - 1) + ']')
            return -1

        wholeblock = self.RawBlocks.Get(n)
        print('Block (raw hex block) [' + str(n) + '] : \n' + str((wholeblock[start:end + 1].hex())))
        return 0

    # file operations
    # implements cd (change directory)
    def cd(self, dir):
        i = self.AbsolutePathObject.PathNameToInodeNumber(dir, self.cwd)
        if i == -1:
            print("Error: not found\n")
            return -1
        inobj = InodeNumber(i)
        inobj.InodeNumberToInode(self.RawBlocks)
        if inobj.inode.type != fsconfig.INODE_TYPE_DIR:
            print("Error: not a directory\n")
            return -1
        self.cwd = i

    # implements ls (lists files in directory)
    def ls(self):
        inobj = InodeNumber(self.cwd)
        inobj.InodeNumberToInode(self.RawBlocks)
        block_index = 0
        while block_index <= (inobj.inode.size // fsconfig.BLOCK_SIZE):
            block = self.RawBlocks.Get(inobj.inode.block_numbers[block_index])
            if block_index == (inobj.inode.size // fsconfig.BLOCK_SIZE):
                end_position = inobj.inode.size % fsconfig.BLOCK_SIZE
            else:
                end_position = fsconfig.BLOCK_SIZE
            current_position = 0
            while current_position < end_position:
                entryname = block[current_position:current_position + fsconfig.MAX_FILENAME]
                entryinode = block[current_position + fsconfig.MAX_FILENAME:current_position + fsconfig.FILE_NAME_DIRENTRY_SIZE]
                entryinodenumber = int.from_bytes(entryinode, byteorder='big')
                inobj2 = InodeNumber(entryinodenumber)
                inobj2.InodeNumberToInode(self.RawBlocks)
                if inobj2.inode.type == fsconfig.INODE_TYPE_DIR:
                    print("[" + str(inobj2.inode.refcnt) + "]:" + entryname.decode() + "/")
                else:
                    if inobj2.inode.type == fsconfig.INODE_TYPE_SYM:
                        target_block_number = inobj2.inode.block_numbers[0]
                        target_block = self.RawBlocks.Get(target_block_number)
                        target_slice = target_block[0:inobj2.inode.size]
                        print("[" + str(inobj2.inode.refcnt) + "]:" + entryname.decode() + "@ -> " + target_slice.decode())
                    else:
                        print("[" + str(inobj2.inode.refcnt) + "]:" + entryname.decode())
                current_position += fsconfig.FILE_NAME_DIRENTRY_SIZE
            block_index += 1
        return 0

    # implements cat (print file contents)
    def cat(self, filename):
        i = self.AbsolutePathObject.PathNameToInodeNumber(filename, self.cwd)
        if i == -1:
            print("Error: not found\n")
            return -1
        inobj = InodeNumber(i)
        inobj.InodeNumberToInode(self.RawBlocks)
        if inobj.inode.type != fsconfig.INODE_TYPE_FILE:
            print("Error: not a file\n")
            return -1
        data, errorcode = self.FileOperationsObject.Read(i, 0, fsconfig.MAX_FILE_SIZE)
        if data == -1:
            print("Error: " + errorcode)
            return -1
        print(data.decode())
        return 0

    # implements mkdir
    def mkdir(self, dir):
        i, errorcode = self.FileOperationsObject.Create(self.cwd, dir, fsconfig.INODE_TYPE_DIR)
        if i == -1:
            print("Error: " + errorcode + "\n")
            return -1
        return 0

    # implements create
    def create(self, file):
        i, errorcode = self.FileOperationsObject.Create(self.cwd, file, fsconfig.INODE_TYPE_FILE)
        if i == -1:
            print("Error: " + errorcode + "\n")
            return -1
        return 0

    # implements append
    def append(self, filename, string):
        i = self.AbsolutePathObject.PathNameToInodeNumber(filename, self.cwd)
        if i == -1:
            print("Error: not found\n")
            return -1
        inobj = InodeNumber(i)
        inobj.InodeNumberToInode(self.RawBlocks)
        if inobj.inode.type != fsconfig.INODE_TYPE_FILE:
            print("Error: not a file\n")
            return -1
        written, errorcode = self.FileOperationsObject.Write(i, inobj.inode.size, bytearray(string, "utf-8"))
        if written == -1:
            print("Error: " + errorcode)
            return -1
        print("Successfully appended " + str(written) + " bytes.")
        return 0

    # implements slice filename offset count ("slice off" contents from a file starting from offset and for count bytes)
    def slice(self, filename, offset, count):
        try:
            offset = int(offset)
        except ValueError:
            print('Error: ' + offset + ' not a valid Integer')
            return -1
        try:
            count = int(count)
        except ValueError:
            print('Error: ' + count + ' not a valid Integer')
            return -1
        i = self.AbsolutePathObject.PathNameToInodeNumber(filename, self.cwd)
        if i == -1:
            print("Error: not found\n")
            return -1
        inobj = InodeNumber(i)
        inobj.InodeNumberToInode(self.RawBlocks)
        if inobj.inode.type != fsconfig.INODE_TYPE_FILE:
            print("Error: not a file\n")
            return -1
        data, errorcode = self.FileOperationsObject.Slice(i, offset, count)
        if data == -1:
            print("Error: " + errorcode)
            return -1
        return 0

    # implements mirror filename (mirror the contents of a file)
    def mirror(self, filename):
        i = self.AbsolutePathObject.PathNameToInodeNumber(filename, self.cwd)
        if i == -1:
            print("Error: not found\n")
            return -1
        inobj = InodeNumber(i)
        inobj.InodeNumberToInode(self.RawBlocks)
        if inobj.inode.type != fsconfig.INODE_TYPE_FILE:
            print("Error: not a file\n")
            return -1
        data, errorcode = self.FileOperationsObject.Mirror(i)
        if data == -1:
            print("Error: " + errorcode)
            return -1
        return 0

    # implements rm
    def rm(self, filename):
        i, errorcode = self.FileOperationsObject.Unlink(self.cwd, filename)
        if i == -1:
            print("Error: " + errorcode + "\n")
            return -1
        return 0

    # implements hard link
    def lnh(self, target, name):
        i, errorcode = self.AbsolutePathObject.Link(target, name, self.cwd)
        if i == -1:
            print("Error: " + errorcode)
            return -1
        return 0

    # implements soft link
    def lns(self, target, name):
        i, errorcode = self.AbsolutePathObject.Symlink(target, name, self.cwd)
        if i == -1:
            print("Error: " + errorcode)
            return -1
        return 0

    def repair(self, server_id):
        """
        Repairs the contents of a failed server using RAID-5 parity reconstruction.
        :param server_id: The ID of the server to repair (0-indexed)
        """
        try:
            server_id = int(server_id)
        except ValueError:
            print(f"Error: {server_id} is not a valid server ID")
            return -1

        if server_id < 0 or server_id >= fsconfig.NO_OF_SERVERS:
            print(f"Error: Server ID {server_id} is out of range (0-{fsconfig.NO_OF_SERVERS - 1})")
            return -1

        print(f"Starting repair for server {server_id}...")

        server_port = fsconfig.STARTPORT + server_id

        # Iterate over all blocks
        for block_number in range(fsconfig.TOTAL_NUM_BLOCKS):
            data_server_index, stripe_number, parity_server_index = self.RawBlocks.getServerBlockAndParity(block_number)

            # Check if this block belongs to the failed server
            if data_server_index == server_id or parity_server_index == server_id:
                print(f"Reconstructing block {block_number} on server {server_id}...")

                try:
                    # Fetch parity data
                    parity_port = fsconfig.STARTPORT + parity_server_index
                    try:
                        parity_data = self.RawBlocks.block_servers[parity_port].Get(stripe_number)
                    except ConnectionRefusedError:
                        print(f"Error: Parity server {parity_server_index} is unreachable.")
                        return -1

                    if not parity_data:
                        parity_data = bytearray(fsconfig.BLOCK_SIZE)

                    # Initialize reconstructed block with parity data
                    reconstructed_data = bytearray(parity_data)

                    # XOR with data from all other servers
                    for i in range(fsconfig.NO_OF_SERVERS):
                        if i != server_id and i != parity_server_index:
                            data_port = fsconfig.STARTPORT + i
                            try:
                                data_block = self.RawBlocks.block_servers[data_port].Get(stripe_number)
                                if data_block:
                                    reconstructed_data = bytes([x ^ y for x, y in zip(reconstructed_data, data_block)])
                            except ConnectionRefusedError:
                                print(f"Warning: Server {i} is unreachable. Skipping...")

                    # Write reconstructed data to the failed server
                    try:
                        ret = self.RawBlocks.block_servers[server_port].Put(stripe_number, reconstructed_data)
                        if ret == -1:
                            print(f"Error: Failed to write block {block_number} to server {server_id}")
                            return -1
                    except ConnectionRefusedError:
                        print(f"Error: Failed to write block {block_number} to server {server_id}. Server unreachable.")
                        return -1

                    print(f"Successfully repaired block {block_number} on server {server_id}")

                except Exception as e:
                    print(f"Error reconstructing block {block_number}: {str(e)}")
                    return -1

        print(f"Repair completed for server {server_id}")
        return 0

    ## Main interpreter loop
    def Interpreter(self):
        while (True):
            command = input("[cwd=" + str(self.cwd) + "]%")
            splitcmd = command.split()
            if len(splitcmd) == 0:
                continue
            elif splitcmd[0] == "cd":
                if len(splitcmd) != 2:
                    print ("Error: cd requires one argument")
                else:
                    self.RawBlocks.Acquire()
                    self.cd(splitcmd[1])
                    self.RawBlocks.Release()
            elif splitcmd[0] == "cat":
                if len(splitcmd) != 2:
                    print ("Error: cat requires one argument")
                else:
                    self.RawBlocks.Acquire()
                    self.cat(splitcmd[1])
                    self.RawBlocks.Release()
            elif splitcmd[0] == "ls":
                self.RawBlocks.Acquire()
                self.ls()
                self.RawBlocks.Release()
            elif splitcmd[0] == "showblock":
                if len(splitcmd) != 2:
                    print ("Error: showblock requires one argument")
                else:
                    self.showblock(splitcmd[1])
            elif splitcmd[0] == "showblockslice":
                if len(splitcmd) != 4:
                    print ("Error: showblockslice requires three arguments")
                else:
                    self.showblockslice(splitcmd[1],splitcmd[2],splitcmd[3])
            elif splitcmd[0] == "showinode":
                if len(splitcmd) != 2:
                    print ("Error: showinode requires one argument")
                else:
                    self.showinode(splitcmd[1])
            elif splitcmd[0] == "showfsconfig":
                if len(splitcmd) != 1:
                    print ("Error: showfsconfig do not require argument")
                else:
                    self.showfsconfig()
            elif splitcmd[0] == "load":
                if len(splitcmd) != 2:
                    print ("Error: load requires 1 argument")
                else:
                    self.load(splitcmd[1])
            elif splitcmd[0] == "save":
                if len(splitcmd) != 2:
                    print ("Error: save requires 1 argument")
                else:
                    self.save(splitcmd[1])
            elif splitcmd[0] == "mkdir":
                if len(splitcmd) != 2:
                    print("Error: mkdir requires one argument")
                else:
                    self.RawBlocks.Acquire()
                    self.mkdir(splitcmd[1])
                    self.RawBlocks.Release()
            elif splitcmd[0] == "create":
                if len(splitcmd) != 2:
                    print("Error: create requires one argument")
                else:
                    self.RawBlocks.Acquire()
                    self.create(splitcmd[1])
                    self.RawBlocks.Release()
            elif splitcmd[0] == "append":
                if len(splitcmd) != 3:
                    print("Error: append requires two arguments")
                else:
                    self.RawBlocks.Acquire()
                    self.append(splitcmd[1], splitcmd[2])
                    self.RawBlocks.Release()
            elif splitcmd[0] == "slice":
                if len(splitcmd) != 4:
                    print ("Error: slice requires three arguments")
                else:
                    self.RawBlocks.Acquire()
                    self.slice(splitcmd[1],splitcmd[2],splitcmd[3])
                    self.RawBlocks.Release()
            elif splitcmd[0] == "mirror":
                if len(splitcmd) != 2:
                    print("Error: mirror requires one argument")
                else:
                    self.RawBlocks.Acquire()
                    self.mirror(splitcmd[1])
                    self.RawBlocks.Release()
            elif splitcmd[0] == "rm":
                if len(splitcmd) != 2:
                    print("Error: rm requires one argument")
                else:
                    self.RawBlocks.Acquire()
                    self.rm(splitcmd[1])
                    self.RawBlocks.Release()
            elif splitcmd[0] == "lnh":
                if len(splitcmd) != 3:
                    print("Error: lnh requires two arguments")
                else:
                    self.RawBlocks.Acquire()
                    self.lnh(splitcmd[1], splitcmd[2])
                    self.RawBlocks.Release()
            elif splitcmd[0] == "lns":
                if len(splitcmd) != 3:
                    print("Error: lns requires two arguments")
                else:
                    self.RawBlocks.Acquire()
                    self.lns(splitcmd[1], splitcmd[2])
                    self.RawBlocks.Release()
            elif splitcmd[0] == "repair":
                if len(splitcmd) != 2:
                    print("Error: repair requires one argument (server ID)")
                else:
                    self.RawBlocks.Acquire()
                    self.repair(splitcmd[1])
                    self.RawBlocks.Release()
            elif splitcmd[0] == "verify":
                if len(splitcmd) != 2:
                    print("Error: verify requires one argument (block number)")
                else:
                    try:
                        block_num = int(splitcmd[1])
                        if self.RawBlocks.verifyRAID5Consistency(block_num):
                            print(f"RAID 5 consistency verified for block {block_num}")
                        else:
                            print(f"RAID 5 consistency check failed for block {block_num}")
                    except ValueError:
                        print("Error: block number must be an integer")

            elif splitcmd[0] == "exit":
                return
            else:
                print ("command " + splitcmd[0] + " not valid.\n")


