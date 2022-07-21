# -*- coding: utf-8 -*-

import argparse
import hashlib
import json
import math
import os
from os import path
import re
import requests
import shlex
import signal
import struct
import sys
import threading
import time
import traceback
import types
from concurrent.futures import ThreadPoolExecutor
from CDNDrive import __version__
from CDNDrive.drivers import *
from CDNDrive.encoders import *
from CDNDrive.util import *

encoder = None
api = None

succ = True
nblocks = 0
lock = threading.Lock()

def load_api_by_prefix(s):
    global api
    global encoder

    prefix = s.split('://')[0]
    if prefix not in prefixes:
        return False
    site = prefixes[prefix]
    api = drivers[site]
    encoder = encoders[site]
    return True

def fetch_meta(s):
    url = api.meta2real(s)
    if not url: return None
    full_meta = api.image_download(url)
    if not full_meta: return None
    meta_dict = json.loads(encoder.decode(full_meta).decode("utf-8"))
    return meta_dict

def tr_download(i, block_dict, f, offset):
    global succ

    url = block_dict['url']
    for j in range(10):
        if not succ: break
        block = api.image_download(url)
        if not block:
            log(f"分块{i + 1}/{nblocks}第{j + 1}次下载失败")
            if j == 9: succ = False
            continue
        block = encoder.decode(block)
        if calc_sha1(block) == block_dict['sha1']:
            with lock:
                f.seek(offset)
                f.write(block)
            log(f"分块{i + 1}/{nblocks}下载完毕")
            break
        else:
            log(f"分块{i + 1}/{nblocks}校验未通过")
            if j == 9: succ = False
            

def download_handle(args):
    global succ
    global nblocks

    if not load_api_by_prefix(args.meta):
        log("元数据解析失败")
        return
    start_time = time.time()
    meta_dict = fetch_meta(args.meta)
    if not meta_dict:
        log("元数据解析失败")
        return

    file_name = args.file if args.file else meta_dict['filename']
    log(f"下载: {path.basename(file_name)} ({size_string(meta_dict['size'])}), 共有{len(meta_dict['block'])}个分块, 上传于{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(meta_dict['time']))}")

    if path.exists(file_name):
        if path.getsize(file_name) == meta_dict['size'] and calc_sha1(read_in_chunk(file_name)) == meta_dict['sha1']:
            log("文件已存在, 且与服务器端内容一致")
            return file_name
        if not args.force and not ask_overwrite():
            return

    log(f"线程数: {args.thread}")
    succ = True
    nblocks = len(meta_dict['block'])
    trpool = ThreadPoolExecutor(args.thread)
    hdls = []
    
    mode = "r+b" if path.exists(file_name) else "wb"
    with open(file_name, mode) as f:
        for i, block_dict in enumerate(meta_dict['block']):
            offset = block_offset(meta_dict, i)
            hdl = trpool.submit(tr_download, i, block_dict, f, offset)
            hdls.append(hdl)
            # 及时清理队列中的任务
            if len(hdls) == args.thread:    
                for h in hdls: h.result()
                hdls = []
        for h in hdls: h.result()
        if not succ: return
        f.truncate(meta_dict['size'])
    
    log(f"{path.basename(file_name)} ({size_string(meta_dict['size'])}) 下载完毕, 用时{time.time() - start_time:.1f}秒, 平均速度{size_string(meta_dict['size'] / (time.time() - start_time))}/s")
    sha1 = calc_sha1(read_in_chunk(file_name))
    if sha1 == meta_dict['sha1']:
        log("文件校验通过")
        return file_name
    else:
        log("文件校验未通过")
        return

def info_handle(args):
    if not load_api_by_prefix(args.meta):
        log("元数据解析失败")
        return
    meta_dict = fetch_meta(args.meta)
    if meta_dict:
        print_meta(meta_dict)
    else:
        log("元数据解析失败")

def interact_mode(parser, subparsers):
    subparsers.add_parser("help", help="查看帮助信息 (show this help message)").set_defaults(func=lambda _: parser.parse_args(["--help"]).func())
    subparsers.add_parser("version", help="查看程序版本 (show program's version number)").set_defaults(func=lambda _: parser.parse_args(["--version"]).func())
    subparsers.add_parser("exit", help="退出程序 (exit program)").set_defaults(func=lambda _: os._exit(0))
    parser.print_help()
    while True:
        try:
            args = shlex.split(input("CDNDrive > "))
            args = parser.parse_args(args)
            args.func(args)
        except:
            pass

def main():
    signal.signal(signal.SIGINT, lambda signum, frame: os.kill(os.getpid(), 9))
    parser = argparse.ArgumentParser(prog="cdrive", description="Make Picbeds Great Cloud Storages! (Download Only Version)", formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-v", "--version", action="version", version=f"CDNDrive version: {__version__}")
    parser.set_defaults(func=lambda x: parser.print_help())
    subparsers = parser.add_subparsers()
    
    download_parser = subparsers.add_parser("download", help="下载文件 (download a file)")
    download_parser.add_argument("meta", help="元数据地址 (meta url)")
    download_parser.add_argument("file", nargs="?", default="", help="自定义文件名 (new file name)")
    download_parser.add_argument("-f", "--force", action="store_true", help="如果存在同名文件，则强制覆盖 (force to overwrite if file exists)")
    download_parser.add_argument("-t", "--thread", default=8, type=int, help="下载线程数 (download thread number)")
    download_parser.set_defaults(func=download_handle)
    
    info_parser = subparsers.add_parser("info", help="列出元数据对应文件信息 (show meta info)")
    info_parser.add_argument("meta", help="元数据地址 (meta url)")
    info_parser.set_defaults(func=info_handle)
    
    if len(sys.argv) != 1:
        args = parser.parse_args()
        args.func(args)
    else:
        interact_mode(parser, subparsers)

if __name__ == "__main__":
    main()
