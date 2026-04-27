import concurrent.futures
import subprocess
import re
import time
import os
import encodings.idna
import random
import sys
import shutil
import urllib.request
import zipfile
import json
import requests
from fake_useragent import UserAgent


playlist_file = "playlists/"

m3u8_file_path = "output/"

filter_url_arr = ['122.152.202.33','cnstream.top','goodiptv','jlntv','zjrtv.vip','epg.pw','21dtv.com/songs','sd5hxc','bs3/video-hls',
'gcalic.v.myalicdn.com/gc/','gctxyc.liveplay.myqcloud.com','bizcommon.alicdn.com','dd.ddzb.fun'] # 剔除一些特定的直播源，因它们不是开放的静态直播源，或者其他一些不想要的

filter_url_arr_1 = ['live.metshop.top'] # 针对斗鱼，虎牙的直播源做特殊过滤，仅保留电影相关的

# 外部公开直播源聚合地址（GitHub 知名 IPTV 仓库 + 其他聚合站）
EXTERNAL_SOURCE_URLS = [
    # 直播电视IPV4
    "https://live.zbds.top/tv/iptv4.txt",
    # Meroser IPTV
    "https://raw.githubusercontent.com/Meroser/IPTV/main/IPTV.m3u",
    # YueChan Live
    "https://raw.githubusercontent.com/YueChan/Live/main/IPTV.m3u",
    # joevess IPTV
    "https://raw.githubusercontent.com/joevess/IPTV/main/home.m3u8",
    # suxuang myIPTV
    "https://raw.githubusercontent.com/suxuang/myIPTV/main/ipv4.m3u",
    # kimwang collect-tv-txt（txt 格式）
    "https://raw.githubusercontent.com/kimwang1978/collect-tv-txt/main/merged_output.txt",
    # vbskycn iptv
    "https://raw.githubusercontent.com/vbskycn/iptv/master/tv/iptv4.m3u",
    "https://raw.githubusercontent.com/vbskycn/iptv/master/tv/iptv6.m3u",
    # ssili126 tv
    "https://raw.githubusercontent.com/ssili126/tv/main/iptv.m3u",
    # qist tvbox
    "https://raw.githubusercontent.com/qist/tvbox/master/iptv/iptv.m3u",
    # zbefine iptv
    "https://raw.githubusercontent.com/zbefine/iptv/main/iptv.m3u",
    # mengxh myIPTV（txt 格式）
    "https://raw.githubusercontent.com/mengxh1990/myIPTV/master/live.txt",
    # iptv-org 中国区频道
    "https://iptv-org.github.io/iptv/countries/cn.m3u",
    # Ftindy IPTV-URL
    "https://raw.githubusercontent.com/Ftindy/IPTV-URL/main/huyafenxi.m3u",
    # 台湾/港澳卫星
    "https://raw.githubusercontent.com/YanG-1989/m3u/main/Gather.m3u",
    # liuchenyang IPTV（含央视/卫视/地方台）
    "https://raw.githubusercontent.com/liuchenyang0515/IPTV/main/IPTV.m3u",
]

max_workers = 8  # 测试直播源的线程数量。线程数太多，容易被屏蔽请求

if (len(sys.argv)-1) >= 1:
    max_workers = int(sys.argv[1])

download_video_time = 4 # 使用ffmpeg下载多少秒直播源的视频时长，时间太短一些国外的源，可能还没发缓冲过来，不建议在调整该值

download_video_length = download_video_time * 70 # 使用ffmpeg下载{download_video_time}秒直播源的视频时长，如果视频文件的大小，小于这个值，说明下载很慢，那么剔除掉，一般1秒钟需要有70KB才不卡顿

timeout = download_video_time + 0.1   # 使用ffmpeg下载{download_video_time}秒直播源的视频，最大允许的耗时秒数，超过的终止请求。超时时间太短可能没法获取视频分辨率，不建议在调整该值

if (len(sys.argv)-1) >= 2:
    timeout = int(sys.argv[2])
    
download_video_use_time = timeout + 0.1  # 使用ffmpeg下载{download_video_time}秒直播源的视频，到解析出视频分辨率，最大允许的耗时秒数，超过的剔除，不建议在调整该值

