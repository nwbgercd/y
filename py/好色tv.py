import re
import sys
import urllib.parse
import threading
import time
import requests
from pyquery import PyQuery as pq
sys.path.append('..')
from base.spider import Spider

class Spider(Spider):
    def __init__(self):
        # 使用rule中定义的配置
        self.name = '好色TV（优）'
        self.host = 'https://hsex.icu/'
        self.candidate_hosts = [
            "https://hsex.icu/",
            "https://hsex1.icu/",
            "https://hsex.tv/"
        ]
        self.headers = {
            'User-Agent': 'MOBILE_UA',
            'Referer': self.host
        }
        self.timeout = 5000
        
        # 分类映射 - 根据rule中的class_name和class_url
        self.class_map = {
            '周榜': {'type_id': 'top7', 'url_suffix': 'top7'},
            '月榜': {'type_id': 'top', 'url_suffix': 'top'}
        }

    def getName(self):
        return self.name

    def init(self, extend=""):
        # 尝试获取最快可用域名
        self.host = self.get_fastest_host()
        self.headers['Referer'] = self.host

    def isVideoFormat(self, url):
        if not url:
            return False
        return any(fmt in url.lower() for fmt in ['.mp4', '.m3u8', '.flv', '.avi'])

    def manualVideoCheck(self):
        def check(url):
            if not self.isVideoFormat(url):
                return False
            try:
                resp = self.fetch(url, headers=self.headers, method='HEAD', timeout=3)
                return resp.status_code in (200, 302) and 'video' in resp.headers.get('Content-Type', '')
            except:
                return False
        return check

    def get_fastest_host(self):
        """测试候选域名，返回最快可用的"""
        results = {}
        threads = []

        def test_host(url):
            try:
                start_time = time.time()
                resp = requests.head(url, headers=self.headers, timeout=2, allow_redirects=False)
                if resp.status_code in (200, 301, 302):
                    delay = (time.time() - start_time) * 1000
                    results[url] = delay
                else:
                    results[url] = float('inf')
            except:
                results[url] = float('inf')

        for host in self.candidate_hosts:
            t = threading.Thread(target=test_host, args=(host,))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()

        valid_hosts = [(h, d) for h, d in results.items() if d != float('inf')]
        return valid_hosts[0][0] if valid_hosts else self.candidate_hosts[0]

    def homeContent(self, filter):
        result = {}
        # 根据rule中的class_name和class_url设置分类
        classes = []
        for name, info in self.class_map.items():
            classes.append({
                'type_name': name,
                'type_id': info['type_id']
            })
        result['class'] = classes
        
        try:
            # 获取首页内容
            html = self.fetch_with_retry(self.host, retry=2, timeout=5).text
            data = pq(html)
            
            # 根据rule中的一级解析规则提取视频
            # rule: '.row&&.col-xs-6;h5&&Text;.image&&style;.duration&&Text;a&&href'
            vlist = []
            items = data('.row .col-xs-6')
            for item in items.items():
                try:
                    title = item('h5').text().strip()
                    if not title:
                        continue
                    
                    # 提取图片URL
                    style = item('.image').attr('style') or ''
                    pic_match = re.search(r'url\(["\']?([^"\']+)["\']?\)', style)
                    vod_pic = pic_match.group(1) if pic_match else ''
                    if vod_pic and not vod_pic.startswith('http'):
                        vod_pic = f"{self.host.rstrip('/')}/{vod_pic.lstrip('/')}"
                    
                    # 提取描述信息
                    desc = item('.duration').text().strip() or '未知'
                    
                    # 提取链接
                    href = item('a').attr('href') or ''
                    if not href:
                        continue
                    vod_id = href.split('/')[-1]
                    if not vod_id.endswith('.htm'):
                        vod_id += '.htm'
                    
                    vlist.append({
                        'vod_id': vod_id,
                        'vod_name': title,
                        'vod_pic': vod_pic,
                        'vod_remarks': desc
                    })
                except Exception as e:
                    print(f"解析首页视频项失败: {e}")
                    continue
            
            result['list'] = vlist
        except Exception as e:
            print(f"首页解析失败: {e}")
            result['list'] = []
        return result

    def homeVideoContent(self):
        return []

    def categoryContent(self, tid, pg, filter, extend):
        result = {}
        try:
            # 根据rule中的URL模板构造分类URL
            # rule: url: 'https://hsex.icu/fyclass_list-fypage.htm'
            cate_info = None
            for info in self.class_map.values():
                if info['type_id'] == tid:
                    cate_info = info
                    break
            
            if not cate_info:
                result['list'] = []
                return result
            
            url = f"{self.host}{cate_info['url_suffix']}_list-{pg}.htm"
            html = self.fetch(url, headers=self.headers, timeout=8).text
            html = html.encode('utf-8', errors='ignore').decode('utf-8')
            data = pq(html)
            
            # 使用相同的一级解析规则
            vlist = []
            items = data('.row .col-xs-6')
            for item in items.items():
                try:
                    title = item('h5').text().strip()
                    if not title:
                        continue
                    
                    style = item('.image').attr('style') or ''
                    pic_match = re.search(r'url\(["\']?([^"\']+)["\']?\)', style)
                    vod_pic = pic_match.group(1) if pic_match else ''
                    if vod_pic and not vod_pic.startswith('http'):
                        vod_pic = f"{self.host.rstrip('/')}/{vod_pic.lstrip('/')}"
                    
                    desc = item('.duration').text().strip() or '未知'
                    
                    href = item('a').attr('href') or ''
                    if not href:
                        continue
                    vod_id = href.split('/')[-1]
                    if not vod_id.endswith('.htm'):
                        vod_id += '.htm'
                    
                    vlist.append({
                        'vod_id': vod_id,
                        'vod_name': title,
                        'vod_pic': vod_pic,
                        'vod_remarks': desc
                    })
                except Exception as e:
                    print(f"解析分类视频项失败: {e}")
                    continue
            
            # 提取总页数
            pagecount = 1
            try:
                pagination = data('.pagination1 li a')
                page_nums = []
                for a in pagination.items():
                    text = a.text().strip()
                    if text.isdigit():
                        page_nums.append(int(text))
                if page_nums:
                    pagecount = max(page_nums)
            except:
                pagecount = 1
            
            result['list'] = vlist
            result['page'] = pg
            result['pagecount'] = pagecount
            result['limit'] = len(vlist)
            result['total'] = 999999
        except Exception as e:
            print(f"分类解析失败: {e}")
            result['list'] = []
            result['page'] = pg
            result['pagecount'] = 1
            result['limit'] = 0
            result['total'] = 0
        return result

    def detailContent(self, ids):
        try:
            if not ids or not ids[0]:
                return {'list': []}
            
            vod_id = ids[0].strip()
            if not vod_id.endswith('.htm'):
                vod_id += '.htm'
            url = f"{self.host}{vod_id.lstrip('/')}"
            
            html = self.fetch_with_retry(url, retry=2, timeout=8).text
            html = html.encode('utf-8', errors='ignore').decode('utf-8')
            data = pq(html)
            
            # 提取标题
            title = data('.panel-title, .video-title').text().strip() or '未知标题'
            
            # 提取图片
            vod_pic = ''
            poster_style = data('.vjs-poster').attr('style') or ''
            pic_match = re.search(r'url\(["\']?([^"\']+)["\']?\)', poster_style)
            if pic_match:
                vod_pic = pic_match.group(1)
            if not vod_pic:
                vod_pic = data('.video-pic img, .vjs-poster img').attr('src') or ''
            if vod_pic and not vod_pic.startswith('http'):
                vod_pic = f"{self.host}{vod_pic.lstrip('/')}"
            
            # 提取描述信息
            duration = '未知'
            views = '未知'
            info_items = data('.panel-body .col-md-3, .video-info .info-item')
            for item in info_items.items():
                text = item.text().strip()
                if '时长' in text:
                    duration = text.replace('时长：', '').replace('时长', '').strip()
                elif '观看' in text:
                    views = text.replace('观看：', '').replace('观看', '').strip()
            remarks = f"{duration} | {views}"
            
            # 提取播放地址 - 根据rule中的play_parse和lazy设置
            video_url = ''
            m3u8_match = re.search(r'videoUrl\s*=\s*["\']([^"\']+\.m3u8)["\']', html)
            if m3u8_match:
                video_url = m3u8_match.group(1)
            if not video_url:
                source = data('source[src*=".m3u8"], source[src*=".mp4"]')
                video_url = source.attr('src') or ''
            if video_url and not video_url.startswith('http'):
                video_url = f"{self.host}{video_url.lstrip('/')}"
        
            vod = {
                'vod_id': vod_id,
                'vod_name': title,
                'vod_pic': vod_pic,
                'vod_remarks': remarks,
                'vod_play_from': '好色TV（优）',
                'vod_play_url': f'正片${video_url}' if video_url else '正片$暂无地址'
            }
            return {'list': [vod]}
        except Exception as e:
            print(f"详情解析失败: {e}")
            return {'list': []}

    def searchContent(self, key, quick, pg="1"):
        try:
            # 根据rule中的searchUrl构造搜索URL
            # rule: searchUrl: 'https://hsex.icu/search-.htm?search=**&sort=new'
            encoded_key = urllib.parse.quote(key, encoding='utf-8', errors='replace')
            search_url = f"{self.host}search-.htm?search={encoded_key}&sort=new&page={pg}"
            
            html = self.fetch(search_url, headers=self.headers, timeout=5).text
            html = html.encode('utf-8', errors='ignore').decode('utf-8')
            data = pq(html)
            
            # 使用相同的一级解析规则
            vlist = []
            items = data('.row .col-xs-6')
            for item in items.items():
                try:
                    title = item('h5').text().strip()
                    if not title:
                        continue
                    
                    style = item('.image').attr('style') or ''
                    pic_match = re.search(r'url\(["\']?([^"\']+)["\']?\)', style)
                    vod_pic = pic_match.group(1) if pic_match else ''
                    if vod_pic and not vod_pic.startswith('http'):
                        vod_pic = f"{self.host.rstrip('/')}/{vod_pic.lstrip('/')}"
                    
                    desc = item('.duration').text().strip() or '未知'
                    
                    href = item('a').attr('href') or ''
                    if not href:
                        continue
                    vod_id = href.split('/')[-1]
                    if not vod_id.endswith('.htm'):
                        vod_id += '.htm'
                    
                    vlist.append({
                        'vod_id': vod_id,
                        'vod_name': title,
                        'vod_pic': vod_pic,
                        'vod_remarks': desc
                    })
                except Exception as e:
                    print(f"解析搜索视频项失败: {e}")
                    continue
            
            return {'list': vlist, 'page': int(pg)}
        except Exception as e:
            print(f"搜索失败: {e}")
            return {'list': [], 'page': int(pg)}

    def playerContent(self, flag, id, vipFlags):
        headers = self.headers.copy()
        headers.update({
            'Referer': self.host,
            'Origin': self.host.rstrip('/'),
            'Host': urllib.parse.urlparse(self.host).netloc,
        })
        
        # 根据rule中的double设置
        return {
            'parse': 1,  # 根据rule中的play_parse设置
            'url': id,
            'header': headers,
            'double': True  # 根据rule中的double设置
        }

    def localProxy(self, param):
        try:
            url = param['url']
            if url and not url.startswith(('http://', 'https://')):
                url = f"{self.host.rstrip('/')}/{url.lstrip('/')}"
            
            img_headers = self.headers.copy()
            img_headers.update({'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'})
            
            res = self.fetch(url, headers=img_headers, timeout=10)
            content_type = res.headers.get('Content-Type', 'image/jpeg')
            
            return [200, content_type, res.content]
        except Exception as e:
            print(f"图片代理失败: {e}")
            return [200, 'image/jpeg', b'']

    def fetch_with_retry(self, url, retry=2, timeout=5):
        for i in range(retry + 1):
            try:
                resp = self.fetch(url, headers=self.headers, timeout=timeout)
                if resp.status_code in (200, 301, 302):
                    return resp
                print(f"请求{url}返回状态码{resp.status_code}，重试中...")
            except Exception as e:
                print(f"第{i+1}次请求{url}失败: {e}")
            if i < retry:
                time.sleep(0.5)
        return type('obj', (object,), {'text': '', 'status_code': 404})

    def fetch(self, url, headers=None, timeout=5, method='GET'):
        headers = headers or self.headers
        try:
            if method.upper() == 'GET':
                resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            elif method.upper() == 'HEAD':
                resp = requests.head(url, headers=headers, timeout=timeout, allow_redirects=False)
            else:
                resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            resp.encoding = 'utf-8'
            return resp
        except Exception as e:
            print(f"网络请求失败({url}): {e}")
            return type('obj', (object,), {'text': '', 'status_code': 500, 'headers': {}})