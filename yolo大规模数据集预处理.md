传入源路径和目标路径，将源路径下的'.png', '.jpg', '.jpeg'图片文件调整为640x640并转换为jpg并设置常规的压缩率：
```python
import os
from PIL import Image
from tqdm import tqdm
import multiprocessing

def process_image(args):
    """
    处理单个图片（包含格式转换和压缩）
    """
    src_path, source_dir, target_dir, target_size = args
    rel_path = os.path.relpath(src_path, source_dir)
    
    # 修改文件扩展名为.jpg
    base, _ = os.path.splitext(rel_path)
    dst_path = os.path.join(target_dir, f"{base}.jpg")
    
    try:
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        
        with Image.open(src_path) as img:
            img = img.convert('RGB')
            width, height = img.size
            target_width, target_height = target_size
            
            # 计算缩放比例
            ratio = min(target_width / width, target_height / height)
            new_size = (int(width * ratio), int(height * ratio))
            
            # 缩放并填充
            img_resized = img.resize(new_size, Image.Resampling.LANCZOS)
            new_img = Image.new('RGB', target_size, (0, 0, 0))
            offset = (
                (target_width - new_size[0]) // 2,
                (target_height - new_size[1]) // 2
            )
            new_img.paste(img_resized, offset)
            
            # 保存为JPEG格式并设置压缩质量（75属于常规强度压缩）
            new_img.save(dst_path, 'JPEG', quality=75, optimize=True)
            return None
    except Exception as e:
        return f"处理失败：{src_path} - {str(e)}"

def preprocess_dataset(source_dir, target_dir, target_size=(640, 640)):
    """
    多进程版本预处理函数
    """
    # 收集所有PNG文件路径
    png_files = []
    for root, _, files in os.walk(source_dir):
        for file in files:
            if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                src_path = os.path.join(root, file)
                png_files.append(src_path)

    # 准备进程池参数
    cpu_count = multiprocessing.cpu_count()
    pool_args = [(path, source_dir, target_dir, target_size) for path in png_files]

    # 使用进程池处理
    with multiprocessing.Pool(processes=cpu_count) as pool:
        results = []
        with tqdm(total=len(png_files), desc="处理图片", unit="张") as pbar:
            for result in pool.imap(process_image, pool_args):
                if result:
                    results.append(result)
                pbar.update(1)

    # 打印错误信息
    if results:
        print("\n处理过程中出现以下错误：")
        for error in results:
            print(error)

if __name__ == "__main__":
    source_directory = "./video_scan_16_frame_work_dir/i_frame"
    target_directory = "./video_scan_16_frame_work_dir_640/i_frame"
    preprocess_dataset(source_directory, target_directory)
```

