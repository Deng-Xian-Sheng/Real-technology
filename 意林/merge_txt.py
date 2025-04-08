# 递归读取txt文件，并合并成一个文件
import os

def merge_txt_files(directory_path):
    merged_content = ""
    count = 0
    # 递归读取txt文件
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            # if file.endswith(".txt"):
            if file.endswith(".md"):
                with open(os.path.join(root, file), "r", encoding="utf-8") as f:
                    merged_content += f.read()
                count += 1
    print(f"合并了{count}个文件")
    return merged_content

if __name__ == "__main__":
    # directory_path = "/media/likewendy/c5b68963-7f31-453f-8a33-11d45badf8cc/home/likewendy/Desktop/optillm/yolo/小说"
    directory_path = "./yilin_articles"
    merged_content = merge_txt_files(directory_path)
    with open("yilin_merged_content.txt", "w", encoding="utf-8") as f:
        f.write(merged_content)
