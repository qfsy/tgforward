import os
import socks
import shutil
import random
import time
import httpx
import json
import re
import asyncio
from telethon import TelegramClient, functions
from telethon.tl.types import MessageMediaPhoto
from telethon.sessions import StringSession
from telethon.tl.functions.channels import JoinChannelRequest

if os.environ.get("HTTP_PROXY"):
    http_proxy_list = os.environ["HTTP_PROXY"].split(":")

class TGForwarder:
    def __init__(self, api_id, api_hash, string_session, channels_to_monitor, groups_to_monitor, forward_to_channel,
                 limit, replies_limit, kw, ban, only_send, nokwforwards, fdown, download_folder, proxy, checknum, linkvalidtor):
        self.checkbox = {}
        self.checknum = checknum
        self.history = 'history.json'
        self.pattern = r"(?:链接：\s*)?(https?://[^\s]+|magnet:.+)"
        self.api_id = api_id
        self.api_hash = api_hash
        self.string_session = string_session
        self.channels_to_monitor = channels_to_monitor
        self.groups_to_monitor = groups_to_monitor
        self.forward_to_channel = forward_to_channel
        self.limit = limit
        self.replies_limit = replies_limit
        self.kw = kw
        self.ban = ban
        self.linkvalidtor = linkvalidtor
        self.only_send = only_send
        self.nokwforwards = nokwforwards
        self.fdown = fdown
        self.download_folder = download_folder
        if not proxy:
            self.client = TelegramClient(StringSession(string_session), api_id, api_hash)
        else:
            self.client = TelegramClient(StringSession(string_session), api_id, api_hash, proxy=proxy)

    def random_wait(self, min_ms, max_ms):
        min_sec = min_ms / 1000
        max_sec = max_ms / 5000
        wait_time = random.uniform(min_sec, max_sec)
        time.sleep(wait_time)

    def contains(self, s, kw):
        return any(k in s for k in kw)

    def nocontains(self, s, ban):
        return not any(k in s for k in ban)

    async def send(self, message, target_chat_name):
        if self.fdown and message.media and isinstance(message.media, MessageMediaPhoto):
            media = await message.download_media(self.download_folder)
            await self.client.send_file(target_chat_name, media, caption=message.message)
        else:
            await self.client.send_message(target_chat_name, message.message)

    async def get_peer(self, client, channel_name):
        peer = None
        try:
            peer = await client.get_input_entity(channel_name)
        except Exception as e:
            print(f"Unexpected error: {e}")
        finally:
            return peer

    async def get_all_replies(self, chat_name, message):
        offset_id = 0
        all_replies = []
        peer = await self.get_peer(self.client, chat_name)
        if peer is None:
            return []
        while True:
            try:
                replies = await self.client(functions.messages.GetRepliesRequest(
                    peer=peer,
                    msg_id=message.id,
                    offset_id=offset_id,
                    offset_date=None,
                    add_offset=0,
                    limit=100,
                    max_id=0,
                    min_id=0,
                    hash=0
                ))
                all_replies.extend(replies.messages)
                if len(replies.messages) < 100:
                    break
                offset_id = replies.messages[-1].id
            except Exception as e:
                print(f"Unexpected error while fetching replies: {e.__class__.__name__} {e}")
                break
        return all_replies

    async def forward_messages(self, chat_name, target_chat_name):
        global total
        links = self.checkbox.get('links', [])
        sizes = self.checkbox.get('sizes', [])
        try:
            await self.client(JoinChannelRequest(chat_name))
            chat = await self.client.get_entity(chat_name)
            messages = self.client.iter_messages(chat, limit=self.limit)
            async for message in messages:
                self.random_wait(200, 1000)
                forwards = message.forwards
                if message.media:
                    if hasattr(message.document, 'mime_type') and self.contains(message.document.mime_type, 'video') and self.nocontains(message.message, self.ban):
                        if forwards:
                            size = message.document.size
                            if size not in sizes:
                                await self.client.forward_messages(target_chat_name, message)
                                sizes.append(size)
                                total += 1
                            else:
                                print(f'视频已经存在，size: {size}')
                    elif self.contains(message.message, self.kw) and message.message and self.nocontains(message.message, self.ban):
                        matches = re.findall(self.pattern, message.message)
                        if matches:
                            link = matches[0]
                            if link not in links:
                                link_ok = True if not self.linkvalidtor else False
                                if self.linkvalidtor:
                                    result = await self.netdisklinkvalidator(matches)
                                    for r in result:
                                        if r[1]:
                                            link_ok = True
                                if forwards and not self.only_send and link_ok:
                                    await self.client.forward_messages(target_chat_name, message)
                                    total += 1
                                    links.append(link)
                                elif link_ok:
                                    await self.send(message, target_chat_name)
                                    total += 1
                                    links.append(link)
                            else:
                                print(f'链接已存在，link: {link}')
                    elif self.nokwforwards and message.message and self.nocontains(message.message, self.ban):
                        replies = await self.get_all_replies(chat_name, message)
                        replies = replies[-self.replies_limit:]
                        for r in replies:
                            if hasattr(r.document, 'mime_type') and self.contains(r.document.mime_type, 'video') and self.nocontains(r.message, self.ban):
                                size = r.document.size
                                if size not in sizes:
                                    await self.client.forward_messages(target_chat_name, r)
                                    total += 1
                                    sizes.append(size)
                                else:
                                    print(f'视频已经存在，size: {size}')
                            elif self.contains(r.message, self.kw) and r.message and self.nocontains(r.message, self.ban):
                                matches = re.findall(self.pattern, r.message)
                                if matches:
                                    link = matches[0]
                                    if link not in links:
                                        link_ok = True if not self.linkvalidtor else False
                                        if self.linkvalidtor:
                                            result = await self.netdisklinkvalidator(matches)
                                            for r in result:
                                                if r[1]:
                                                    link_ok = r[1]
                                        if forwards and not self.only_send and link_ok:
                                            await self.client.forward_messages(target_chat_name, r)
                                            total += 1
                                            links.append(link)
                                        elif link_ok:
                                            await self.send(r, target_chat_name)
                                            total += 1
                                            links.append(link)
                                    else:
                                        print(f'链接已存在，link: {link}')

            self.checkbox['links'] = links
            self.checkbox['sizes'] = sizes
            print(f"从 {chat_name} 转发资源到 {self.forward_to_channel} total: {total}")
        except Exception as e:
            print(f"从 {chat_name} 转发资源到 {self.forward_to_channel} 失败: {e}")

    async def checkhistory(self):
        links = []
        sizes = []
        if os.path.exists(self.history):
            with open(self.history, 'r', encoding='utf-8') as f:
                self.checkbox = json.loads(f.read())
                links = self.checkbox.get('links', [])
                sizes = self.checkbox.get('sizes', [])
        else:
            self.checknum = 5000
        chat = await self.client.get_entity(self.forward_to_channel)
        messages = self.client.iter_messages(chat, limit=self.checknum)
        async for message in messages:
            if hasattr(message.document, 'mime_type'):
                sizes.append(message.document.size)
            if message.message:
                matches = re.findall(self.pattern, message.message)
                for match in matches:
                    links.append(match)
        self.checkbox['links'] = list(set(links))
        self.checkbox['sizes'] = list(set(sizes))

    async def check_aliyun(self, share_id):
        api_url = "https://api.aliyundrive.com/adrive/v3/share_link/get_share_by_anonymous"
        headers = {"Content-Type": "application/json"}
        data = json.dumps({"share_id": share_id})
        async with httpx.AsyncClient() as client:
            response = await client.post(api_url, headers=headers, data=data)
            response_json = response.json()
            if response_json.get('has_pwd'):
                return True
            if response_json.get('code') == 'NotFound.ShareLink':
                return False
            return True

    async def netdisklinkvalidator(self, matches):
        result = []
        for match in matches:
            if 'aliyundrive.com/s/' in match:
                share_id = match.split('/')[-1]
                valid = await self.check_aliyun(share_id)
                result.append((match, valid))
        return result

    async def start(self):
        await self.client.start()
        await self.checkhistory()
        total = 0
        for channel in self.channels_to_monitor:
            await self.forward_messages(channel, self.forward_to_channel)
        for group in self.groups_to_monitor:
            await self.forward_messages(group, self.forward_to_channel)
        with open(self.history, 'w', encoding='utf-8') as f:
            f.write(json.dumps(self.checkbox))
        await self.client.run_until_disconnected()