从视频中，均匀的，提取16个关键帧的代码：
```python
import argparse
import ctypes
import mimetypes
import multiprocessing
from dataclasses import dataclass
import multiprocessing.sharedctypes
import multiprocessing.synchronize
import subprocess
import time
from typing import Set,List,Tuple
import json
import os
import logging
import uuid
import magic
from multiprocessing import Process,cpu_count
import queue
import signal
import hashlib
from tqdm import tqdm

logging.basicConfig()

Dir = ""

WorkDir = "./video_scan_16_frame_work_dir"
FileListJsonPath = ""

FileListPath: Set[str] = set()
FileListMd5: Set[str] = set()
LoadFileListProcessedIFrameFilePath: Set[str] = set()

# SafeQueueWriteFileMd5[Tuple[str,str](path,md5)]
SafeQueueWriteFileMd5:multiprocessing.Queue = multiprocessing.Queue(maxsize=1000)
# SafeQueueWriteFileIFrame[Tuple[str,List[str]](path,i_frame_list)]
SafeQueueWriteFileIFrame: multiprocessing.Queue = multiprocessing.Queue(maxsize=1000)

WalkVideoFileList: List[str] = []
SafeQueuePushMd5: multiprocessing.Queue = multiprocessing.Queue(maxsize=1000)
SafeMd5QueueProcessCount:multiprocessing.sharedctypes.Synchronized = multiprocessing.Value(ctypes.c_uint)
SafeMd5QueueProcessTotal:multiprocessing.sharedctypes.Synchronized = multiprocessing.Value(ctypes.c_uint)

SafeQueuePushIFrame: multiprocessing.Queue = multiprocessing.Queue(maxsize=1000)
SafeIFrameQueueProcessCount: multiprocessing.sharedctypes.Synchronized = multiprocessing.Value(ctypes.c_uint)
SafeIFrameQueueProcessTotal: multiprocessing.sharedctypes.Synchronized = multiprocessing.Value(ctypes.c_uint)

WaitExit: multiprocessing.synchronize.Event = multiprocessing.Event()


"""
file_list.json
[
    {
        "path":"/xxx/xxx.mp4"
        "md5":"abcd"
        "i_frame":[
            "/xxx/xxx.png"
        ]
    }
]
"""


def load_file_list():
    global FileListPath, FileListMd5, LoadFileListProcessedIFrameFilePath

    # 检查file_list.json是否存在
    if not os.path.exists(FileListJsonPath):
        if not os.path.exists(WorkDir):
            try:
                os.mkdir(WorkDir)
            except Exception as e:
                raise RuntimeError(f"WorkDir {WorkDir} 创建失败: {e}")
        return
        
    # 读取并解析file_list.json
    try:
        with open(FileListJsonPath, "r", encoding="utf-8") as f:
            file_lists = json.load(f)
            
        # 遍历文件列表,提取信息
        for file_info in file_lists:
            FileListPath.add(file_info['path'])
            FileListMd5.add(file_info['md5'])
            
            # 如果i_frame不为空,则添加到已处理列表
            if file_info['i_frame']:
                LoadFileListProcessedIFrameFilePath.add(file_info['path'])
                
    except Exception as e:
        raise RuntimeError(f"加载file_list.json失败: {str(e)}") from e

def walk():
    """递归查找目录中的所有视频文件"""
    global WalkVideoFileList
    mime_checker = magic.Magic(mime=True)

    def _is_video_file(file_path:str)->bool:
        # 判断给定文件是否为视频文件
        try:
            _, ext = os.path.splitext(file_path)
            ext = ext.lower()
            
            if ext:  
                # 有扩展名的情况
                mime_type, _ = mimetypes.guess_type(file_path)
                return mime_type is not None and mime_type.startswith('video/')
            else:   
                # 无扩展名的情况,使用libmagic进行快速MIME类型检测
                detected_mime = mime_checker.from_file(file_path)
                return detected_mime.startswith('video/')
        except Exception as e:
            logging.warning(f"检查是否为视频失败 {file_path}: {str(e)}")
            return False
    
    for root, _, files in os.walk(Dir):
        for filename in files:
            file_path = os.path.join(root, filename)
            if _is_video_file(file_path):
                WalkVideoFileList.append(file_path)
    
    logging.info(f"共发现 {len(WalkVideoFileList)} 个视频文件")

def get_file_md5(filename, buffer_size=65536):
    md5 = hashlib.md5()
    with open(filename, 'rb') as f:
        while chunk := f.read(buffer_size):
            md5.update(chunk)
    return md5.hexdigest()

def md5(SafeQueuePushMd5:multiprocessing.Queue,SafeQueueWriteFileMd5:multiprocessing.Queue,WaitExit:multiprocessing.synchronize.Event,SafeMd5QueueProcessCount:multiprocessing.sharedctypes.Synchronized,SafeMd5QueueProcessTotal:multiprocessing.sharedctypes.Synchronized):
    wait_time = 0
    while True:
        try:
            path = SafeQueuePushMd5.get_nowait()
            wait_time = 0
        
            md5 = get_file_md5(path)
            
            wait2_time = 0
            while True:
                try:
                    SafeQueueWriteFileMd5.put_nowait((path,md5))
                    break

                except queue.Full:
                    logging.warning(f"SafeQueueWriteFileMd5队列已满，第{wait2_time}秒")
                    time.sleep(0.1)
                    wait2_time += 1
                
                if WaitExit.is_set() and (wait2_time == 0 or wait2_time > 20):
                    return
                
        except queue.Empty:
            logging.warning(f"SafeQueuePushMd5队列无数据，第{wait_time}秒")
            time.sleep(0.1)
            wait_time += 1

        if WaitExit.is_set():
            return
        
        if SafeMd5QueueProcessCount.value == SafeMd5QueueProcessTotal.value:
            return

def first_ctrl_c_handler(signum, frame):
    """信号处理函数"""

    global WaitExit
    WaitExit.set()
    logging.info("已经号召各进程完成工作并优雅退出！")

    # 恢复默认的信号处理（后续的 Ctrl+C 会终止程序）
    signal.signal(signal.SIGINT, signal.SIG_DFL)

def write_file(SafeQueueWriteFileMd5:multiprocessing.Queue,SafeQueueWriteFileIFrame:multiprocessing.Queue,WaitExit:multiprocessing.synchronize.Event,SafeMd5QueueProcessCount:multiprocessing.sharedctypes.Synchronized,FileListPath:Set[str],FileListMd5:Set[str],SafeIFrameQueueProcessCount:multiprocessing.sharedctypes.Synchronized,SafeIFrameQueueProcessTotal:multiprocessing.sharedctypes.Synchronized,SafeMd5QueueProcessTotal:multiprocessing.sharedctypes.Synchronized):
    try:
        # 检查文件是否存在，如果不存在则创建
        if not os.path.exists(FileListJsonPath):
            with open(FileListJsonPath, 'w',encoding="utf-8") as file_list_buffer:
                json.dump([], file_list_buffer, indent=4, ensure_ascii=False)

        with open(FileListJsonPath, 'r',encoding="utf-8") as file_list_buffer:
            file_lists = json.load(file_list_buffer)

    except FileNotFoundError as e:
        raise RuntimeError(f"write_file()打开{FileListJsonPath}错误: {e}") from e
    except json.JSONDecodeError as e:
        raise RuntimeError(f"write_file(){FileListJsonPath}反序列化json错误: {e}") from e
    except Exception as e:
        raise RuntimeError(f"write_file()错误: {e}") from e
    
    pbar = tqdm(total=100,desc="MD5")
    pbar2 = tqdm(total=100,desc="I帧")

    wait_time = 0
    wait2_time = 0
    while True:
        ######
        # MD5
        ######
        try:
            path,md5 = SafeQueueWriteFileMd5.get_nowait()
            wait_time = 0

            if not path and not md5:
                SafeMd5QueueProcessCount.value += 1
                pbar.total = SafeMd5QueueProcessTotal.value
                pbar.update(1)
                continue

            if md5 in FileListMd5:
                SafeMd5QueueProcessCount.value += 1
                pbar.total = SafeMd5QueueProcessTotal.value
                pbar.update(1)
                continue

            FileListPath.add(path)
            SafeMd5QueueProcessCount.value += 1
            pbar.total = SafeMd5QueueProcessTotal.value
            pbar.update(1)
            FileListMd5.add(md5)
            
            file_lists.append({
                "path":path,
                "md5":md5,
                "i_frame":[]
            })
            
            with open(FileListJsonPath, 'w',encoding="utf-8") as file_list_buffer:
                json.dump(file_lists, file_list_buffer, indent=4, ensure_ascii=False)

        except queue.Empty:
            logging.warning(f"SafeQueueWriteFileMd5队列无数据，第{wait_time}秒")
            time.sleep(0.1)
            wait_time += 1
        except Exception as e:
            logging.error(f"write_file()错误: {e}")
        
        ######
        # I frame
        ######
        try:
            path,i_frame_list = SafeQueueWriteFileIFrame.get_nowait()
            wait2_time = 0
            SafeIFrameQueueProcessCount.value += 1
            pbar2.total = SafeIFrameQueueProcessTotal.value
            pbar2.update(1)

            if not path or not i_frame_list:
                continue
            
            # 遍历file_lists查找匹配的path
            for file_list in file_lists:
                if file_list['path'] == path:
                    file_list['i_frame'].extend(i_frame_list)
                    break
            
            with open(FileListJsonPath, 'w',encoding="utf-8") as file_list_buffer:
                json.dump(file_lists, file_list_buffer, indent=4, ensure_ascii=False)

            if SafeIFrameQueueProcessCount.value == SafeIFrameQueueProcessTotal.value:
                return

        except queue.Empty:
            logging.warning(f"SafeQueueWriteFileIFrame队列无数据，第{wait2_time}秒")
            time.sleep(0.1)
            wait2_time += 1

        except Exception as e:
            logging.error(f"write_file()错误: {e}")

        if WaitExit.is_set() and SafeQueueWriteFileMd5.empty() and SafeQueueWriteFileIFrame.empty():
            return

def safe_queue_push_md5(SafeQueuePushMd5:multiprocessing.Queue,WaitExit:multiprocessing.synchronize.Event,allow_path_list:List[str]):
    for path in allow_path_list:
        wait_time = 0
        while True:
            try:
                SafeQueuePushMd5.put_nowait(path)
                break
            except queue.Full:
                logging.warning(f"SafeQueuePushMd5队列已满，第{wait_time}秒")
                time.sleep(0.1)
                wait_time += 1
            
            if WaitExit.is_set():
                return

        if WaitExit.is_set():
            return

def main_md5():
    """md5生成的主函数"""

    global SafeQueuePushMd5,SafeQueueWriteFileMd5,WaitExit,SafeMd5QueueProcessCount,SafeMd5QueueProcessTotal,WalkVideoFileList,FileListPath

    allow_path_list = []
    for path in WalkVideoFileList:
        if path in FileListPath:
            continue
        allow_path_list.append(path)
    SafeMd5QueueProcessTotal.value = len(allow_path_list)

    process_list: List[multiprocessing.Process] = []
    for _ in range(cpu_count()):
        p = Process(target=md5,args=(SafeQueuePushMd5,SafeQueueWriteFileMd5,WaitExit,SafeMd5QueueProcessCount,SafeMd5QueueProcessTotal,))
        p.start()
        process_list.append(p)

    Process(target=safe_queue_push_md5,args=(SafeQueuePushMd5,WaitExit,allow_path_list,)).start()

    # 等待所有进程完成
    for p in process_list:
        p.join()

def get_i_frames(input_video):
    """
    使用 ffprobe 获取视频中所有 I 帧的时间点
    :param input_video: 输入视频文件路径
    :return: 包含所有 I 帧时间点的列表（单位：秒 float））
    """
    cmd = [
        'ffprobe',
        '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'frame=pts_time,pict_type',
        '-of', 'csv=print_section=0',
        input_video
        
    ]
    
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        out, err = proc.communicate()
        
        if proc.returncode != 0:
            raise RuntimeError(f"ffprobe 执行失败: {err.strip()}")
        
        i_frames = []
        for line in out.splitlines():
            if 'I' in line and "N/A" not in line:
                pts_time = float(line.split(',')[0])
                i_frames.append(pts_time)
                
        return i_frames
    
    except Exception as e:
        raise RuntimeError(f"获取 I 帧失败: {str(e)}") from e


def extract_frames(time_points, input_video, output_template="frame_{time:.6f}.png")->List[str]:
    """
    根据时间点从视频中提取帧
    :param time_points: 时间点列表（单位：秒 float）
    :param input_video: 输入视频文件路径
    :param output_template: 输出文件名模板（支持 {time} 占位符）
    """

    output_file_list = []

    for time in time_points:
        output_file = output_template.format(time=time)

        output_file_list.append(output_file)
        
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        cmd = [
            'ffmpeg',
            '-ss', f'{time:.6f}',
            '-i', input_video,
            '-frames:v', '1',
            '-qscale:v', '2',
            '-y',
            output_file
        ]

        try:
            subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            logging.debug(f"成功提取 {time:.6f} 秒的帧到 {output_file}")
            
        except subprocess.CalledProcessError as e:
            logging.warning(f"提取 {time:.6f} 秒的帧失败: {e.stderr.strip()}")
        except Exception as e:
            logging.warning(f"处理 {time:.6f} 秒时发生错误: {str(e)}")
    
    return output_file_list

def i_frame(SafeQueuePushIFrame:multiprocessing.Queue,SafeQueueWriteFileIFrame:multiprocessing.Queue,SafeIFrameQueueProcessCount:multiprocessing.sharedctypes.Synchronized,SafeIFrameQueueProcessTotal:multiprocessing.sharedctypes.Synchronized,WaitExit: multiprocessing.synchronize.Event):
    wait_time = 0
    while True:
        try:
            path:str = SafeQueuePushIFrame.get_nowait()
            wait_time = 0
        
            i_frame_time_list = get_i_frames(path)
            if not i_frame_time_list:
                continue


            allow_i_frame_list: List[float] = []

            if len(i_frame_time_list) <= 16:
                allow_i_frame_list.extend(i_frame_time_list)

            else:
                x = len(i_frame_time_list) // 16

                # 以步长x选取元素，并截取前16个
                allow_i_frame_list = i_frame_time_list[::x][:16]
            
            i_frame_file_list = extract_frames(allow_i_frame_list,path,os.path.join(WorkDir,"i_frame",str(uuid.uuid4()),"{time:.6f}.png"))

            wait2_time = 0
            while True:
                try:
                    SafeQueueWriteFileIFrame.put_nowait((path,i_frame_file_list))
                    break

                except queue.Full:
                    logging.warning(f"SafeQueueWriteFileIFrame队列已满，第{wait2_time}秒")
                    time.sleep(0.1)
                    wait2_time += 1
                
                if WaitExit.is_set() and (wait2_time == 0 or wait2_time > 20):
                    return
                
        except queue.Empty:
            logging.warning(f"SafeQueuePushIFrame队列无数据，第{wait_time}秒")
            time.sleep(0.1)
            wait_time += 1

        except Exception as e:
            logging.error(f"i_frame()错误: {e}")

        if WaitExit.is_set():
            return
        
        if SafeIFrameQueueProcessCount.value == SafeIFrameQueueProcessTotal.value:
            return

def main_i_frame():
    global SafeQueuePushIFrame,SafeQueueWriteFileIFrame,SafeIFrameQueueProcessCount,WaitExit,FileListPath,LoadFileListProcessedIFrameFilePath,SafeIFrameQueueProcessTotal

    unprocessed_list = list(FileListPath.difference(LoadFileListProcessedIFrameFilePath))
    SafeIFrameQueueProcessTotal.value = len(unprocessed_list)

    process_list: List[multiprocessing.Process] = []
    for _ in range(cpu_count()):
        p = Process(target=i_frame,args=(SafeQueuePushIFrame,SafeQueueWriteFileIFrame,SafeIFrameQueueProcessCount,SafeIFrameQueueProcessTotal,WaitExit,))
        p.start()
        process_list.append(p)

    Process(target=safe_queue_push_i_frame,args=(unprocessed_list,SafeQueuePushIFrame,WaitExit)).start()
    
    # 等待所有进程完成
    for p in process_list:
        p.join()

def safe_queue_push_i_frame(unprocessed_list:list[str],SafeQueuePushIFrame:multiprocessing.Queue,WaitExit:multiprocessing.synchronize.Event):
    for path in unprocessed_list:
        wait_time = 0
        while True:
            try:
                SafeQueuePushIFrame.put_nowait(path)
                break
            except queue.Full:
                logging.warning(f"SafeQueuePushIFrame队列已满，第{wait_time}秒")
                time.sleep(0.1)
                wait_time += 1
            
            if WaitExit.is_set():
                return

        if WaitExit.is_set():
            return
 

def main_write_file():
    global SafeQueueWriteFileMd5,SafeQueueWriteFileIFrame,SafeMd5QueueProcessCount,WaitExit,FileListPath,FileListMd5,SafeIFrameQueueProcessCount,SafeIFrameQueueProcessTotal,SafeMd5QueueProcessTotal
    p = Process(target=write_file,args=(SafeQueueWriteFileMd5,SafeQueueWriteFileIFrame,WaitExit,SafeMd5QueueProcessCount,FileListPath,FileListMd5,SafeIFrameQueueProcessCount,SafeIFrameQueueProcessTotal,SafeMd5QueueProcessTotal,))
    p.start()

def parse_args():
    parser = argparse.ArgumentParser(description='扫描视频文件并提取16个I帧')
    parser.add_argument('--dir', type=str, required=True,
                      help='扫描目录,程序会递归遍历该目录下的视频文件，如果不传递，则程序退出')
    parser.add_argument('--work_dir', type=str, 
                      default='./video_scan_16_frame_work_dir',
                      help='工作目录,程序会在此目录存储file_list.json、I帧文件夹，如果不传递，默认./video_scan_16_frame_work_dir')
    
    args = parser.parse_args()
    
    if not args.dir:
        raise RuntimeError("必须指定扫描目录参数 --dir")

    global Dir, WorkDir,FileListJsonPath
    Dir = args.dir
    WorkDir = args.work_dir
    FileListJsonPath = os.path.join(WorkDir,"file_list.json")

if __name__ == "__main__":
    # 注册自定义信号处理函数
    signal.signal(signal.SIGINT, first_ctrl_c_handler)    
    parse_args()
    load_file_list()
    walk()
    main_write_file()
    main_md5()
    main_i_frame()
```

