import fsconfig
import logging
from inode import Inode
from inodenumber import InodeNumber
from filename import FileName


## This class implements methods for absolute path layer


class AbsolutePathName:
    def __init__(self, FileNameObject, RawBlocks):
        self.FileNameObject = FileNameObject
        self.RawBlocks = RawBlocks

    ## Maximum depth for symlink resolution to prevent infinite loops
    MAX_SYMLINK_DEPTH = 10

    def _ResolveSymlink(self, inode_number, depth=0):
        """If inode_number points to a symlink, follow the target and return the final inode number.
        Returns the inode number of the resolved target, or -1 on error."""
        if depth > self.MAX_SYMLINK_DEPTH:
            logging.error("AbsolutePathName::_ResolveSymlink: too many levels of symlinks")
            return -1

        inobj = InodeNumber(inode_number)
        inobj.InodeNumberToInode(self.RawBlocks)

        if inobj.inode.type != fsconfig.INODE_TYPE_SYM:
            return inode_number

        # Read the symlink target path from the first data block
        target_block = self.RawBlocks.Get(inobj.inode.block_numbers[0])
        target_path = target_block[0:inobj.inode.size].decode("utf-8")
        logging.debug("AbsolutePathName::_ResolveSymlink: following symlink -> " + target_path)

        # Resolve the target path (could be absolute or relative)
        resolved = self.GeneralPathToInodeNumber(target_path, 0)
        if resolved == -1:
            return -1

        # Target could itself be a symlink, resolve recursively
        return self._ResolveSymlink(resolved, depth + 1)

    def PathToInodeNumber(self, path, dir):

        logging.debug(
            "AbsolutePathName::PathToInodeNumber: path: "
            + str(path)
            + ", dir: "
            + str(dir)
        )

        if "/" in path:
            split_path = path.split("/")
            first = split_path[0]
            del split_path[0]
            rest = "/".join(split_path)
            logging.debug(
                "AbsolutePathName::PathToInodeNumber: first: "
                + str(first)
                + ", rest: "
                + str(rest)
            )
            d = self.FileNameObject.Lookup(first, dir)
            if d == -1:
                return -1
            # Resolve symlinks for intermediate path components
            d = self._ResolveSymlink(d)
            if d == -1:
                return -1
            return self.PathToInodeNumber(rest, d)
        else:
            d = self.FileNameObject.Lookup(path, dir)
            if d == -1:
                return -1
            # Resolve symlinks for the final path component
            return self._ResolveSymlink(d)

    def GeneralPathToInodeNumber(self, path, cwd):

        if not path:
            return -1

        logging.debug(
            "AbsolutePathName::GeneralPathToInodeNumber: path: "
            + str(path)
            + ", cwd: "
            + str(cwd)
        )

        if path[0] == "/":
            if len(path) == 1:  # special case: root
                logging.debug(
                    "AbsolutePathName::GeneralPathToInodeNumber: returning root inode 0"
                )
                return 0
            cut_path = path[1 : len(path)]
            logging.debug(
                "AbsolutePathName::GeneralPathToInodeNumber: cut_path: " + str(cut_path)
            )
            return self.PathToInodeNumber(cut_path, 0)
        else:
            return self.PathToInodeNumber(path, cwd)

    def Link(self, target, name, cwd):
        logging.debug(
            "AbsolutePathName::Link: target="
            + target
            + ", name="
            + name
            + ", cwd="
            + str(cwd)
        )

        # Get the Inode of the Target
        # target_inode = self.FileNameObject.Lookup(target, cwd)

        target_inode = self.GeneralPathToInodeNumber(target, cwd)  # for absolute path
        # Check if the Target Exists

        if target_inode == -1:
            return -1, "ERROR_LINK_TARGET_DOESNOT_EXIST"

        # Get the Current Working Directory Inode
        cwd_inode = InodeNumber(cwd)
        cwd_inode.InodeNumberToInode(self.RawBlocks)

        # Check if CWD is a Directory
        if cwd_inode.inode.type != fsconfig.INODE_TYPE_DIR:
            return -1, "ERROR_LINK_NOT_DIRECTORY"

        # Check for Available Space
        if (
            cwd_inode.inode.size + fsconfig.FILE_NAME_DIRENTRY_SIZE
            > fsconfig.MAX_FILE_SIZE
        ):
            return -1, "ERROR_LINK_DATA_BLOCK_NOT_AVAILABLE"

        # Check for Existing Entry
        existing_entry = self.FileNameObject.Lookup(name, cwd)
        if existing_entry != -1:
            return -1, "ERROR_LINK_ALREADY_EXISTS"

        # Get the Target Inode Object
        target_inode_obj = InodeNumber(target_inode)
        target_inode_obj.InodeNumberToInode(self.RawBlocks)

        # Check if Target is a File
        if target_inode_obj.inode.type != fsconfig.INODE_TYPE_FILE:
            return -1, "ERROR_LINK_TARGET_NOT_FILE"

        # Insert the New Link Entry
        self.FileNameObject.InsertFilenameInodeNumber(cwd_inode, name, target_inode)

        # Increment Reference Count
        target_inode_obj.inode.refcnt += 1
        target_inode_obj.StoreInode(self.RawBlocks)

        return 0, "LINK CREATED"

    def Symlink(self, target, name, cwd):
        logging.debug(
            "AbsolutePathName::Symlink: target = {}, name = {}, cwd = {}".format(
                target, name, cwd
            )
        )

        # Check if the target exists
        # target_inode = self.FileNameObject.Lookup(target, cwd)
        target_inode = self.GeneralPathToInodeNumber(target, cwd)

        if target_inode == -1:
            return -1, "ERROR_SYMLINK_TARGET_DOESNOT_EXIST"

        # Get the Current Working Directory Inode
        cwd_inode = InodeNumber(cwd)
        cwd_inode.InodeNumberToInode(self.RawBlocks)

        # Check if the cwd is a directory
        if cwd_inode == -1 or cwd_inode.inode.type != fsconfig.INODE_TYPE_DIR:
            return -1, "ERROR_SYMLINK_NOT_DIRECTORY"

        # Check if there is space for another entry in the cwd
        if cwd_inode.inode.size >= fsconfig.MAX_FILE_SIZE:
            return -1, "ERROR_SYMLINK_DATA_BLOCK_NOT_AVAILABLE"

        # Check if the name already exists in cwd
        existing_entry = self.FileNameObject.Lookup(name, cwd)
        if existing_entry != -1:
            return -1, "ERROR_SYMLINK_ALREADY_EXISTS"

        # Check if there are free inodes available
        free_inode_number = self.FileNameObject.FindAvailableInode()
        if free_inode_number == -1:
            return -1, "ERROR_SYMLINK_INODE_NOT_AVAILABLE"

        # Check if target exceeds block size
        # Convert target to a bytearray
        target_data = bytearray(target, "utf-8")
        if len(target_data) > fsconfig.BLOCK_SIZE:
            return -1, "ERROR_SYMLINK_TARGET_EXCEEDS_BLOCK_SIZE"

        # Allocate a new inode for the symlink
        symlink_inode = InodeNumber(free_inode_number)
        symlink_inode.inode.type = fsconfig.INODE_TYPE_SYM
        symlink_inode.inode.size = len(target_data)
        symlink_inode.inode.refcnt = 1

        # Store the target string in the first data block
        symlink_inode.inode.block_numbers[0] = self.FileNameObject.AllocateDataBlock()
        block = self.RawBlocks.Get(symlink_inode.inode.block_numbers[0])
        # Prepare the block
        block[: len(target_data)] = target_data
        # Fill the rest of the block with zeros if needed
        block[len(target_data) :] = bytearray(
            b"\x00" * (fsconfig.BLOCK_SIZE - len(target_data))
        )  # Pad if necessary
        self.RawBlocks.Put(symlink_inode.inode.block_numbers[0], block)

        # Insert the symlink into the cwd directory
        result = self.FileNameObject.InsertFilenameInodeNumber(
            cwd_inode, name, free_inode_number
        )
        if result is not None:
            return -1, str(result)

        # Store the inode in raw storage
        symlink_inode.StoreInode(self.RawBlocks)

        return 0, "SYMLINK_CREATED"