# 使用示例
if __name__ == "__main__":
    channels_to_monitor = ['DSJ1314', 'guaguale115', 'hao115', 'shareAliyun', 'alyp_JLP', 'Quark_Share_Channel']  # 监控的频道
    groups_to_monitor = []  # 监控的群组
    api_id = os.environ['API_ID']
    api_hash = os.environ['API_HASH']
    string_session = os.environ['STRING_SESSION']
    forward_to_channel = os.environ['FORWARD_TO_CHANNEL']
    limit = 10  # 监控最近消息数
    replies_limit = 1  # 监控消息中的评论数
    kw = ['链接', '片名', '名称', '剧名','pan.quark.cn','115.com','alipan.com','aliyundrive.com']  # 匹配的关键词
    ban = ['预告', '预感', 'https://t.me/', '盈利', '即可观看', '书籍', '电子书', '图书', '软件', '安卓', '风水', '教程', '课程', 'Android']  # 屏蔽关键词
    try_join = False  # 是否尝试自动加入未加入的频道或群组
    nokwforwards = True  # 处理不含关键词的评论
    only_send = True   # 图文资源只主动发送，不转发，可以降低限制风险；不支持视频场景
    fdown = True  # 下载并重新发送图片或视频
    download_folder = 'downloads'  # 下载文件的文件夹
    proxy = None  # 如果需要代理则配置代理
    checknum = 500  # 检查最近多少条消息
    linkvalidtor = False  # 对网盘链接有效性检测
    forwarder = TGForwarder(api_id, api_hash, string_session, channels_to_monitor, groups_to_monitor, forward_to_channel,
                            limit, replies_limit, kw, ban, only_send, nokwforwards, fdown, download_folder, proxy, checknum, linkvalidtor)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(forwarder.start())
