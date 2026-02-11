import os

# ============ 配置 ============
GIF_DIR = "gifs"
SCALE_OPTIONS = [round(i / 10, 1) for i in range(1, 21)]  # 缩放档位（0.1x ~ 2.0x）
DEFAULT_SCALE_INDEX = 9
TRANSPARENCY_OPTIONS = [round(i / 10, 1) for i in range(1, 11)]  # 透明度档位（0.1=10%）
DEFAULT_TRANSPARENCY_INDEX = 9  # 默认不透明

# 软件信息
AUTHOR_BILIBILI = "-fugu-"
AUTHOR_EMAIL = "1977184420@qq.com"
GITEE_RELEASES_URL = "https://gitee.com/lzy-buaa-jdi/ameath/releases"
SPEED_X = 3
SPEED_Y = 2
TRANSPARENT_COLOR = "pink"
STOP_CHANCE = 0.003  # 每帧停下的概率
STOP_DURATION_MIN = 4000  # 最小停止时间(ms)
STOP_DURATION_MAX = 8000  # 最大停止时间(ms)

# 帧率配置（性能优化）
MOVE_INTERVAL = 30  # 移动更新间隔(ms) ≈33fps
JITTER_INTERVAL = 5  # 抖动更新间隔(帧数) 每5帧更新一次随机抖动

# 运动配置
EDGE_ESCAPE_CHANCE = 0.3  # 撞边后直接消失概率
RESPAWN_MARGIN = 50  # 重生在屏幕外多少像素
TARGET_CHANGE_MIN = 200  # 目标点最小帧数（约4秒）
TARGET_CHANGE_MAX = 500  # 目标点最大帧数（约10秒）
OUTSIDE_TARGET_CHANCE = 0.4  # 目标点在屏幕外的概率
FOLLOW_DISTANCE = 80  # 跟随鼠标保持的距离
INERTIA_FACTOR = 0.95  # 惯性因子
INTENT_FACTOR = 0.05  # 意图因子
JITTER = 0.15  # 随机抖动幅度

# 状态机配置
MOTION_WANDER = "wander"  # 随机游荡
MOTION_FOLLOW = "follow"  # 跟随鼠标
MOTION_CURIOUS = "curious"  # 好奇：近距离观察
MOTION_REST = "rest"  # 休息：停下不动

# 状态参数
REST_CHANCE = 0.6  # 到达目标后休息的概率
REST_DURATION_MIN = 1000  # 休息最小时间(ms)
REST_DURATION_MAX = 3000  # 休息最大时间(ms)
REST_DISTANCE = 20  # 到达目标的判定距离
MIN_INTERVAL = 30000  # 暂停模式随机动画最小时间(ms)
MAX_INTERVAL = 120000  # 暂停模式随机动画最大时间(ms)

# 跟随参数
FOLLOW_START_DIST = 200  # 开始跟随的距离
FOLLOW_STOP_DIST = 60  # 停止跟随/好奇的距离

# 速度倍率
SPEED_WANDER = 0.8  # 游荡速度
SPEED_FOLLOW = 1.2  # 跟随速度
SPEED_CURIOUS = 0.5  # 好奇速度（慢）

CONFIG_FILE = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "ameath_config.json"
)

# Windows API 常量
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020

STAY_PUT_CHANCE = 0.3  # 停下时原地不动的概率
