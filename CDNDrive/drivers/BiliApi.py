# -*- coding: utf-8 -*-

import base64
import hashlib
import random
import requests
import rsa
import time
import re
from urllib import parse
from CDNDrive.util import *
from .BaseApi import BaseApi

class BiliApi(BaseApi):
    app_key = "1d8b6e7d45233436"

    default_hdrs = {'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.182 Safari/537.36"}
    
    default_url = lambda self, sha1: f"http://i0.hdslb.com/bfs/album/{sha1}.png"
    extract_hash = lambda self, s: re.findall(r"[a-fA-F0-9]{40}", s)[0]    
    get_cookies = lambda self: self.cookies
    
    def __init__(self):
        super().__init__()
        self.cookies = load_cookies('bili')
        
    def meta2real(self, url):
        if re.match(r"^bdex://[a-fA-F0-9]{40}$", url):
            return self.default_url(self.extract_hash(url))
        elif re.match(r"^bdrive://[a-fA-F0-9]{40}$", url):
            return self.default_url(self.extract_hash(url)) \
                       .replace('.png', '.x-ms-bmp')
        else:
            return None
            
    def real2meta(self, url):
        if re.match(r"^https?://i0.hdslb.com/bfs/album/[a-fA-F0-9]{40}.png$", url):
            return "bdex://" + self.extract_hash(url)
        else:
            return None
        

    def set_cookies(self, cookie_str):
        self.cookies = parse_cookies(cookie_str)
        save_cookies('bili', self.cookies)
            

    @staticmethod
    def CalcSign(data):
        parms = ''
        for value in data:
            parms = parms + str(value) + '=' + str(data[value]) + '&'

        parms = parms[:-1] + '59b43e04ad6965f34319062b478f83dd'
        sign = hashlib.md5(parms.encode('utf-8')).hexdigest()
        parms = parms[:-len('59b43e04ad6965f34319062b478f83dd')] + '&sign=' + sign
        return parms
    
        
    # 登录
    
    def bili_tv_Login(self):
        url = 'http://passport.bilibili.com/x/passport-tv-login/qrcode/auth_code'
        nosign_data = {'appkey':'4409e2ce8ffd12b8', 
         'local_id':'0', 
         'ts':int(time.time())}
        signed_data = self.CalcSign(nosign_data)
        res = json.loads(requests.post(url + '?' + signed_data).text)
        qrcode_url = res['data']['url']
        auth_code = res['data']['auth_code']
        print('复制此网址到浏览器登录')
        print(qrcode_url)
        while 1:
            time.sleep(1)
            url = 'https://passport.bilibili.com/x/passport-tv-login/qrcode/poll'
            nosign_data = {'appkey':'4409e2ce8ffd12b8', 
             'auth_code':auth_code, 
             'local_id':'0', 
             'ts':int(time.time())}
            signed_data = self.CalcSign(nosign_data)
            res = json.loads(requests.post(url + '?' + signed_data).text)
            if res['code'] == 0:
                return res


    def login(self):
        res = self.bili_tv_Login()
        b_cookies = {'DedeUserID':str(res['data']['token_info']['mid']), 
         'SESSDATA':res['data']['cookie_info']['cookies'][0]['value']}
        save_cookies('bili',b_cookies)
        uid = res['data']['token_info']['mid']
        self.cookies = load_cookies('bili')
        return res


    # 获取用户信息
    def get_user_info(self, fmt=True):
        url = f"https://api.bilibili.com/x/space/myinfo"
        headers = BiliApi.default_hdrs.copy()
        headers.update({
            'Referer': f"https://space.bilibili.com",
        })
        
        try:
            j = request_retry(
                "get", url, 
                headers=headers, 
                cookies=self.cookies
            ).json()
        except:
            return

        if j['code'] != 0: return
        
        info = {
            'ban': False,
            'coins': 0,
            'experience': {
                'current': 0,
                'next': 0,
            },
            'face': "",
            'level': 0,
            'nickname': "",
            'uid': 0,
        }
        info['ban'] = bool(j['data']['silence'])
        info['coins'] = j['data']['coins']
        info['experience']['current'] = j['data']['level_exp']['current_exp']
        info['experience']['next'] = j['data']['level_exp']['next_exp']
        info['face'] = j['data']['face']
        info['level'] = j['data']['level']
        info['nickname'] = j['data']['name']
        info['uid'] = j['data']['mid']
        
        if fmt:
            return f"{info['nickname']}(UID={info['uid']}), Lv.{info['level']}({info['experience']['current']}/{info['experience']['next']}), 拥有{info['coins']}枚硬币, 账号{'状态正常' if not info['ban'] else '被封禁'}"
        else:
            return info
            
    
    # 图片是否已存在
    def exist(self, sha1):
        url = self.default_url(sha1)
        try:
            r = request_retry('HEAD', url, headers=BiliApi.default_hdrs)
        except:
            return
        return url if r.status_code == 200 else None
        
    def image_upload(self, data):
        sha1 = calc_sha1(data)
        url = self.exist(sha1)
        if url: return {'code': 0, 'data': url}
        
        url = "https://api.vc.bilibili.com/api/v1/drawImage/upload"
        headers = BiliApi.default_hdrs.copy()
        headers.update({
            'Origin': "https://t.bilibili.com",
            'Referer': "https://t.bilibili.com/",
        })
        files = {
            'file_up': (f"{int(time.time() * 1000)}.png", data),
        }
        data = {
            'biz': "draw",
            'category': "daily",
        }
        try:
            r = request_retry(
                'POST', url, data=data, 
                headers=headers, 
                cookies=self.cookies, 
                files=files, timeout=300
            )
        except Exception as ex:
            return {'code': 114514, 'message': str(ex)}
            
        if r.status_code != 200:
            return {
                'code': r.status_code, 
                'message': f'HTTP {r.status_code}'
            }
        j = r.json()
        if j['code'] == 0:
            j['data'] = j['data']['image_url']
        return j