max_bitrate = 5000  # bitrate高于5000，容易卡顿，故剔除掉

max_fps = 50  # fps高于50，容易卡顿，故剔除掉

max_width = 2000 # 分辨率宽度超过{max_width}，容易卡顿，剔除掉

print(f"max_workers: {max_workers}")
print(f"timeout: {timeout}")

def check_and_setup_ffmpeg():
    """
    检测 ffmpeg 是否可用。
    - 若在 PATH 中找到，直接返回。
    - 若在脚本同目录下找到 ffmpeg / ffmpeg.exe，将该目录加入 PATH 后返回。
    - 若都没有：
        Linux/macOS：尝试 apt-get 安装。
        Windows    ：从 BtbN/FFmpeg-Builds 下载静态构建并解压到项目目录。
    """
    # 1. 检查 PATH 里是否有 ffmpeg
    if shutil.which("ffmpeg") is not None:
        print("[ffmpeg] Found in PATH, ready to use.")
        return

    # 2. 检查项目目录下是否已有 ffmpeg 可执行文件
    script_dir = os.path.dirname(os.path.abspath(__file__))
    local_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    local_path = os.path.join(script_dir, local_name)

    if os.path.isfile(local_path):
        print(f"[ffmpeg] Found locally at: {local_path}")
        os.environ["PATH"] = script_dir + os.pathsep + os.environ.get("PATH", "")
        return

    print("[ffmpeg] Not found, attempting to install / download ...")

    # 3a. Linux / macOS —— apt-get 安装
    if sys.platform.startswith("linux") or sys.platform == "darwin":
        for cmd_prefix in [["sudo", "apt-get"], ["apt-get"]]:
            try:
                subprocess.run(
                    cmd_prefix + ["install", "-y", "ffmpeg"],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                print("[ffmpeg] Installed via apt-get.")
                return
            except Exception as e:
                print(f"[ffmpeg] apt-get attempt failed: {e}")
        print("[ffmpeg] ERROR: Could not install ffmpeg automatically. Please install it manually.")
        sys.exit(1)

    # 3b. Windows —— 下载静态构建包并解压
    elif sys.platform == "win32":
        zip_url = (
            "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
            "ffmpeg-master-latest-win64-lgpl.zip"
        )
        zip_path = os.path.join(script_dir, "_ffmpeg_download.zip")
        try:
            print(f"[ffmpeg] Downloading from {zip_url} ...")
            urllib.request.urlretrieve(zip_url, zip_path)
            print("[ffmpeg] Download complete, extracting ffmpeg.exe ...")
            with zipfile.ZipFile(zip_path, "r") as zf:
                for name in zf.namelist():
                    # 包内路径类似 ffmpeg-xxx/bin/ffmpeg.exe
                    if name.endswith("bin/ffmpeg.exe"):
                        data = zf.read(name)
                        with open(local_path, "wb") as f_out:
                            f_out.write(data)
                        print(f"[ffmpeg] Extracted to: {local_path}")
                        break
            os.remove(zip_path)
            os.environ["PATH"] = script_dir + os.pathsep + os.environ.get("PATH", "")
            print("[ffmpeg] Ready.")
        except Exception as e:
            print(f"[ffmpeg] ERROR: Failed to download/extract ffmpeg: {e}")
            print("[ffmpeg] Please download ffmpeg manually and place ffmpeg.exe in the project folder.")
            sys.exit(1)
    else:
        print(f"[ffmpeg] Unsupported platform: {sys.platform}. Please install ffmpeg manually.")
        sys.exit(1)


def get_fake_User_Agent():
    ua = UserAgent()
    user_agent = ua.random
    return user_agent


def get_test_url_time(start_time, width, height, url):
    end_time = time.time()
    get_time = end_time - start_time
    get_time = "{:.3f}".format(get_time)
    print(f"get_time: {get_time}  Resolution: {width}x{height} url: {url}")
    return get_time


def get_resolution_and_download_time(i, url):
    start_time = time.time()
    process = None
    output_file_name = "test_" + str(i) + ".mp4"

    try:
        # print(f"get_resolution_and_download_time start, url：{url}")
        ua = get_fake_User_Agent()

        cmd = ["ffmpeg"]
        cmd.append("-user_agent")
        cmd.append(ua)
        cmd.append("-i")
        cmd.append(url)
        cmd.append("-hide_banner")
        cmd.append("-t")
        cmd.append(str(download_video_time))  # 将{download_video_time}秒钟的直播视频下载下来
        cmd.append("-c")
        cmd.append("copy")
        cmd.append(output_file_name)

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            encoding="utf-8",
            check=True,
        )

        if result is not None and result.returncode == 0:
            print(f"cmd result: {result}")
            original_file_size = os.path.getsize(output_file_name)
            file_size = original_file_size / 1024

            # 删除之前测试直播源存储的视频文件
            os.remove(output_file_name)
            
            print(f"file_size: {file_size} =======================================")

            if file_size < download_video_length:
                print(f"{download_video_time}秒钟的视频大小没有超过{download_video_length}KB, 播放容易卡顿，故剔除掉 url: {url}")
                get_test_url_time(start_time, 0, 0, url)
                return None, None, None, None

            output_cont = result.stdout
            cont_arr = output_cont.split("\n")
            cont_len = len(cont_arr)

            bitrate = ""
            bitrateFloat = 0
            
            fps = ""
            fpsInt = 0
            
            width_height = ""
            
            for j in range(cont_len):
                # print(f"##########cont_arr[{j}] result: {cont_arr[j]}")
                
                if j == (cont_len - 2):
                    match = re.search(r"bitrate\=\d{3,4}\.\d{1,4}kbits\/s", cont_arr[j])
                    if match:
                        bitrate = match.group(0)
                        bitrateFloat = float(bitrate.replace("bitrate=","").replace("kbits/s",""))
                        print(f"bitrate:{bitrateFloat} =======================================")
                        
                if cont_arr[j].find("Stream #0:0:") > -1:
                    match = re.search(r"\d{2}\sfps", cont_arr[j])
                    if match:
                        fps = match.group(0)
                        fpsInt = int(fps.replace(" fps",""))
                        print(f"fps:{fpsInt} =======================================")
                       
                    match = re.search(r"(\d{3,4}x\d{3,4})", cont_arr[j])
                    if match:
                        width_height = match.group(1)
                        print(f"width_height:{width_height} =======================================")
                        
            # 过滤 fps 太高的直播源，容易卡顿
            if fpsInt > max_fps:
                print(f"fps:{fpsInt}高于{max_fps}，容易卡顿，故剔除掉 url:{url}")
                return None, None, None, None
                
            # 过滤 bitrate 太高的直播源，容易卡顿
            elif bitrateFloat > max_bitrate:
                print(f"bitrate:{bitrateFloat}高于{max_bitrate}，容易卡顿，故剔除掉 url:{url}")
                return None, None, None, None
                
            elif len(width_height) > 0:
                arr = width_height.split("x")
                width = arr[0]
                height = arr[1]

                get_time = get_test_url_time(start_time, width, height, url)
                return width, height, get_time, original_file_size
            # 没有获取到分辨率的，过滤掉
            else:
                get_test_url_time(start_time, 0, 0, url)
                return None, None, None, None

        else:
            # 删除之前测试直播源存储的视频文件
            if os.path.isfile(output_file_name):
                os.remove(output_file_name)

            get_test_url_time(start_time, 0, 0, url)
            return None, None, None, None

    except Exception as e:
        if process is not None:
            process.kill()

        # 删除之前测试直播源存储的视频文件
        if os.path.isfile(output_file_name):
            os.remove(output_file_name)

        print(f"Failed to get resolution for URL {url}: {e}")
        get_test_url_time(start_time, 0, 0, url)
        return None, None, None, None


