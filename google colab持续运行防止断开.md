通过操控电脑鼠标不断点击的方式让谷歌认为colab仍在使用。
防止在训练过程中，人不操作colab导致超时断开。

```python
from pynput.mouse import Button, Controller
import time

def move_and_click_periodically(x, y, interval=10):
    mouse = Controller()
    
    while True:
        # 移动鼠标到指定位置
        mouse.position = (x, y)
        print(f'现在鼠标位置: {mouse.position}')
        
        # 点击鼠标左键
        mouse.click(Button.left, 1)
        
        # 等待指定的时间间隔（秒）
        time.sleep(interval)

if __name__ == "__main__":
    # 指定要移动到的位置坐标
    x_position = 1024
    y_position = 1024

    #x_position = 128
    #y_position = 85
    
    # 调用函数，设置间隔时间为10秒
    move_and_click_periodically(x_position, y_position, interval=10)

```
