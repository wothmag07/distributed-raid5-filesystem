import pickle, logging
import fsconfig
import xmlrpc.client, socket


#### BLOCK LAYER

# global TOTAL_NUM_BLOCKS, BLOCK_SIZE, INODE_SIZE, MAX_NUM_INODES, MAX_FILENAME, INODE_NUMBER_DIRENTRY_SIZE

class DiskBlocks():
    def __init__(self):

        self.put_count = 0
        self.get_count = 0

        # initialize clientID
        if fsconfig.CID >= 0 and fsconfig.CID < fsconfig.MAX_CLIENTS:
            self.clientID = fsconfig.CID
        else:
            raise RuntimeError('Must specify valid cid')

        # initialize XMLRPC client connection to raw block server
        if fsconfig.PORT:
            PORT = fsconfig.PORT
        else:
            raise RuntimeError('Must specify port number')
        self.block_servers = {}
        for port in range(fsconfig.STARTPORT, fsconfig.STARTPORT + fsconfig.NO_OF_SERVERS):
            server_url = 'http://' + fsconfig.SERVER_ADDRESS + ':' + str(port)
            self.block_servers[port] = xmlrpc.client.ServerProxy(server_url, use_builtin_types=True)
        socket.setdefaulttimeout(fsconfig.SOCKET_TIMEOUT)

        # Track servers that have been detected as failed (at-most-once / fail-fast)
        self.failed_servers = set()

    def getServerBlockAndParity(self, block_number):
        """
        Calculate RAID 5 server mapping for a given block number.

        In RAID 5, parity is distributed across all servers. For each stripe:
        - Data blocks are stored on (N-1) servers
        - Parity block is stored on 1 server
        - Parity location rotates across servers for each stripe

        Args:
            block_number: Logical block number

        Returns:
            tuple: (data_server_index, stripe_number, parity_server_index)
        """
        # Number of data blocks per stripe (excluding parity)
        datablock_per_stripe = fsconfig.NO_OF_SERVERS - 1

        # Calculate stripe number and data block offset within the stripe
        stripe_number = block_number // datablock_per_stripe
        data_offset = block_number % datablock_per_stripe

        # Calculate which server holds parity for this stripe (rotating parity)
        parity_server_index = stripe_number % fsconfig.NO_OF_SERVERS

        # Calculate which server holds the data block
        # Create list of all servers excluding the parity server
        data_servers = [i for i in range(fsconfig.NO_OF_SERVERS) if i != parity_server_index]
        data_server_index = data_servers[data_offset]

        logging.debug(
            f"RAID 5 mapping: block_number={block_number}, stripe={stripe_number}, "
            f"data_server={data_server_index}, parity_server={parity_server_index}, "
            f"data_offset={data_offset}")

        return data_server_index, stripe_number, parity_server_index

    ## Put: interface to write a raw block of data to the block indexed by block number
    ## Blocks are padded with zeroes up to BLOCK_SIZE

    def SinglePut(self, block_number, block_data, server_proxy=None):
        if server_proxy is None:
            server_proxy = self.block_servers[fsconfig.STARTPORT]

        logging.debug(
            f'Put: block number {block_number} len {len(block_data)}\n{block_data.hex()}'
        )

        if len(block_data) > fsconfig.BLOCK_SIZE:
            logging.error(f'Put: Block larger than BLOCK_SIZE: {len(block_data)}')
            raise RuntimeError(f'Put: Block larger than BLOCK_SIZE: {len(block_data)}')

        if block_number in range(0, fsconfig.TOTAL_NUM_BLOCKS):
            # Pad block data with zeros if needed
            putdata = bytearray(block_data.ljust(fsconfig.BLOCK_SIZE, b'\x00'))

            # Call the SinglePut method on the server
            ret = server_proxy.SinglePut(block_number, putdata)

            if ret == -1:
                logging.error('Put: Server returns error')
                return -1

            return 0  # Successfully written
        else:
            logging.error(f'Put: Block out of range: {block_number}')
            raise RuntimeError(f'Put: Block out of range: {block_number}')

    def SingleGet(self, block_number, server_proxy=None):
        if server_proxy is None:
            server_proxy = self.block_servers[fsconfig.STARTPORT]

        logging.debug('Get: ' + str(block_number))

        if block_number not in range(0, fsconfig.TOTAL_NUM_BLOCKS):
            logging.error(
                f'DiskBlocks::Get: Block number {block_number} is out of range (0-{fsconfig.TOTAL_NUM_BLOCKS - 1})')
            raise RuntimeError(
                f'DiskBlocks::Get: Block number {block_number} is out of range (0-{fsconfig.TOTAL_NUM_BLOCKS - 1})')

        if not server_proxy:
            logging.error(f"Connection refused by server at port {fsconfig.STARTPORT}")
            raise RuntimeError(f"Connection refused by server at port {fsconfig.STARTPORT}")

        # Call Get() method on the server and return the data as bytearray
        data = server_proxy.SingleGet(block_number)
        return bytearray(data)

    def RAID1Put(self, block_number, block_data):
        logging.debug(f'MultiPut: Writing block number {block_number} across multiple servers')

        if len(block_data) > fsconfig.BLOCK_SIZE:
            logging.error(f'MultiPut: Block larger than BLOCK_SIZE: {len(block_data)}')
            raise RuntimeError(f'MultiPut: Block larger than BLOCK_SIZE: {len(block_data)}')

        if block_number in range(0, fsconfig.TOTAL_NUM_BLOCKS):
            putdata = bytearray(block_data.ljust(fsconfig.BLOCK_SIZE, b'\x00'))

            # Iterate over all available servers and call SinglePut on each one
            for port, server_proxy in self.block_servers.items():
                if not server_proxy:
                    logging.error(f"Connection refused by server on port {port}")
                    raise RuntimeError(f"Connection refused by server on port {port}")

                ret = server_proxy.Put(block_number, putdata)

                if ret == -1:
                    logging.error(f'MultiPut: Server on port {port} returned an error')
                    raise RuntimeError(f'MultiPut: Server on port {port} returned an error')

            return 0  # Successfully written to all servers
        else:
            logging.error(f'MultiPut: Block out of range: {block_number}')
            raise RuntimeError(f'MultiPut: Block out of range: {block_number}')

    def RAID1Get(self, block_number):
        logging.debug(f'Get: Reading block number {block_number} across multiple servers')

        if block_number not in range(0, fsconfig.TOTAL_NUM_BLOCKS):
            logging.error(f'Get: Block number {block_number} is out of range (0-{fsconfig.TOTAL_NUM_BLOCKS - 1})')
            raise IndexError(f'Block number {block_number} is out of range')

        # Iterate over all available servers and call SingleGet
        for port, server_proxy in self.block_servers.items():
            if server_proxy is None:
                logging.error(f"Connection refused by server on port {port}")
                print(f"SERVER_DISCONNECTED GET {block_number}")
                continue

            data = server_proxy.Get(block_number)  # Attempt to get data from the server
            if isinstance(data, str) and "CORRUPTED_BLOCK" in data:
                print(f"CORRUPTED_BLOCK {block_number}")
                logging.warning(f"Block {block_number} is corrupted. Attempting recovery...")
                raise ValueError("Corrupted block")
            logging.debug(f"Successfully fetched block {block_number} from server on port {port}")

            return bytearray(data)  # Return the first successful result

        # If no server succeeded, raise an error
        logging.error(f"MultiGet: Failed to retrieve block {block_number} from any server")
        raise RuntimeError(f"Failed to get block {block_number} from any server")

    def RAID4Put(self, block_number, block_data):
        logging.debug(f'Put: Writing block number {block_number} across servers')

        if block_number not in range(0, fsconfig.TOTAL_NUM_BLOCKS):
            logging.error(f'Put: Block number {block_number} is out of range (0-{fsconfig.TOTAL_NUM_BLOCKS - 1})')

        # Identify the last server (parity server)
        servers = list(self.block_servers.items())
        parity_server_port = servers[-1][0]  # Last server in the list is the parity server
        data_servers = servers[:-1]  # All servers except the last one are data servers

        # Distribute the data block across the data servers
        server_index = block_number % len(data_servers)  # Decides which data server to use
        blockno_slice = block_number // len(data_servers)  # This might change depending on how blocks are divided

        # Prepare the block data to ensure it's the correct size
        putdata = bytearray(block_data.ljust(fsconfig.BLOCK_SIZE, b'\x00'))

        # Store the data on the selected data server
        try:
            ret = data_servers[server_index][1].Put(blockno_slice, putdata)  # Assuming Put method is in server
            if ret == -1:
                logging.error(f'Put: Server on port {data_servers[server_index][0]} returned an error')
                raise Exception(f"Failed to store data on data server {server_index}")
        except ConnectionRefusedError:
            print(f"SERVER_DISCONNECTED Put {block_number}")
            return -1

        # Fetch the old parity data from the parity server, if it exists
        try:
            old_parity = self.block_servers[parity_server_port].Get(blockno_slice)
        except ConnectionRefusedError:
            print(f"SERVER_DISCONNECTED Put {block_number}")
            return -1  # Return error if parity server is down

        # If old parity data does not exist (first time storing this block), initialize it to zeros
        if old_parity is None:
            old_parity = bytearray(fsconfig.BLOCK_SIZE)

        # Subtract the old data from parity (XOR removes the old data)
        old_data = data_servers[server_index][1].Get(blockno_slice)
        parity_data = bytes([x ^ y for x, y in zip(old_parity, old_data)])

        # Add the new data to the parity (XOR adds the new data)
        parity_data = bytes([x ^ y for x, y in zip(parity_data, putdata)])

        # Store the updated parity on the parity server
        try:
            ret = self.block_servers[parity_server_port].Put(blockno_slice, parity_data)
            if ret == -1:
                logging.error(f'Put: Parity server on port {parity_server_port} returned an error')
        except ConnectionRefusedError:
            print(f"SERVER_DISCONNECTED Put {block_number}")

        logging.debug(
            f"Block {block_number} stored on Data Server {data_servers[server_index][0]} and Parity Server {parity_server_port}")
        return 0  # Successfully written to all servers

    ## Get: interface to read a raw block of data from block indexed by block number
    ## Equivalent to the textbook's BLOCK_NUMBER_TO_BLOCK(b)

    def RAID4Get(self, block_number):
        logging.debug(f'Get: Reading block number {block_number} across multiple servers')

        if block_number not in range(0, fsconfig.TOTAL_NUM_BLOCKS):
            logging.error(f'Get: Block number {block_number} is out of range (0-{fsconfig.TOTAL_NUM_BLOCKS - 1})')

        servers = list(self.block_servers.items())
        parity_server_port = servers[-1][0]  # Last server in the list is the parity server
        data_servers = servers[:-1]  # All servers except the last one are data servers

        # Assign the block data to the data servers
        server_index = block_number % len(data_servers)  # Decide which data server to use
        data_server_startport = data_servers[server_index][0]
        blockno_slice = block_number // len(data_servers)

        # Try fetching the data block from the selected data server
        try:
            data = data_servers[server_index][1].Get(blockno_slice)  # Attempt to get data from the data server
            if isinstance(data, str) and "CORRUPTED_BLOCK" in data:
                print(f"CORRUPTED_BLOCK {block_number}")
                logging.warning(f"Block {block_number} is corrupted. Attempting recovery...")
                raise ValueError("Corrupted block")
            logging.debug(
                    f"Successfully fetched block {blockno_slice} from data server on port {data_server_startport}")
            return bytearray(data)

        except ConnectionRefusedError:
            print(f"SERVER_DISCONNECTED Get {block_number}")

            # If data server is down, calculate missing data using parity
            logging.debug(
                f"Attempting to recover missing block {block_number} using parity data from parity server {parity_server_port}")

            try:
                parity_data = self.block_servers[parity_server_port].Get(blockno_slice)
                logging.debug(
                    f"Successfully fetched parity block {blockno_slice} from parity server on port {parity_server_port}")

                # Recover missing block using XOR with parity and the available data blocks
                recovered_data = bytearray(parity_data)

                # XOR all the other data blocks to recover the missing one
                for server_port, server in data_servers:
                    if server_port != data_servers[server_index][0]:  # Only XOR with the other data servers
                        try:
                            data_block = server.Get(blockno_slice)  # Fetch data from the other servers
                            recovered_data = bytes([x ^ y for x, y in zip(recovered_data, data_block)])
                        except ConnectionRefusedError:
                            print(f"SERVER_DISCONNECTED Get {block_number} during recovery")

                logging.debug(f"Successfully recovered block {block_number} from parity data")
                return bytearray(recovered_data)

            except ConnectionRefusedError:
                print(f"SERVER_DISCONNECTED Get {block_number} - Unable to recover missing data")

        return None  # Return None if all attempts fail

    def _compute_parity_from_scratch(self, stripe_number, data_server_index, parity_server_index, new_data):
        """Compute parity by XORing new_data with all other data blocks in the stripe.
        Used in degraded mode when the data server is down and we can't read old_data."""
        new_parity = bytearray(new_data)
        for i in range(fsconfig.NO_OF_SERVERS):
            if i != data_server_index and i != parity_server_index:
                port = fsconfig.STARTPORT + i
                try:
                    block = self.block_servers[port].Get(stripe_number)
                    if block and not (isinstance(block, str) and "CORRUPTED_BLOCK" in block):
                        new_parity = bytes([x ^ y for x, y in zip(new_parity, block)])
                    else:
                        logging.error(f"Cannot read valid data from server {i} during degraded write")
                        return None
                except ConnectionRefusedError:
                    self.failed_servers.add(i)
                    logging.error(f"Server {i} unreachable during degraded write")
                    return None
        return new_parity

    def Put(self, block_number, block_data):
        logging.debug(f'Put: Writing block number {block_number} using RAID 5')

        if block_number not in range(0, fsconfig.TOTAL_NUM_BLOCKS):
            logging.error(f'Put: Block number {block_number} is out of range (0-{fsconfig.TOTAL_NUM_BLOCKS - 1})')
            return -1

        data_server_index, stripe_number, parity_server_index = self.getServerBlockAndParity(block_number)
        data_server_port = fsconfig.STARTPORT + data_server_index
        parity_server_port = fsconfig.STARTPORT + parity_server_index

        putdata = bytearray(block_data.ljust(fsconfig.BLOCK_SIZE, b'\x00'))

        data_failed = data_server_index in self.failed_servers
        parity_failed = parity_server_index in self.failed_servers

        # Cannot write if both servers in the stripe are failed
        if data_failed and parity_failed:
            logging.error(f"Put: Both data server {data_server_index} and parity server {parity_server_index} are failed")
            return -1

        # --- Degraded mode: data server is known-failed ---
        if data_failed:
            print(f"SERVER_DISCONNECTED PUT {block_number}")
            # Compute new parity from scratch: XOR new_data with all other data blocks
            new_parity = self._compute_parity_from_scratch(stripe_number, data_server_index, parity_server_index, putdata)
            if new_parity is None:
                return -1
            try:
                ret = self.block_servers[parity_server_port].Put(stripe_number, new_parity)
                if ret == -1:
                    return -1
                return 0
            except ConnectionRefusedError:
                self.failed_servers.add(parity_server_index)
                print(f"SERVER_DISCONNECTED PUT {block_number}")
                return -1

        # --- Degraded mode: parity server is known-failed ---
        if parity_failed:
            print(f"SERVER_DISCONNECTED PUT {block_number}")
            # Write data only, parity will be rebuilt on repair
            try:
                ret = self.block_servers[data_server_port].Put(stripe_number, putdata)
                if ret == -1:
                    return -1
                return 0
            except ConnectionRefusedError:
                self.failed_servers.add(data_server_index)
                print(f"SERVER_DISCONNECTED PUT {block_number}")
                return -1

        # --- Normal mode: both servers available ---
        # Step 1: Read old parity
        try:
            old_parity = self.block_servers[parity_server_port].Get(stripe_number)
            if isinstance(old_parity, str) and "CORRUPTED_BLOCK" in old_parity:
                old_parity = bytearray(fsconfig.BLOCK_SIZE)
            elif old_parity is None:
                old_parity = bytearray(fsconfig.BLOCK_SIZE)
        except ConnectionRefusedError:
            # Parity server just failed - flag it and do data-only write
            self.failed_servers.add(parity_server_index)
            print(f"SERVER_DISCONNECTED PUT {block_number}")
            try:
                ret = self.block_servers[data_server_port].Put(stripe_number, putdata)
                if ret == -1:
                    return -1
                return 0
            except ConnectionRefusedError:
                self.failed_servers.add(data_server_index)
                print(f"SERVER_DISCONNECTED PUT {block_number}")
                return -1

        # Step 2: Read old data
        try:
            old_data = self.block_servers[data_server_port].Get(stripe_number)
            if isinstance(old_data, str) and "CORRUPTED_BLOCK" in old_data:
                old_data = bytearray(fsconfig.BLOCK_SIZE)
            elif old_data is None:
                old_data = bytearray(fsconfig.BLOCK_SIZE)
        except ConnectionRefusedError:
            # Data server just failed - flag it and compute parity from scratch
            self.failed_servers.add(data_server_index)
            print(f"SERVER_DISCONNECTED PUT {block_number}")
            new_parity = self._compute_parity_from_scratch(stripe_number, data_server_index, parity_server_index, putdata)
            if new_parity is None:
                return -1
            try:
                ret = self.block_servers[parity_server_port].Put(stripe_number, new_parity)
                if ret == -1:
                    return -1
                return 0
            except ConnectionRefusedError:
                self.failed_servers.add(parity_server_index)
                print(f"SERVER_DISCONNECTED PUT {block_number}")
                return -1

        # Step 3: Write new data to data server
        try:
            ret = self.block_servers[data_server_port].Put(stripe_number, putdata)
            if ret == -1:
                logging.error(f'Put: Data server {data_server_port} returned an error')
                return -1
        except ConnectionRefusedError:
            # Data server failed during write - flag it, still update parity
            self.failed_servers.add(data_server_index)
            print(f"SERVER_DISCONNECTED PUT {block_number}")
            parity_data = bytes([x ^ y ^ z for x, y, z in zip(old_parity, old_data, putdata)])
            try:
                self.block_servers[parity_server_port].Put(stripe_number, parity_data)
                return 0
            except ConnectionRefusedError:
                self.failed_servers.add(parity_server_index)
                print(f"SERVER_DISCONNECTED PUT {block_number}")
                return -1

        # Step 4: Calculate new parity: new_parity = old_parity ^ old_data ^ new_data
        parity_data = bytes([x ^ y ^ z for x, y, z in zip(old_parity, old_data, putdata)])

        # Step 5: Write the updated parity
        try:
            ret = self.block_servers[parity_server_port].Put(stripe_number, parity_data)
            if ret == -1:
                logging.error(f'Put: Parity server {parity_server_port} returned an error')
                return -1
        except ConnectionRefusedError:
            # Parity server failed after data was written - data is saved, parity is stale
            self.failed_servers.add(parity_server_index)
            print(f"SERVER_DISCONNECTED PUT {block_number}")
            # Data write succeeded, so this is still a successful write
            return 0

        logging.debug(
            f"RAID 5: Block {block_number} stored on Data Server {data_server_port} and updated Parity Server {parity_server_port}")

        return 0

    def Get(self, block_number):
        logging.debug(f'Get: Reading block number {block_number} using RAID 5')

        if block_number not in range(0, fsconfig.TOTAL_NUM_BLOCKS):
            logging.error(f'Get: Block number {block_number} is out of range (0-{fsconfig.TOTAL_NUM_BLOCKS - 1})')
            return None

        data_server_index, stripe_number, parity_server_index = self.getServerBlockAndParity(block_number)
        data_server_port = fsconfig.STARTPORT + data_server_index
        parity_server_port = fsconfig.STARTPORT + parity_server_index

        need_recovery = False

        # Step 1: Try to read from the primary data server (skip if known-failed)
        if data_server_index not in self.failed_servers:
            try:
                data = self.block_servers[data_server_port].Get(stripe_number)
                if isinstance(data, str) and "CORRUPTED_BLOCK" in data:
                    print(f"CORRUPTED_BLOCK {block_number}")
                    logging.warning(f"Block {block_number} is corrupted. Attempting recovery...")
                    need_recovery = True
                else:
                    logging.debug(f"Successfully fetched block {stripe_number} from data server on port {data_server_port}")
                    return bytearray(data)
            except ConnectionRefusedError:
                self.failed_servers.add(data_server_index)
                print(f"SERVER_DISCONNECTED GET {block_number}")
                need_recovery = True
        else:
            print(f"SERVER_DISCONNECTED GET {block_number}")
            need_recovery = True

        if not need_recovery:
            return None

        # Step 2: Recovery using parity and other data servers
        logging.debug(f"Attempting to recover block {block_number} using parity server on port {parity_server_port}")

        recovery_failures = 0

        try:
            parity_data = self.block_servers[parity_server_port].Get(stripe_number)
            if not parity_data or (isinstance(parity_data, str) and "CORRUPTED_BLOCK" in parity_data):
                logging.error(f"Failed to fetch valid parity data from parity server {parity_server_port}")
                return None

            logging.debug(f"Successfully fetched parity block {stripe_number} from parity server on port {parity_server_port}")

            # Initialize recovered data with parity
            recovered_data = bytearray(parity_data)

            # XOR with data from all other servers in the stripe
            for i in range(fsconfig.NO_OF_SERVERS):
                if i != data_server_index and i != parity_server_index:
                    server_port = fsconfig.STARTPORT + i
                    try:
                        data_block = self.block_servers[server_port].Get(stripe_number)
                        if data_block and not (isinstance(data_block, str) and "CORRUPTED_BLOCK" in data_block):
                            recovered_data = bytes([x ^ y for x, y in zip(recovered_data, data_block)])
                        else:
                            logging.warning(f"No valid data from server {i} for stripe {stripe_number}")
                            recovery_failures += 1
                    except ConnectionRefusedError:
                        self.failed_servers.add(i)
                        logging.warning(f"Server {i} is unreachable during recovery")
                        recovery_failures += 1

            if recovery_failures > 0:
                logging.error(
                    f"RAID 5 recovery failed: {recovery_failures} additional server(s) unreachable during "
                    f"recovery of block {block_number}. Cannot recover from 2+ failures in a stripe.")
                return None

            logging.debug(f"Successfully recovered block {block_number} using parity data")
            return bytearray(recovered_data)

        except ConnectionRefusedError:
            self.failed_servers.add(parity_server_index)
            print(f"SERVER_DISCONNECTED GET {block_number}")
            logging.error(f"Parity server on port {parity_server_port} is unavailable")
            return None

    def verifyRAID5Consistency(self, block_number):
        """
        Verify that RAID 5 parity is consistent for a given block.

        Args:
            block_number: Logical block number to verify

        Returns:
            bool: True if consistent, False otherwise
        """
        data_server_index, stripe_number, parity_server_index = self.getServerBlockAndParity(block_number)

        # Get all data blocks in this stripe
        stripe_data = []
        for i in range(fsconfig.NO_OF_SERVERS):
            if i != parity_server_index:
                server_port = fsconfig.STARTPORT + i
                try:
                    data = self.block_servers[server_port].Get(stripe_number)
                    if data:
                        stripe_data.append(data)
                    else:
                        stripe_data.append(bytearray(fsconfig.BLOCK_SIZE))
                except ConnectionRefusedError:
                    logging.warning(f"Server {i} unreachable during consistency check")
                    stripe_data.append(bytearray(fsconfig.BLOCK_SIZE))

        # Calculate expected parity
        expected_parity = bytearray(fsconfig.BLOCK_SIZE)
        for data in stripe_data:
            expected_parity = bytes([x ^ y for x, y in zip(expected_parity, data)])

        # Get actual parity
        parity_port = fsconfig.STARTPORT + parity_server_index
        try:
            actual_parity = self.block_servers[parity_port].Get(stripe_number)
            if not actual_parity:
                actual_parity = bytearray(fsconfig.BLOCK_SIZE)
        except ConnectionRefusedError:
            logging.error(f"Parity server {parity_server_index} unreachable during consistency check")
            return False

        # Compare
        if expected_parity == actual_parity:
            logging.debug(f"RAID 5 consistency verified for block {block_number}")
            return True
        else:
            logging.error(f"RAID 5 consistency check failed for block {block_number}")
            return False

    def verifyAllRAID5Consistency(self):
        """
        Verify RAID 5 parity consistency for all unique stripes.

        Iterates through all stripes and checks that the XOR of all data blocks
        in each stripe equals the stored parity block.

        Returns:
            bool: True if all stripes are consistent, False otherwise
        """
        datablock_per_stripe = fsconfig.NO_OF_SERVERS - 1
        total_stripes = (fsconfig.TOTAL_NUM_BLOCKS + datablock_per_stripe - 1) // datablock_per_stripe
        all_consistent = True

        checked_stripes = set()
        for block_number in range(fsconfig.TOTAL_NUM_BLOCKS):
            _, stripe_number, parity_server_index = self.getServerBlockAndParity(block_number)
            stripe_key = (stripe_number, parity_server_index)
            if stripe_key in checked_stripes:
                continue
            checked_stripes.add(stripe_key)

            if not self.verifyRAID5Consistency(block_number):
                logging.error(f"Consistency check failed for stripe {stripe_number} "
                              f"(parity server index {parity_server_index})")
                all_consistent = False

        if all_consistent:
            logging.info("All RAID 5 stripes passed consistency check")
        else:
            logging.error("One or more RAID 5 stripes failed consistency check")

        return all_consistent

    ## RSM: read and set memory equivalent
    ## Single-client design: RSM always returns success (unlocked) without contacting the server.
    ## Since there is only one client, mutual exclusion is guaranteed by design.

    def RSM(self, block_number):
        logging.debug('RSM: ' + str(block_number))
        if block_number in range(0, fsconfig.TOTAL_NUM_BLOCKS):
            # Single-client: no need to contact the server, just return unlocked
            return bytearray(fsconfig.RSM_UNLOCKED.ljust(fsconfig.BLOCK_SIZE, b'\x00'))

        logging.error('RSM: Block number larger than TOTAL_NUM_BLOCKS: ' + str(block_number))
        raise RuntimeError('RSM: Block number larger than TOTAL_NUM_BLOCKS: ' + str(block_number))

        ## Acquire and Release using a disk block lock

    def Acquire(self):
        # Single-client design: no locking needed, return immediately
        logging.debug('Acquire: no-op (single client)')
        return 0

    def Release(self):
        # Single-client design: no locking needed, return immediately
        logging.debug('Release: no-op (single client)')
        return 0

    ## Serializes and saves the DiskBlocks block[] data structure to a "dump" file on your disk

    def DumpToDisk(self, filename):

        logging.info("DiskBlocks::DumpToDisk: Dumping pickled blocks to file " + filename)
        # Collect all blocks via self.Get() into a list
        all_blocks = []
        for i in range(0, fsconfig.TOTAL_NUM_BLOCKS):
            all_blocks.append(self.Get(i))
        file_system_constants = "BS_" + str(fsconfig.BLOCK_SIZE) + "_NB_" + str(
            fsconfig.TOTAL_NUM_BLOCKS) + "_IS_" + str(fsconfig.INODE_SIZE) \
                                + "_MI_" + str(fsconfig.MAX_NUM_INODES) + "_MF_" + str(
            fsconfig.MAX_FILENAME) + "_IDS_" + str(fsconfig.INODE_NUMBER_DIRENTRY_SIZE)
        with open(filename, 'wb') as file:
            pickle.dump(file_system_constants, file)
            pickle.dump(all_blocks, file)

    ## Loads DiskBlocks block[] data structure from a "dump" file on your disk

    def LoadFromDump(self, filename):

        logging.info("DiskBlocks::LoadFromDump: Reading blocks from pickled file " + filename)
        file_system_constants = "BS_" + str(fsconfig.BLOCK_SIZE) + "_NB_" + str(
            fsconfig.TOTAL_NUM_BLOCKS) + "_IS_" + str(fsconfig.INODE_SIZE) \
                                + "_MI_" + str(fsconfig.MAX_NUM_INODES) + "_MF_" + str(
            fsconfig.MAX_FILENAME) + "_IDS_" + str(fsconfig.INODE_NUMBER_DIRENTRY_SIZE)

        try:
            with open(filename, 'rb') as file:
                read_file_system_constants = pickle.load(file)
                if file_system_constants != read_file_system_constants:
                    print(
                        'DiskBlocks::LoadFromDump Error: File System constants of File :' + read_file_system_constants + ' do not match with current file system constants :' + file_system_constants)
                    return -1
                block = pickle.load(file)
                for i in range(0, fsconfig.TOTAL_NUM_BLOCKS):
                    self.Put(i, block[i])
                return 0
        except TypeError:
            print("DiskBlocks::LoadFromDump: Error: File not in proper format, encountered type error ")
            return -1
        except EOFError:
            print("DiskBlocks::LoadFromDump: Error: File not in proper format, encountered EOFError error ")
            return -1

    ## Prints to screen block contents, from min to max

    def PrintBlocks(self, tag, min, max):
        print('#### Raw disk blocks: ' + tag)
        for i in range(min, max):
            print('Block [' + str(i) + '] : ' + str((self.Get(i)).hex()))