def test_stream(url, output_file, tv_name, i, total):
    print(f"test url no.:{i} total: {total}")
    try:
        width, height, get_time, file_size_1 = get_resolution_and_download_time(i, url)
        time.sleep(5)
        width, height, get_time, file_size_2 = get_resolution_and_download_time(i, url)

        print(f"get_time:{get_time} =======================================")
        
        if (file_size_1 == file_size_2):
            print(f"TV Name: {tv_name} URL: {url} 视频内容重复，剔除掉")
       
        # 剔除获取不到视频分辨率的
        # 剔除下载2秒视频流，耗时超过xx秒的直播源
        elif (width is None or height is None or get_time is None):
            print(f"TV Name: {tv_name} URL: {url} 未获取到分辨率，剔除掉")
            
        elif (float(width) > max_width):
            print(f"TV Name: {tv_name} URL: {url} 分辨率宽度超过{max_width}，容易卡顿，剔除掉")
            
        elif (float(get_time) > download_video_use_time):
            print(f"TV Name: {tv_name} URL: {url} 获取分辨率超时，剔除掉")
            
        elif (width is not None
            and height is not None
            and get_time is not None):
            with open(output_file, "a", encoding="utf-8") as f:
                f.write(f"#EXTINF:-1,{tv_name}___{width}x{height}_{get_time}\n")
                f.write(url + "\n")
            print(f"TV Name: {tv_name}_{width}x{height}_{get_time} ===========================")
            print(f"URL: {url}")

    except Exception as e:
        print(f"Failed to test URL {url}: {e}")


