#! /usr/bin/env python

##
## Disk image mgmt tool
##
## Author: xEnVrE
##

import argparse
import losetup
import re
import subprocess
import shlex
import shutil

from subprocess import CalledProcessError

def execute(command):
    subprocess.check_call(shlex.split(command))

def output_execute(command):
    return subprocess.check_output(shlex.split(command))

## Misc 
def check_partition_index(index):

    max_index=4
    if not 1 <= index <= 4:
        print('{0} is not a valid partition index. Aborting.'
               .format(index))
        exit(1)

## Loopback device

def attach_loopback(target, start_offset, end_offset):
    offset=start_offset*512
    sizelimit=(end_offset - start_offset)*512

    losetup.get_loop_devices()
    loop=losetup.find_unused_loop_device()
    loop.mount(target, offset, sizelimit)
    return loop

def detach_loopback (loop_dev):
    loop_dev.unmount()

## Command functions

def create_image(args):

    ##  Image creation
    sects_required=args.image_size*(2**20)/512
    try:
        out=open(args.image_name,'w')
        for i in range(int(sects_required)):
            out.write("\0"*512)
        out.close()
    except IOError:
        print('Error while creating the disk image. Aborting.')
        exit(1)
    else:
        print('Disk image {0} created successfully.'
              .format(args.image_name))

    ##  Partition table creation
    cmd_string='parted --script {0} mklabel msdos'\
    .format(args.image_name)
    try:
        execute(cmd_string)
    except CalledProcessError:
        print('Error while creating the partition table. Aborting.')
        exit(1)
    else:
        print('Partition table created successfully.')
    
def inject(args):

    ## Data injection
    try:
        image=open(args.image_name,'r+b')
        raw_data=open(args.raw_data,'rb')
        raw_data.seek(args.raw_start_offset)
        if args.raw_trunc_length == -1:
            data_portion = raw_data.read()
        else:
            data_portion = raw_data.read(args.raw_trunc_length)
        image.seek(args.image_start_offset)
        image.write(data_portion)
        raw_data.close()
        image.close()
    except IOError:
        printf('Error while loading data. Aborting.')
        exit(1)
    else:
        print ('Injection completed successfully.')

def create_partition(args):

    ##  Partition creation
    cmd_string='parted --script {0} unit s mkpart primary {1} {2} {3}'\
    .format (args.image_name, args.fs_type,
             args.sector_start,args.sector_end)
    try:
        execute(cmd_string)
    except CalledProcessError:
        print('Error while creating the partition. Aborting.')
        exit(1)
    else:
        print('Partition created successfully.')

def format_partition(args):

    ## Create the partition first
    create_partition(args)

    ## Partition format                    
    loop_dev=attach_loopback (args.image_name,
                              args.sector_start,
                              args.sector_end)
    cmd_string=''
    if args.fs_type == 'fat32':
        cmd_string='mkfs.vfat -F32 {0}'\
        .format(loop_dev.device)
    #else (ext2, ext3, ext4, ...)                                       

    try:
        execute(cmd_string)
    except CalledProcessError:
        print('Error while formatting the partition. Aborting.')
        exit(1)
    else:
        print('Parition formatted successfully as {0}'
              .format(args.fs_type))
    finally:
        detach_loopback(loop_dev)

def active_partition(args):

    ##  Set active partition
    check_partition_index(args.part_index)
    cmd_string='parted --script {0} set {1} boot on '\
    .format (args.image_name, args.part_index)

    try:
        execute(cmd_string)
    except CalledProcessError:
        print('Error while setting partition no. {0} as active. Aborting.'
              .format(args.part_index))
        exit(1)
    else:
        print('Partitition no. {0} set as active successfully.'
              .format(args.part_index))

def print_partition_table(args):

    ## Print partition table
    cmd_string='parted {0} unit s print'\
    .format(args.image_name)

    try:
        pt_table_listing=output_execute(cmd_string).decode('utf-8')
    except CalledProcessError:
        print('Error while reading partition table. Aborting.')
        exit(1)
    else:
        print('{0}'
              .format(pt_table_listing))

    
def extract_partition_boundaries(args):

    ## Start/end sector extraction
    regex=re.compile('{0}\s+([0-9]*)s\s+([0-9]*)s'
                     .format(args.part_index))
    cmd_string='parted {0} unit s print'\
    .format(args.image_name)

    try:
        pt_table_listing=output_execute(cmd_string).decode('utf-8')
    except CalledProcessError:
        print('Error while extracting partition boundaries. Aborting.')
        exit(1)
    else:
        matches=regex.findall(pt_table_listing)
        if not matches:
            print('Partition no. {0} doesn\'t exist. Aborting.'
                  .format(args.part_index))
            exit(1)
        start_sector=int(matches[0][0])
        end_sector=int(matches[0][1])
    
    return (start_sector,end_sector)

