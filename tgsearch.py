import os
import socks
import shutil
import re
import random
import time
from telethon import TelegramClient, functions
from telethon.tl.types import MessageMediaPhoto
from telethon.sessions import StringSession
from telethon.tl.functions.channels import JoinChannelRequest

'''
代理参数说明:
# SOCKS5
proxy = (socks.SOCKS5,proxy_address,proxy_port,proxy_username,proxy_password)
# HTTP
proxy = (socks.HTTP,proxy_address,proxy_port,proxy_username,proxy_password))
# HTTP_PROXY
proxy=(socks.HTTP,http_proxy_list[1][2:],int(http_proxy_list[2]),proxy_username,proxy_password)
'''

if os.environ.get("HTTP_PROXY"):
    http_proxy_list = os.environ["HTTP_PROXY"].split(":")


class TGForwarder:
    def __init__(self, api_id, api_hash, string_session, channels_to_monitor, groups_to_monitor, forward_to_channel,
                 limit, replies_limit, kw, ban, nokwforwards, fdown, download_folder, proxy, checknum):
        self.checkbox = {}
        self.checknum = checknum
        # 正则表达式匹配资源链接
        self.pattern = r"(?:链接：|magnet:)?\s*(https?://[^\s]+|magnet:.+)"
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
        self.nokwforwards = nokwforwards
        self.fdown = fdown
        self.download_folder = download_folder
        if not proxy:
            self.client = TelegramClient(StringSession(string_session), api_id, api_hash)
        else:
            self.client = TelegramClient(StringSession(string_session), api_id, api_hash, proxy=proxy)

    def random_wait(self, min_ms, max_ms):
        min_sec = min_ms / 1000
        max_sec = max_ms / 1000
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
        '''
        获取频道消息下的评论，有些视频/资源链接被放在评论中
        '''
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
        try:
            if try_join:
                await self.client(JoinChannelRequest(chat_name))
            chat = await self.client.get_entity(chat_name)
            messages = self.client.iter_messages(chat, limit=self.limit)
            async for message in messages:
                self.random_wait(200, 1000)
                forwards = message.forwards
                if message.media:
                    # 视频
                    if hasattr(message.document, 'mime_type') and self.contains(message.document.mime_type, 'video') and self.nocontains(message.message, self.ban):
                        if forwards:
                            size = message.document.size
                            if size not in self.checkbox['sizes']:
                                await self.client.forward_messages(target_chat_name, message)
                                total += 1
                            else:
                                print(f'视频已经存在，size: {size}')
                    # 图文(匹配关键词)
                    elif self.contains(message.message, self.kw) and message.message and self.nocontains(message.message, self.ban):
                        matches = re.findall(self.pattern, message.message)
                        if matches:
                            link = matches[0]
                            if link not in self.checkbox['links']:
                                if forwards:
                                    await self.client.forward_messages(target_chat_name, message)
                                    total += 1
                                else:
                                    await self.send(message, target_chat_name)
                                    total += 1
                            else:
                                print(f'链接已存在，link: {link}')
                    # 图文(不含关键词，默认nokwforwards=False)，资源被放到评论中
                    elif self.nokwforwards and message.message and self.nocontains(message.message, self.ban):
                        replies = await self.get_all_replies(chat_name, message)
                        replies = replies[-self.replies_limit:]
                        for r in replies:
                            # 评论中的视频
                            if hasattr(r.document, 'mime_type') and self.contains(r.document.mime_type, 'video') and self.nocontains(r.message, self.ban):
                                size = r.document.size
                                if size not in self.checkbox['sizes']:
                                    await self.client.forward_messages(target_chat_name, r)
                                    total += 1
                                else:
                                    print(f'视频已经存在，size: {size}')
                            # 评论中链接关键词
                            elif self.contains(r.message, self.kw) and r.message and self.nocontains(r.message, self.ban):
                                matches = re.findall(self.pattern, r.message)
                                if matches:
                                    link = matches[0]
                                    if link not in self.checkbox['links']:
                                        if forwards:
                                            await self.client.forward_messages(target_chat_name, r)
                                            total += 1
                                        else:
                                            await self.send(r, target_chat_name)
                                            total += 1
                                    else:
                                        print(f'链接已存在，link: {link}')

            print(f"从 {chat_name} 转发资源到 {self.forward_to_channel} total: {total}")
        except Exception as e:
            print(f"从 {chat_name} 转发资源到 {self.forward_to_channel} 失败: {e}")

    async def check(self):
        # post_ids = []
        links = []
        sizes = []
        chat = await self.client.get_entity(self.forward_to_channel)
        messages = self.client.iter_messages(chat, limit=self.checknum)
        async for message in messages:
            # print(f'{self.forward_to_channel}: {message.id}')
            # 视频类型对比大小
            if hasattr(message.document, 'mime_type'):
                sizes.append(message.document.size)
            # 匹配出链接
            if message.message:
                matches = re.findall(self.pattern, message.message)
                for match in matches:
                    links.append(match)
            # 消息类型为转发-不再从相同频道再次转发，links可以覆盖该场景
            # if message.fwd_from:
            #     post_ids.append(f'{message.fwd_from.from_id.channel_id}_{message.fwd_from.channel_post}')
        # self.checkbox['posts_ids'] = list(set(post_ids))
        self.checkbox['links'] = list(set(links))
        self.checkbox['sizes'] = list(set(sizes))

    async def main(self):
        await self.check()
        if not os.path.exists(self.download_folder):
            os.makedirs(self.download_folder)
        for chat_name in self.channels_to_monitor + self.groups_to_monitor:
            global total
            total = 0
            await self.forward_messages(chat_name, self.forward_to_channel)
        await self.client.disconnect()
        if self.fdown:
            shutil.rmtree(self.download_folder)

    def run(self):
        with self.client.start():
            self.client.loop.run_until_complete(self.main())

if __name__ == '__main__':
    channels_to_monitor = ['XiangxiuNB','yunpanpan','kuakeyun']  # 监控的频道
    groups_to_monitor = ['alypzyhzq','Mbox115']  # 监控的群组
    forward_to_channel = 'qfsy_tgsearch'  # 转发到的频道或群组
    limit = 10  # 监控最近消息数
    replies_limit = 1  # 监控消息中的评论数
    kw = ['链接', '片名', '名称']  # 匹配的关键词
    ban = ['预告', '盈利', 'https://t.me/']  # 屏蔽关键词
    try_join = False  # 是否尝试自动加入未加入的频道或群组
    nokwforwards = True  # 处理不含关键词的评论
    fdown = True  # 下载并重新发送图片或视频
    download_folder = 'downloads'  # 下载文件的文件夹
    api_id = int(os.environ.get('API_ID'))  # 从环境变量中读取 api_id
    api_hash = os.environ.get('API_HASH')  # 从环境变量中读取 api_hash
    string_session = os.environ.get('STRING_SESSION')  # 从环境变量中读取 string_session
    proxy = None  # 如果需要代理则配置代理
    checknum = 100  # 检查最近多少条消息

    TGForwarder(api_id, api_hash, string_session, channels_to_monitor, groups_to_monitor, forward_to_channel, limit,
                replies_limit, kw, ban, nokwforwards, fdown, download_folder, proxy, checknum).run()