def get_tv_name(line, isHandle):
    match = re.search(r'tvg-name="([^"]+)"', line)
    if match:
        if isHandle:
            new_parts = match.group(1).strip().split("_");
            return new_parts[0]
        else:
            return match.group(1).strip()
    else:
        parts = line.split(",")
        if len(parts) > 1:
            if isHandle:
                new_parts = parts[1].strip().split("_");
                return new_parts[0]
            else:
                return parts[1].strip();
        else:
            return "Unknown"


def fetch_external_sources():
    """
    从 EXTERNAL_SOURCE_URLS 中抓取公开直播源列表，返回 [(url, tv_name), ...] 。
    支持 M3U / M3U8 和 TXT（"频道名,URL" 格式）两种格式，自动根据内容判断。
    """
    fetched = []
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; StreamChecker/1.0)",
        "Accept": "*/*",
    }

    for source_url in EXTERNAL_SOURCE_URLS:
        try:
            print(f"[fetch] Fetching external source: {source_url}")
            resp = requests.get(source_url, headers=headers, timeout=30)
            if resp.status_code != 200:
                print(f"[fetch] HTTP {resp.status_code} for {source_url}, skipping.")
                continue

            content = resp.text
            lines = content.splitlines()

            # 根据内容首行判断格式：M3U 还是 TXT
            is_m3u = False
            for line in lines:
                stripped = line.strip()
                if stripped:
                    is_m3u = stripped.startswith("#EXTM3U") or stripped.startswith("#EXTINF")
                    break

            count_before = len(fetched)

            if is_m3u:
                total = len(lines)
                for i in range(total):
                    if lines[i].startswith("#EXTINF:-1") or lines[i].startswith("#EXTINF:"):
                        tv_name = get_tv_name(lines[i], True)
                        if i + 1 < total:
                            url = lines[i + 1].strip()
                            if url.startswith("http"):
                                fetched.append((url, tv_name))
            else:
                # TXT 格式："频道名,URL" 或 "频道名,URL1#URL2"
                for line in lines:
                    if (line.find("http:") != -1 or line.find("https:") != -1) and line.find(",") != -1:
                        arr = line.split(",")
                        tv_name = arr[0].strip()
                        url_part = arr[1].strip()
                        if url_part.find("#") != -1:
                            for u in url_part.split("#"):
                                u = u.strip()
                                if u.startswith("http"):
                                    fetched.append((u, tv_name))
                        else:
                            if url_part.startswith("http"):
                                fetched.append((url_part, tv_name))

            added = len(fetched) - count_before
            print(f"[fetch] Added {added} URLs from {source_url}")

        except Exception as e:
            print(f"[fetch] Error fetching {source_url}: {e}")

    print(f"[fetch] Total external URLs fetched: {len(fetched)}")
    return fetched


