deepin的网络设置里没提供这种功能，但是大多数笔记本电脑的wifi网卡是支持的。

大多数网卡支持1个信道、1个ap、一个managed。

managed就是连接wifi，ap是开放热点，1个信道是你连的热点和你开的wifi是同信道。

这个功能有点类似于路由器的无线桥接(WDS)模式。

我这么做的原因是：
- 我的电脑开clash TUN，电脑开热点，ipad和手机直接免设置直连谷歌。
- 电脑有服务，手机和ipad直接通过网关访问服务。（否则你需要固定电脑在局域网的ip地址，不然DHCP之后ip变了你服务就访问不了了）
- 我电脑没法插有线，我只能连wifi。（这种情况有很多，比如电脑没RJ45口但是不想插扩展坞，比如得拉网线，比如我的USB联通随享网络不稳定，比如租房没得选等）

这个需求的实现，最核心的地方是:
虚拟接口ap0一旦被创建后，会被NetworkManager发现，然后NetworkManager会把类型从ap改成了managed，然后就没法开热点了。
解决办法是，创建->等几秒(NetworkManager改成managed)->再改回ap。

创建一个虚拟接口才能把一个物理无线网卡的ap功能给支出来。

脚本如下，UPLINK_SSID是上游wifi名(SSID)，likewendy-PC是我热点SSID，你随便设置。

推荐先在deepin的网络设置个人热点那块，先填上一个热点的配置，比如加密方法、密码。不然你得用环境变量来设置，脚本会读环境变量。