使用BRISQUE算法获取图像清晰度指数：
```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import argparse
import shutil
import torch
import piq
from skimage.io import imread
from multiprocessing import Pool, cpu_count
from tqdm import tqdm 

def compute_brisque(img_path: str) -> dict:
    """
    读取图像并计算其 BRISQUE 指标。返回包含图像路径和 BRISQUE 指标的字典。
    BRISQUE 值越小，表示图像质量越好（更清晰）。
    """
    try:
        # 读取图像（skimage.io.imread 返回的是 [H, W, C] 维度）
        img = imread(img_path)
        
        # 转换为 [N, C, H, W] 维度，并归一化到 [0,1]
        # 这里把 N=1，当作 batch size=1
        img_tensor = torch.tensor(img).permute(2, 0, 1).unsqueeze(0).float() / 255.0

        # 如果可用，则移动到 GPU
        if torch.cuda.is_available():
            img_tensor = img_tensor.cuda()

        # 使用 piq 计算 BRISQUE
        brisque_score = piq.brisque(img_tensor, data_range=1.0, reduction='none')

        # 因为 reduction='none'，返回的是一个长度为 batch size 的向量，这里 batch=1
        score_value = brisque_score.item()

        return {
            "path": img_path,
            "brisque": score_value
        }
    except Exception as e:
        # 如果图片损坏或处理出错，可返回一个较大的值防止影响排序
        # 或者您也可以根据需求做其他处理
        return {
            "path": img_path,
            "brisque": float('inf')
        }

def get_image_files_recursive(folder: str):
    """
    递归遍历 folder，返回所有 .jpg / .jpeg / .png 文件的绝对路径列表。
    """
    valid_exts = {'.jpg', '.jpeg', '.png'}
    result_files = []
    for root, dirs, files in os.walk(folder):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in valid_exts:
                result_files.append(os.path.join(root, f))
    return result_files

def copy_top_images(image_info_list, target_folder):
    """
    将结果列表按 BRISQUE 升序(分数越小越好)排序，取前 30% 复制到目标目录。
    """
    sorted_list = sorted(image_info_list, key=lambda x: x["brisque"])
    top_count = max(1, int(len(sorted_list) * 0.3))  # 取前30%
    top_images = sorted_list[:top_count]

    if not os.path.exists(target_folder):
        os.makedirs(target_folder, exist_ok=True)

    for item in tqdm(top_images, desc="复制图片"):
        src_path = item["path"]
        filename = os.path.basename(src_path)
        dst_path = os.path.join(target_folder, filename)
        shutil.copy2(src_path, dst_path)

def main():
    parser = argparse.ArgumentParser(description="使用 piq 库的 BRISQUE 指标来筛选图像清晰度")
    parser.add_argument("src_folder", type=str, help="源文件夹路径")
    parser.add_argument("dst_folder", type=str, help="目标文件夹路径")
    parser.add_argument("--workers", type=int, default=0,
                        help="并发进程数（默认为CPU核心数），0表示自动使用CPU核心数。")

    args = parser.parse_args()

    src_folder = args.src_folder
    dst_folder = args.dst_folder

    # 获取所有图片文件路径
    image_files = get_image_files_recursive(src_folder)
    if not image_files:
        print("在指定的源文件夹中未找到任何 jpg/jpeg/png 图片。")
        return

    # 如果用户指定了workers
    if args.workers <= 0:
        workers = cpu_count()
    else:
        workers = args.workers

    print(f"共找到 {len(image_files)} 张图片，开始计算 BRISQUE 分数...")

    # 使用多进程计算
    with Pool(processes=workers) as pool:
        image_info_list = list(tqdm(
            pool.imap(compute_brisque, image_files),
            total=len(image_files),
            desc="计算BRISQUE"
        ))

    print("BRISQUE 计算完毕，开始筛选并复制前 30% 的图片...")

    # 将分数较好的（更清晰）图片复制到目标文件夹
    copy_top_images(image_info_list, dst_folder)

    print(f"处理完成！前 30% 的清晰图片已复制到: {dst_folder}")

if __name__ == "__main__":
    # 如果在 Windows 并且需要 GPU，可以考虑手动设定 start_method = 'spawn'
    # import multiprocessing
    # multiprocessing.set_start_method('spawn')
    
    main()

```