def main(playlist_file, m3u8_file_path):

    # 检测并安装/下载 ffmpeg
    check_and_setup_ffmpeg()

    output_file = (
        m3u8_file_path + time.strftime("%Y-%m-%d-%H-%M-%S", time.localtime()) + ".m3u"
    )

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")

    urls = []
    idx = 0

    # ── 1. 抓取外部公开直播源 ──────────────────────────────────────────────────
    external_urls = fetch_external_sources()
    for url, tv_name in external_urls:
        idx += 1
        urls.append((url, tv_name, idx))

    # ── 2. 读取本地 playlists/ 目录下的文件 ────────────────────────────────────
    for file_name in os.listdir(playlist_file):

        print(f"file_name: {file_name}")

        if file_name.endswith(".m3u") or file_name.endswith(".m3u8"):  # 处理m3u、m3u8格式的直播源列表
            file_path = os.path.join(playlist_file, file_name)
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            total = len(lines)
            for i in range(total):
                if lines[i].startswith("#EXTINF:-1"):
                    tv_name = get_tv_name(lines[i], True)
                    if i + 1 <= total and lines[i + 1].startswith("http"):
                        url = lines[i + 1].strip()
                        print(f"read file url: {url} TV Name: {tv_name}")
                        idx = idx + 1
                        urls.append((url, tv_name, idx))
                        

        else:  # 处理txt格式的直播源列表
            file_path = os.path.join(playlist_file, file_name)
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            total = len(lines)
            for i in range(total):
                if (lines[i].find("http:") != -1 or lines[i].find("https:") != -1) and lines[i].find(",") != -1:
                    arr = lines[i].split(",")
                    tv_name = arr[0].strip()
                    url = arr[1].strip()
                    if (url.find("#") != -1):  # 兼容txt格式直播源，带有多个直播源地址的情况
                        urlArr = url.split("#")
                        urlNum = len(urlArr)
                        for j in range(urlNum):
                            print(f"read file url: {urlArr[j]} TV Name: {tv_name}")
                            idx = idx + 1
                            urls.append((urlArr[j], tv_name, idx))
                            

                    else:
                        print(f"read file url: {url} TV Name: {tv_name}")
                        idx = idx + 1
                        urls.append((url, tv_name, idx))
                        
    unique_urls = []
    new_urls = []
    idx = 0
    for url_1, tv_name_1, idx_1 in urls:
        isExist = 1
        
        # 过滤重复的url
        if url_1 not in unique_urls:
            isExist = 0
            unique_urls.append(url_1);
            
        # 过滤不想要的url
        for url_2 in filter_url_arr:
            if url_1.find(url_2) != -1 :
                isExist = 1
                
        # 针对斗鱼，虎牙的直播源做特殊过滤，仅保留电影相关的
        for url_2 in filter_url_arr_1:
            if url_1.find(url_2) != -1 and tv_name_1.find("电影")==-1:
                isExist = 1
                
        
        if isExist == 0 :
            new_urls.append((url_1, tv_name_1, idx))
        
    urls = new_urls;
    new_urls = []
    
    urlLen = len(urls)
    # 随机排序下，以便并发测试时，不要同时测试同一个ip地址的直播源
    random.shuffle(urls)
    new_idx = 0

    # 使用多线程并发测试
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        for url, tv_name, idx in urls:
            new_idx = new_idx + 1
            future = executor.submit(
                test_stream, url, output_file, tv_name, new_idx, urlLen
            )

    # 将可用的直播源重新排序
    with open(output_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    total = len(lines)
    new_urls = []
    idx = 0
    for i in range(total):
        if lines[i].startswith("#EXTINF:-1"):
            tv_name = get_tv_name(lines[i], False)
            if i + 1 <= total and lines[i + 1].startswith("http"):
                url = lines[i + 1].strip()
                host_name = url.split("/")[0]
                # print(f"read file url: {url} TV Name: {tv_name}")
                idx = idx + 1
                new_urls.append((url, host_name, tv_name, idx))

    new_sort_urls = sorted(new_urls, key=lambda d:(d[2],d[1],d[0]))  # 按照 tv_name host_name url 排序

    # 再新建一个m3u文件来存储排序后的
    new_output_file = (
        m3u8_file_path + "all_tv.m3u"
    )

    with open(new_output_file, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")

    with open(new_output_file, "a", encoding="utf-8") as f:
        for url, host_name, tv_name, idx in new_sort_urls:
            f.write(f"#EXTINF:-1,{tv_name}\n")
            f.write(url + "\n")

    # 删除之前的m3u文件，因没有排序
    os.remove(output_file)


if __name__ == "__main__":
    main(playlist_file, m3u8_file_path)
