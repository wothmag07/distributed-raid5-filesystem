import hashlib
import pickle, logging
import argparse
import time
import fsconfig

from xmlrpc.server import SimpleXMLRPCServer
from xmlrpc.server import SimpleXMLRPCRequestHandler


# Restrict to a particular path.
class RequestHandler(SimpleXMLRPCRequestHandler):
    rpc_paths = ('/RPC2',)


class DiskBlocks():
    def __init__(self, total_num_blocks, block_size, delayat):
        # This class stores the raw block array
        self.block = []
        self.checksum = []
        # initialize request counter
        self.counter = 0
        self.delayat = delayat
        # Initialize raw blocks
        for i in range(0, total_num_blocks):
            putdata = bytearray(block_size)
            self.block.insert(i, putdata)
            self.checksum.insert(i, self.compute_checksum(putdata))

    def compute_checksum(self, block_data):
        return hashlib.md5(block_data).hexdigest()

    def Sleep(self):
        self.counter += 1
        if (self.counter % self.delayat) == 0:
            time.sleep(10)


if __name__ == "__main__":


    # Construct the argument parser
    ap = argparse.ArgumentParser()

    ap.add_argument('-nb', '--total_num_blocks', type=int, help='an integer value')
    ap.add_argument('-bs', '--block_size', type=int, help='an integer value')
    ap.add_argument('-port', '--port', type=int, help='an integer value')
    ap.add_argument('-delayat', '--delayat', type=int, help='an integer value')
    ap.add_argument('-cblk', '--corrupted_block', type=int, help='an integer value (optional)')

    args = ap.parse_args()

    if args.total_num_blocks:
        TOTAL_NUM_BLOCKS = args.total_num_blocks
    else:
        print('Must specify total number of blocks')
        quit()

    if args.block_size:
        BLOCK_SIZE = args.block_size
    else:
        print('Must specify block size')
        quit()

    if args.port:
        PORT = args.port
    else:
        print('Must specify port number')
        quit()

    if args.delayat:
        delayat = args.delayat
    else:
        # initialize delayat with artificially large number
        delayat = 1000000000


    # initialize blocks
    RawBlocks = DiskBlocks(TOTAL_NUM_BLOCKS, BLOCK_SIZE, delayat)

    # Create server
    server = SimpleXMLRPCServer(("127.0.0.1", PORT), requestHandler=RequestHandler)


    def Get(block_number):
        if block_number < 0 or block_number >= len(RawBlocks.block):
            raise ValueError(f"Block {block_number} out of range")

        # Simulate corruption if corrupted_block matches
        if args.corrupted_block is not None and block_number == args.corrupted_block:
            logging.warning(f"Simulating corruption for block {block_number}")
            return f"CORRUPTED_BLOCK {block_number}"

        result = RawBlocks.block[block_number]
        block_checksum = RawBlocks.compute_checksum(result)
        expected_checksum = RawBlocks.checksum[block_number]

        # Check if the checksum matches
        if block_checksum != expected_checksum:
            logging.error(f"Checksum mismatch for block {block_number}")
            return f"CORRUPTED_BLOCK {block_number}"

        RawBlocks.Sleep()
        return result

    def SingleGet(block_number):
        """SingleGet method for compatibility with RAID implementations"""
        return Get(block_number)


    server.register_function(Get)


    def Put(block_number, data):
        if block_number < 0 or block_number >= len(RawBlocks.block):
            raise ValueError(f"Block {block_number} out of range")
        RawBlocks.block[block_number] = data.data
        RawBlocks.checksum[block_number] = RawBlocks.compute_checksum(data.data)
        RawBlocks.Sleep()
        return 0

    def SinglePut(block_number, data):
        """SinglePut method for compatibility with RAID implementations"""
        return Put(block_number, data)


    server.register_function(Put)
    server.register_function(SinglePut)
    server.register_function(SingleGet)


    def RSM(block_number):
        RSM_LOCKED = bytearray(b'\x01') * 1
        result = RawBlocks.block[block_number]
        # RawBlocks.block[block_number] = RSM_LOCKED
        RawBlocks.block[block_number] = bytearray(RSM_LOCKED.ljust(BLOCK_SIZE, b'\x01'))
        RawBlocks.Sleep()
        return result


    server.register_function(RSM)

    # Run the server's main loop
    print("Running block server with nb=" + str(TOTAL_NUM_BLOCKS) + ", bs=" + str(BLOCK_SIZE) + " on port " + str(PORT))
    server.serve_forever()