```bash
likewendy@likewendy-PC:~/fan_and_init$ cat wifi_sta_ap_guard.sh 
#!/usr/bin/env bash
set -u

# ====== 可配置 ======
UPLINK_IF="wlp0s20f3"
UPLINK_SSID="kyxq2802"
UPLINK_CON_NAME="${UPLINK_CON_NAME:-}"     # 若NM连接名不等于SSID，可指定

AP_IF="ap0"

HOTSPOT_CON="likewendy-PC"                 # NM连接名（不是SSID）
HOTSPOT_SSID="likewendy-PC"                # 热点SSID
HOTSPOT_PSK="${HOTSPOT_PSK:-}"             # export HOTSPOT_PSK='密码' 可让脚本写入
DELETE_PROFILE_ON_EXIT="${DELETE_PROFILE_ON_EXIT:-0}"

POLL_SEC=5
DEBUG="${DEBUG:-0}"

# ====== 内部变量 ======
CREATED_PROFILE=0
LAST_CHANNEL=""

log() { echo "[$(date '+%F %T')] $*"; }
dbg() { [[ "$DEBUG" == "1" ]] && log "DEBUG: $*"; }

nm() { LC_ALL=C nmcli "$@"; }

need_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    log "需要root权限，尝试sudo重启脚本..."
    exec sudo -E bash "$0" "$@"
  fi
}

freq_to_channel() {
  local f="$1"
  f="${f%.*}"
  [[ -z "$f" ]] && return 1
  if (( f == 2484 )); then echo 14; return 0; fi
  if (( f >= 2412 && f <= 2472 )); then echo $(( (f - 2407) / 5 )); return 0; fi
  if (( f >= 5000 && f <= 5900 )); then echo $(( (f - 5000) / 5 )); return 0; fi
  if (( f >= 5955 && f <= 7115 )); then echo $(( (f - 5950) / 5 )); return 0; fi
  return 1
}

freq_to_band() {
  local f="$1"; f="${f%.*}"
  if (( f >= 2412 && f <= 2484 )); then echo "bg"; else echo "a"; fi
}

uplink_connected() {
  iw dev "$UPLINK_IF" link 2>/dev/null | grep -q '^Connected to'
}

get_uplink_freq() {
  iw dev "$UPLINK_IF" link 2>/dev/null | awk '/freq:/{print $2; exit}'
}

find_nm_wifi_con_by_ssid() {
  local ssid="$1"
  nm -t -f NAME,TYPE,802-11-wireless.ssid con show 2>/dev/null \
    | awk -F: -v s="$ssid" '$2=="802-11-wireless" && $3==s {print $1; exit}'
}

ensure_uplink() {
  uplink_connected && return 0

  local con=""
  if [[ -n "$UPLINK_CON_NAME" ]]; then con="$UPLINK_CON_NAME"
  else con="$(find_nm_wifi_con_by_ssid "$UPLINK_SSID")"
  fi

  if [[ -z "$con" ]]; then
    log "找不到已保存Wi-Fi连接（SSID=$UPLINK_SSID）。先在GUI连一次并保存，或设置 UPLINK_CON_NAME。"
    return 1
  fi

  log "上联未连接，尝试拉起：$con"
  nm con up id "$con" ifname "$UPLINK_IF" >/dev/null 2>&1 || return 1
  return 0
}

wait_uplink() {
  local timeout="${1:-30}" i=0
  while (( i < timeout )); do
    uplink_connected && return 0
    sleep 1; ((i++))
  done
  return 1
}

ap_exists() { ip link show "$AP_IF" >/dev/null 2>&1; }

get_ap_type() {
  iw dev "$AP_IF" info 2>/dev/null | awk '/type/ {print $2; exit}'
}

ap_is_ap() {
  local t; t="$(get_ap_type || true)"
  [[ "$t" == "AP" || "$t" == "__AP" || "$t" == "__ap" ]]
}

nm_dev_state() {
  nm -t -f DEVICE,STATE dev status 2>/dev/null | awk -F: -v d="$1" '$1==d{print $2; exit}'
}

wait_nm_dev_present() {
  local dev="$1" timeout="${2:-10}" i=0
  while (( i < timeout )); do
    nm -t -f DEVICE dev status 2>/dev/null | grep -Fxq "$dev" && return 0
    sleep 1; ((i++))
  done
  return 1
}

wait_nm_dev_not_unavailable() {
  local dev="$1" timeout="${2:-10}" i=0 st=""
  while (( i < timeout )); do
    st="$(nm_dev_state "$dev" || true)"
    dbg "$dev nm-state=$st"
    [[ -n "$st" && "$st" != "unavailable" ]] && return 0
    sleep 1; ((i++))
  done
  return 1
}

create_ap_iface() {
  # 按你的经验：必须最终是AP；但创建时会被NM改回managed，所以创建为__ap即可
  log "创建虚拟接口 $AP_IF (type __ap)"
  if ! iw dev "$UPLINK_IF" interface add "$AP_IF" type __ap 2>/dev/null; then
    local phy
    phy="$(iw dev "$UPLINK_IF" info 2>/dev/null | awk '/wiphy/ {print "phy"$2; exit}')"
    [[ -z "$phy" ]] && return 1
    iw phy "$phy" interface add "$AP_IF" type __ap || return 1
  fi

  # 让NM看到它
  nm dev set "$AP_IF" managed yes >/dev/null 2>&1 || true
  wait_nm_dev_present "$AP_IF" 10 || true

  # 给NM“重置成managed”的时间（你手工成功经验）
  sleep 2
}

force_ap_type_like_manual() {
  # 模拟你手工操作：等NM发现后，再把ap0强制改回__ap
  local tries="${1:-8}" i t out
  for ((i=1; i<=tries; i++)); do
    t="$(get_ap_type || true)"
    if ap_is_ap; then
      dbg "$AP_IF type=$t (OK)"
      return 0
    fi

    dbg "尝试将 $AP_IF 从 type=$t 改为 __ap (第$i次)"
    # 尽量先down再改type
    ip link set "$AP_IF" down >/dev/null 2>&1 || true
    out="$(iw dev "$AP_IF" set type __ap 2>&1)" || true
    [[ -n "$out" ]] && dbg "iw set type 输出：$out"

    # 让NM继续管理（否则热点起不来）
    nm dev set "$AP_IF" managed yes >/dev/null 2>&1 || true

    sleep 1
  done
  return 1
}

ensure_ap_iface_ready() {
  if ! ap_exists; then
    create_ap_iface || return 1
  else
    nm dev set "$AP_IF" managed yes >/dev/null 2>&1 || true
  fi

  # 如果被NM改成managed（你日志里就是这样），按手工方式强制改回AP
  if ! ap_is_ap; then
    local t; t="$(get_ap_type || true)"
    log "检测到 $AP_IF type=$t（不是AP），将按手工策略强制改为AP"
    if ! force_ap_type_like_manual 10; then
      log "强制改AP失败，删除并重建 $AP_IF 后再试"
      iw dev "$AP_IF" del >/dev/null 2>&1 || true
      sleep 1
      create_ap_iface || return 1
      force_ap_type_like_manual 10 || return 1
    fi
  fi

  # 等 NM 设备状态从 unavailable 变为可用（通常是 disconnected）
  if ! wait_nm_dev_not_unavailable "$AP_IF" 10; then
    log "$AP_IF 在NM中仍是 unavailable，热点可能无法启动"
    return 1
  fi

  return 0
}

hotspot_profile_exists() {
  nm -t -f NAME con show 2>/dev/null | grep -Fxq "$HOTSPOT_CON"
}

hotspot_active() {
  nm -t -f NAME con show --active 2>/dev/null | grep -Fxq "$HOTSPOT_CON"
}

ensure_hotspot_profile() {
  local channel="$1" band="$2"

  if ! hotspot_profile_exists; then
    log "热点连接不存在，创建：$HOTSPOT_CON"
    nm con add type wifi ifname "$AP_IF" con-name "$HOTSPOT_CON" ssid "$HOTSPOT_SSID" \
      802-11-wireless.mode ap ipv4.method shared ipv6.method ignore connection.autoconnect no >/dev/null 2>&1 || return 1
    CREATED_PROFILE=1
  fi

  # 只在需要时修改，避免NM抖动
  local cur_ch cur_band
  cur_ch="$(nm -g 802-11-wireless.channel con show "$HOTSPOT_CON" 2>/dev/null | head -n1 || true)"
  cur_band="$(nm -g 802-11-wireless.band con show "$HOTSPOT_CON" 2>/dev/null | head -n1 || true)"

  if [[ "$cur_ch" != "$channel" || "$cur_band" != "$band" ]]; then
    log "更新热点配置：band $cur_band->$band, channel $cur_ch->$channel"
    nm con modify "$HOTSPOT_CON" \
      connection.interface-name "$AP_IF" \
      802-11-wireless.mode ap \
      802-11-wireless.band "$band" \
      802-11-wireless.channel "$channel" \
      ipv4.method shared ipv6.method ignore >/dev/null 2>&1 || return 1
  fi

  if [[ -n "$HOTSPOT_PSK" ]]; then
    nm con modify "$HOTSPOT_CON" \
      802-11-wireless-security.key-mgmt wpa-psk \
      802-11-wireless-security.psk "$HOTSPOT_PSK" >/dev/null 2>&1 || return 1
  fi

  return 0
}

start_hotspot() {
  # 不做down，直接up；更温和
  nm con up id "$HOTSPOT_CON" ifname "$AP_IF"
}

restart_hotspot() {
  nm con down id "$HOTSPOT_CON" >/dev/null 2>&1 || true
  sleep 1
  nm con up id "$HOTSPOT_CON" ifname "$AP_IF"
}

diag() {
  log "诊断信息（LC_ALL=C）："
  nm -f DEVICE,TYPE,STATE dev status 2>/dev/null | sed 's/^/  /'
  nm -f NAME,DEVICE,TYPE con show --active 2>/dev/null | sed 's/^/  /'
  iw dev "$AP_IF" info 2>/dev/null | sed 's/^/  /' || true
  log "ap0 nm-state=$(nm_dev_state "$AP_IF" || true), ap0 iw-type=$(get_ap_type || true)"
  nm -f GENERAL.STATE,GENERAL.MANAGED,GENERAL.REASON dev show "$AP_IF" 2>/dev/null | sed 's/^/  /' || true
}

cleanup() {
  log "开始清理：关闭热点、删除 $AP_IF ..."
  nm con down id "$HOTSPOT_CON" >/dev/null 2>&1 || true

  if [[ "$DELETE_PROFILE_ON_EXIT" == "1" || "$CREATED_PROFILE" == "1" ]]; then
    nm con delete id "$HOTSPOT_CON" >/dev/null 2>&1 || true
  fi

  if ap_exists; then
    iw dev "$AP_IF" del >/dev/null 2>&1 || true
  fi
}

on_int_term() {
  trap - INT TERM
  exit 0
}

# ====== 主流程 ======
need_root "$@"
trap cleanup EXIT
trap on_int_term INT TERM

log "开始守护：STA($UPLINK_IF) + AP($AP_IF) 并发热点"
log "上联SSID=$UPLINK_SSID；热点连接名=$HOTSPOT_CON；热点SSID=$HOTSPOT_SSID"
[[ "$DEBUG" == "1" ]] && log "DEBUG=1 已开启"

while true; do
  if ! ensure_uplink || ! wait_uplink 30; then
    log "上联未就绪，${POLL_SEC}s后重试"
    sleep "$POLL_SEC"
    continue
  fi

  freq="$(get_uplink_freq || true)"
  channel="$(freq_to_channel "${freq:-}" 2>/dev/null || true)"
  band="$(freq_to_band "${freq:-}" 2>/dev/null || true)"
  if [[ -z "${channel:-}" || -z "${band:-}" ]]; then
    log "无法解析上联freq=${freq:-}，${POLL_SEC}s后重试"
    sleep "$POLL_SEC"
    continue
  fi
  dbg "上联：freq=$freq => channel=$channel band=$band"

  if ! ensure_ap_iface_ready; then
    log "ap0 未就绪（通常是type被重置或NM仍unavailable），${POLL_SEC}s后重试"
    [[ "$DEBUG" == "1" ]] && diag
    sleep "$POLL_SEC"
    continue
  fi

  if ! ensure_hotspot_profile "$channel" "$band"; then
    log "热点配置确保失败，${POLL_SEC}s后重试"
    [[ "$DEBUG" == "1" ]] && diag
    sleep "$POLL_SEC"
    continue
  fi

  # 信道变化：必须重启热点以满足 #channels<=1
  if [[ "$channel" != "$LAST_CHANNEL" ]]; then
    log "同步信道：$LAST_CHANNEL -> $channel，重启热点"
    if ! restart_hotspot >/dev/null 2>&1; then
      log "热点重启失败"
      [[ "$DEBUG" == "1" ]] && diag
    fi
    LAST_CHANNEL="$channel"
    sleep "$POLL_SEC"
    continue
  fi

  # 信道未变：只要不active，就up一次
  if ! hotspot_active; then
    log "热点未激活，尝试启动"
    if ! start_hotspot >/dev/null 2>&1; then
      log "热点启动失败"
      [[ "$DEBUG" == "1" ]] && diag
    fi
  else
    dbg "热点已激活"
  fi

  sleep "$POLL_SEC"
done
```
