#!/usr/bin/env python

##
##  Author: Nicola Piga
##
##  Disk image mgmt tool
##

import subprocess
import argparse
import os
import losetup
import parted
import _ped
import shutil
import time
from subprocess import CalledProcessError

## Loopback device handling
def attach_loopback (target, start_offset, end_offset):
    offset = start_offset * 512
    sizelimit = (end_offset - start_offset) * 512

    losetup.get_loop_devices()
    loop = losetup.find_unused_loop_device()
    loop.mount (target, offset, sizelimit)
    return loop

def detach_loopback (loop_dev):
    loop_dev.unmount()

## Misc functions
def check_partition_index (index, max_index):
    if not 1 <= index <= max_index:
        print '%d is not a valid partition index or the partition does not exist. Aborting.' %index
        os._exit(1)

## Command functions
def execute (command):
    subprocess.check_call(command)

def create_image(args):
    sects_required=args.image_size * (2 ** 20) / 512
    try:
        out = open(args.image_name,'w')
        for i in range(sects_required):
            out.write("\0"*512)
        out.close()
    except IOError:
        print 'Error while creating the disk image. Aborting.'
        os._exit(1)
    else:
        print "Disk image %s created successfully." %args.image_name
        
    disk_image = parted.Device(args.image_name)
    logic_disk = parted.freshDisk (disk_image, 'msdos')
    logic_disk.commitToDevice()
    print 'Partition table created succesfully.'

def add_mbr(args):
    truncated_mbr_size=446
    truncated_mbr=bytearray()

    try:
        out = open(args.image_name,'r+b')
        sector = open(args.mbr_sector,'rb')
        truncated_mbr = sector.read(truncated_mbr_size)
        out.seek(0)
        out.write(truncated_mbr)
        sector.close()
        out.close()
    except IOError:
        print 'Error while loading the given MBR. Aborting.'
        os._exit(1)
    else:
        print "MBR %s loaded successfully." %args.mbr_sector


def format_partition(args):
    disk_image=parted.Device (args.image_name)
    logic_disk=parted.Disk (disk_image)
    geom=parted.Geometry (disk_image, args.sector_start, args.sector_end - args.sector_start +1)
    fs=parted.FileSystem (args.fs_type, geom)
    cons=parted.Constraint (exactGeom=geom)
    partition=parted.Partition (logic_disk, parted.PARTITION_NORMAL, fs, geom)
    logic_disk.addPartition (partition, cons)
    if logic_disk.commit() == True:
        print 'Partition created successfully.'
    else:
        print 'Error while creating the partition. Aborting'

    loop_dev = attach_loopback (args.image_name, args.sector_start, args.sector_end)
    
    try:
        if args.fs_type == 'fat32':
            execute(['mkfs.vfat','-F32','%s' %loop_dev.device])
        #else (ext2, ext3, ext4, ...)
    except CalledProcessError:
        print 'Error while formatting the partition. Aborting.'
        os._exit(1)
    else:
        print 'Parition formatted successfully as %s.' %args.fs_type
                               
    time.sleep(1)
    detach_loopback(loop_dev)
    
def active_partition(args):
   disk_image=parted.Device (args.image_name)
   logic_disk=parted.Disk (disk_image)
   check_partition_index (args.part_index, logic_disk.lastPartitionNumber)
   partition=logic_disk.partitions[args.part_index-1]
   partition.setFlag (_ped.PARTITION_BOOT)
   if logic_disk.commit() == True:
       print 'Partition no. %d sucessfully set as active.' %args.part_index
   else:
       print 'Error while trying to set an active partition. Aborting.'

def load_file(args):   
    disk_image=parted.Device (args.image_name)
    logic_disk=parted.Disk (disk_image)
    check_partition_index (args.part_index, logic_disk.lastPartitionNumber)
    partition=logic_disk.partitions[args.part_index-1]
    start_sector=partition.geometry.start
    end_sector=partition.geometry.end
    
    loop_dev = attach_loopback (args.image_name, start_sector, end_sector)
    
    fs_type=''
    if args.fs_type == 'fat32':
        fs_type='vfat'
    #else (...)
    
    try:
        execute(['mount','-t', fs_type, loop_dev.device, 'mnt/'])
        shutil.copyfile(args.file_name, 'mnt/%s' %args.file_name)
        execute(['umount', 'mnt/'])
    except CalledProcessError:
        print 'Error while mounting/umounting the partition. Aborting.'
    except IOError:
        print 'Error while copying the file %s. Aborting.' %args.file_name
    else:
        print 'File %s copied successfully.' %args.file_name
   
    time.sleep(1)
    detach_loopback (loop_dev)

## main
def main():

    # top-level parser
    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                                     description='Disk image management tool.',
                                     epilog="""Type %(prog)s <command> -h for contextual help.""")
    # shared arguments parsers
    imgname_p = argparse.ArgumentParser(add_help=False)
    imgname_p.add_argument('image_name',
                           metavar='<image name>',
                           type=str, 
                           help='Disk image file name')
    fstype_p = argparse.ArgumentParser(add_help=False)
    fstype_p.add_argument('fs_type',
                          metavar='<FS type>',
                          type=str, 
                          help='File system type')
    pindex_p = argparse.ArgumentParser(add_help=False)
    pindex_p.add_argument('part_index', 
                          metavar='<partition index>', 
                          type=int, 
                          help='The partition index')

    # subparsers
    subparsers=parser.add_subparsers(metavar='<command>', 
                                     help='One of the following')

    # 'create' command parser
    create_parser = subparsers.add_parser('create', 
                                          help='Create a disk image named <image name>', 
                                          parents=[imgname_p])
    create_parser.add_argument ('image_size', 
                                metavar='<image size>', 
                                type=int, 
                                help='Disk image size in MiB')
    create_parser.set_defaults(func=create_image)

    # 'add mbr sector' command parser
    mbr_parser = subparsers.add_parser ('mbr', 
                                        help='Insert a given mbr sector inside a given image', 
                                        parents=[imgname_p])
    mbr_parser.add_argument ('mbr_sector', 
                             metavar='<mbr sector>', 
                             type=str, 
                             help='MBR sector file name')
    mbr_parser.set_defaults(func=add_mbr)

    # 'format' command parser
    format_parser = subparsers.add_parser ('format', 
                                           help='Create a format a partition inside a given image', 
                                           parents=[imgname_p, fstype_p])
    format_parser.add_argument('sector_start', 
                               metavar='<sector start>', 
                               type=int, 
                               help='Starting sector number')
    format_parser.add_argument('sector_end', 
                               metavar='<sector end>', 
                               type=int, help='Ending sector number')
    format_parser.set_defaults(func=format_partition)

    # 'set active partition' command parser
    active_parser = subparsers.add_parser ('active', 
                                           help='Set a partition as active inside a given image', 
                                           parents=[imgname_p, pindex_p])
    active_parser.set_defaults(func=active_partition)

    # 'load file' command parser
    load_parser = subparsers.add_parser('load', 
                                        help='Load a given file inside a given image', 
                                        parents=[imgname_p, fstype_p, pindex_p])
    load_parser.add_argument('file_name', 
                             metavar='<file name>', 
                             type=str, 
                             help='The file name to be loaded')
    load_parser.set_defaults(func=load_file)

    # Get the args and call the right function
    args=parser.parse_args()
    args.func(args)

## Let's start
main()