def load_file (args):

    check_partition_index(args.part_index)

    ## Extract partition boundaries first
    (start_sector, end_sector) = extract_partition_boundaries(args)

    ## File loading
    loop_dev=attach_loopback(args.image_name,
                             start_sector,
                             end_sector)
    fs_type=''
    if args.fs_type == 'fat32':
        fs_type='vfat'
    #else (...)                                                                                                                              

    mount_path='mnt/'
    cmd_mount='mount -t {0} {1} {2}'\
    .format(fs_type,loop_dev.device,mount_path)
    cmd_umount='umount {0}'\
    .format(mount_path)

    try:
        execute(cmd_mount)
        shutil.copy(args.file_name,mount_path)
        execute(cmd_umount)
    except CalledProcessError:
        print('Error while mounting/umounting the partition. Aborting.')
        exit(1)
    except IOError:
        print('Error while copying the file {0}. Aborting.'
              .format(args.file_name))
        execute(cmd_umount)
        exit(1)
    else:
        print('File {0} copied successfully.'
              .format(args.file_name))
    finally:
        detach_loopback(loop_dev)

## main
def main():

    # top-level parser
    parser=argparse.ArgumentParser(formatter_class = argparse.RawDescriptionHelpFormatter,
                                   description='Disk image management tool.',
                                   epilog="""Type %(prog)s <command> -h for contexual help.""")
    
    #shared arguments parsers
    imgname_p=argparse.ArgumentParser(add_help=False)
    imgname_p.add_argument('image_name',
                           metavar='<image name>',
                           type=str,
                           help='Disk image file name')

    fstype_p=argparse.ArgumentParser(add_help=False)
    fstype_p.add_argument('fs_type',
                          metavar='<FS type>',
                          type=str,
                          help='File system type')

    pindex_p=argparse.ArgumentParser(add_help=False)
    pindex_p.add_argument('part_index',
                          metavar='<partition index>',
                          type=int,
                          help='Partition index')

    #subparsers
    subparsers=parser.add_subparsers(metavar='<command>',
                                      help='One of the following')

    # 'create' command parser
    create_parser=subparsers.add_parser('create',
                                          help='Create a disk image named <image name>',
                                          parents=[imgname_p])
    create_parser.add_argument('image_size',
                               metavar='<image size>',
                               type=int,
                               help='Disk image size in MiB')
    create_parser.set_defaults(func=create_image)

    # 'inject' command parser
    inject_parser=subparsers.add_parser('inject',
                                        help='Inject a given raw data file into a given image',
                                        parents=[imgname_p])
    inject_parser.add_argument('raw_data',
                               metavar='<raw data>',
                               type=str,
                               help='Raw data file name')
    inject_parser.add_argument('raw_start_offset',
                               metavar='<raw start offset>',
                               type=int,
                               help='Starting offset (in byte) of raw data')
    inject_parser.add_argument('raw_trunc_length',
                               metavar='<raw truncation length>',
                               type=int,
                               help='Length (in byte) of the portion of raw data to be injected (-1 means up to EOF)')
    inject_parser.add_argument('image_start_offset',
                               metavar='<image start offset>',
                               type=int,
                               help='Inject raw data starting from <image start offset>')
    inject_parser.set_defaults(func=inject)

    # 'format' command parser
    format_parser=subparsers.add_parser('format',
                                        help='Create and format a prtition inside a given image',
                                        parents=[imgname_p, fstype_p])
    format_parser.add_argument('sector_start',
                               metavar='<sector start>',
                               type=int,
                               help='Starting sector number')
    format_parser.add_argument('sector_end',
                               metavar='<sector end>',
                               type=int,
                               help='Ending sesctor number')
    format_parser.set_defaults(func=format_partition)

    # 'set active partition' command parser
    active_parser=subparsers.add_parser('active',
                                        help='Set a prtition as active inside a given image',
                                        parents=[imgname_p, pindex_p])
    active_parser.set_defaults(func=active_partition)

    # 'print partition table' command parser
    print_pt_parser=subparsers.add_parser('printpt',
                                          help='Print the partition table given an image',
                                          parents=[imgname_p])
    print_pt_parser.set_defaults(func=print_partition_table)

    # 'load file' command parser
    load_parser=subparsers.add_parser('load',
                                      help='Load a given file inside a given image',
                                      parents=[imgname_p, fstype_p, pindex_p])
    load_parser.add_argument('file_name',
                             metavar='<file name>',
                             type=str,
                             help='The file name to be loaded')
    load_parser.set_defaults(func=load_file)

    #Get the args and call the right function
    args=parser.parse_args()
    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()

## Entry point
main()
